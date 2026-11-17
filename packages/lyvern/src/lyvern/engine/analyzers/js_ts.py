"""JavaScript / TypeScript analyser built on tree-sitter (no execution, no network).

Conservative by design: it reports only patterns that are risky or wrong on their face,
and only with evidence taken from our own copy of the source. Literal arguments (for
example ``eval("1")``) are not flagged because nothing user-controlled reaches them.
Security rules are skipped in test files. A file that tree-sitter parses with errors is
still analysed, because tree-sitter recovers locally.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import PurePosixPath

import tree_sitter_javascript as ts_javascript
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from lyvern.engine.analyzers.errors import AnalyzerError
from lyvern.engine.analyzers.generated import is_generated
from lyvern.engine.contracts import Category, Finding, Origin, Severity

JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs"}
TS_SUFFIXES = {".ts", ".mts", ".cts"}
TSX_SUFFIXES = {".tsx"}
SUPPORTED_SUFFIXES = JS_SUFFIXES | TS_SUFFIXES | TSX_SUFFIXES
MAX_EVIDENCE_LINES = 5
# Rules that were right too rarely on real code to be on by default. Measured on labelled real
# code: empty-catch was a real problem in 8 of 56 cases (14%) because deliberate best-effort
# catches are common; react-dangerous-html in 0 of about 45 (almost every use is a constant, build
# time content, a prop passed through or a test page, and the rule cannot see where data comes from).
# They run only when asked for (`include_noisy=True`, setting LYVERN_STRICT_STYLE_RULES).
NOISY_RULES = frozenset({"empty-catch", "react-dangerous-html"})
MAX_SPAN_LINES = 20

_SECRET_NAME = re.compile(
    r"(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)", re.I
)
_PLACEHOLDER = re.compile(
    r"(example|changeme|change_me|your|xxx|placeholder|dummy|test|<.+>|\$\{|process\.env)", re.I
)
_TOKEN_SHAPES = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_TS_SUPPRESS = re.compile(r"@ts-(ignore|nocheck)\b")
_HASH_LIKE = re.compile(r"^[0-9a-fA-F]{32,}$")  # a digest, not a credential
_EXEC_OBJECTS = {"child_process", "childProcess", "cp"}
_EXEC_NAMES = {"exec", "execSync"}


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    name = p.name.lower()
    return (
        any(
            part in {"test", "tests", "__tests__", "__mocks__", "e2e", "cypress"}
            for part in p.parts[:-1]
        )
        or ".test." in name
        or ".spec." in name
        or ".stories." in name  # Storybook demo data
    )


@cache
def _language(kind: str) -> Language:
    if kind == "ts":
        return Language(ts_typescript.language_typescript())
    if kind == "tsx":
        return Language(ts_typescript.language_tsx())
    return Language(ts_javascript.language())


def _kind_for(path: str) -> str | None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in TS_SUFFIXES:
        return "ts"
    if suffix in TSX_SUFFIXES:
        return "tsx"
    if suffix in JS_SUFFIXES:
        return "js"
    return None


def is_supported(path: str) -> bool:
    return _kind_for(path) is not None


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    category: Category
    severity: Severity
    confidence: float
    title: str
    description: str
    fix: str
    query: str
    # Decide from the captures whether this match is a real finding; returns the node to report.
    accept: Callable[[dict[str, list[Node]]], Node | None]
    security: bool = False


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text is not None else ""


def _is_literal(node: Node | None) -> bool:
    if node is None:
        return True
    if node.type == "string":
        return True
    if node.type == "template_string":
        return not any(child.type == "template_substitution" for child in node.named_children)
    return False


def _first_argument(call: Node) -> Node | None:
    args = call.child_by_field_name("arguments")
    if args is None or not args.named_children:
        return None
    return args.named_children[0]


def _one(caps: dict[str, list[Node]], name: str) -> Node | None:
    nodes = caps.get(name)
    return nodes[0] if nodes else None


def _eval_like(caps: dict[str, list[Node]]) -> Node | None:
    call = _one(caps, "call")
    if call is None:
        return None
    arg = _first_argument(call)
    return None if _is_literal(arg) else call


def _new_function(caps: dict[str, list[Node]]) -> Node | None:
    node = _one(caps, "node")
    if node is None:
        return None
    args = node.child_by_field_name("arguments")
    if args is None or not args.named_children:
        return None
    return None if all(_is_literal(a) for a in args.named_children) else node


def _timer_string(caps: dict[str, list[Node]]) -> Node | None:
    call = _one(caps, "call")
    if call is None:
        return None
    arg = _first_argument(call)
    if arg is None:
        return None
    is_code_string = arg.type == "string" or arg.type == "template_string"
    return call if is_code_string else None


def _dynamic_html(caps: dict[str, list[Node]]) -> Node | None:
    assign = _one(caps, "assign")
    if assign is None:
        return None
    right = assign.child_by_field_name("right")
    return None if _is_literal(right) else assign


def _document_write(caps: dict[str, list[Node]]) -> Node | None:
    call = _one(caps, "call")
    if call is None:
        return None
    return None if _is_literal(_first_argument(call)) else call


def _exec_injection(caps: dict[str, list[Node]]) -> Node | None:
    call = _one(caps, "call")
    if call is None:
        return None
    function = call.child_by_field_name("function")
    if function is None:
        return None
    if function.type == "member_expression":
        obj = function.child_by_field_name("object")
        prop = function.child_by_field_name("property")
        if (
            obj is None
            or prop is None
            or _text(obj) not in _EXEC_OBJECTS
            or _text(prop) not in _EXEC_NAMES
        ):
            return None
    elif function.type == "identifier":
        if _text(function) not in _EXEC_NAMES:
            return None
    else:
        return None
    arg = _first_argument(call)
    if arg is None or _is_literal(arg):
        return None
    if arg.type in {"template_string", "binary_expression", "identifier", "member_expression"}:
        return call
    return None


def _tls_off_pair(caps: dict[str, list[Node]]) -> Node | None:
    return _one(caps, "pair")


def _tls_env(caps: dict[str, list[Node]]) -> Node | None:
    assign = _one(caps, "assign")
    if assign is None:
        return None
    left = assign.child_by_field_name("left")
    right = assign.child_by_field_name("right")
    if left is None or right is None:
        return None
    if _text(left).endswith("NODE_TLS_REJECT_UNAUTHORIZED") and _text(right).strip("'\"` ") == "0":
        return assign
    return None


def _secret_value(caps: dict[str, list[Node]]) -> Node | None:
    name = _one(caps, "name")
    value = _one(caps, "value")
    if name is None or value is None:
        return None
    literal = _text(value)[1:-1]
    if len(literal) < 8 or _PLACEHOLDER.search(literal) or _HASH_LIKE.match(literal):
        return None
    if _SECRET_NAME.search(_text(name)):
        return value
    return None


def _token_shape(caps: dict[str, list[Node]]) -> Node | None:
    value = _one(caps, "value")
    if value is None:
        return None
    return value if _TOKEN_SHAPES.search(_text(value)) else None


# Calls that are routinely wrapped in "try { ... } catch {}" because failing to tidy up is
# harmless. Found on real code: these made up most of the false alarms of this rule.
_CLEANUP_METHODS = {
    "close", "stop", "disconnect", "off", "removeEventListener", "remove", "destroy", "abort",
    "cancel", "dispose", "unsubscribe", "revokeObjectURL", "releaseLock", "terminate",
}  # fmt: skip
_PROBE_ROOTS = {
    "navigator",
    "localStorage",
    "sessionStorage",
}  # may throw by design (privacy, denied)


def _call_of(statement: Node) -> Node | None:
    """The call in a statement like ``x.close();``, ``await x.close();`` or ``a = JSON.parse(s)``."""
    node: Node | None = statement
    while node is not None and node.type in {
        "expression_statement",
        "await_expression",
        "assignment_expression",
        "lexical_declaration",
        "variable_declaration",
        "variable_declarator",
        "parenthesized_expression",
    }:
        children = [c for c in node.named_children if c.type != "comment"]
        if node.type == "assignment_expression":
            node = node.child_by_field_name("right")
        elif node.type == "variable_declarator":
            node = node.child_by_field_name("value")
        elif children:
            node = children[-1]
        else:
            return None
    return node if node is not None and node.type == "call_expression" else None


def _chain_root_and_last(call: Node) -> tuple[str, str]:
    """('navigator', 'query') for navigator.permissions.query(...); ('', name) for name(...)."""
    fn = call.child_by_field_name("function")
    last = ""
    while fn is not None and fn.type in {
        "member_expression",
        "call_expression",
        "await_expression",
    }:
        if fn.type == "member_expression":
            if not last:
                prop = fn.child_by_field_name("property")
                last = _text(prop) if prop is not None else ""
            fn = fn.child_by_field_name("object")
        elif fn.type == "call_expression":
            fn = fn.child_by_field_name("function")
        else:
            fn = fn.named_children[0] if fn.named_children else None
    return (_text(fn) if fn is not None and fn.type == "identifier" else "", last)


def _is_best_effort(try_block: Node | None) -> bool:
    """True if the try block is one statement that is idiomatically allowed to fail silently."""
    if try_block is None:
        return False
    statements = [c for c in try_block.named_children if c.type != "comment"]
    if len(statements) != 1:
        return False
    call = _call_of(statements[0])
    if call is None:
        return False
    root, last = _chain_root_and_last(call)
    if last in _CLEANUP_METHODS:
        return True
    if root == "JSON" and last == "parse":  # parse with a fallback value
        return True
    return root in _PROBE_ROOTS  # browser features that throw when denied or unavailable


def _empty_catch(caps: dict[str, list[Node]]) -> Node | None:
    body = _one(caps, "body")
    if body is None or body.named_children:
        return None
    inner = _text(body).strip()[1:-1].strip()
    if inner:  # a comment inside means it was deliberate
        return None
    handler = body.parent
    try_statement = handler.parent if handler is not None else None
    try_block = try_statement.child_by_field_name("body") if try_statement is not None else None
    return None if _is_best_effort(try_block) else body


_SANITIZERS = {"sanitize", "sanitizeHtml", "sanitizeHTML", "purify"}


def _html_value(attribute: Node) -> Node | None:
    """The value of the ``__html`` key in ``dangerouslySetInnerHTML={{ __html: value }}``."""
    stack = [attribute]
    while stack:
        node = stack.pop()
        if node.type == "pair":
            key = node.child_by_field_name("key")
            if key is not None and _text(key).strip("'\"") == "__html":
                return node.child_by_field_name("value")
        stack.extend(node.children)
    return None


def _module_constant_is_literal(identifier: Node) -> bool:
    """True if the name is a top-level ``const`` of this file initialised with a plain string."""
    root = identifier
    while root.parent is not None:
        root = root.parent
    name = _text(identifier)
    for statement in root.named_children:
        if statement.type != "lexical_declaration" or not _text(statement).startswith("const "):
            continue
        for declarator in statement.named_children:
            if declarator.type != "variable_declarator":
                continue
            target = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")
            if target is not None and _text(target) == name and _is_literal(value):
                return True
    return False


def _html_is_safe(value: Node | None) -> bool:
    """Patterns that are not injection: a constant, a sanitiser call, JSON with `<` escaped."""
    if value is None:
        return False
    if _is_literal(value):
        return True
    if value.type == "identifier":
        return _module_constant_is_literal(value)
    if value.type != "call_expression":
        return False
    callee = value.child_by_field_name("function")
    if callee is None:
        return False
    callee_text = _text(callee)
    if callee_text.split(".")[-1] in _SANITIZERS:
        return True
    prop = callee.child_by_field_name("property") if callee.type == "member_expression" else None
    if prop is not None and _text(prop) == "replace":
        inner = callee.child_by_field_name("object")
        args = value.child_by_field_name("arguments")
        first = args.named_children[0] if args is not None and args.named_children else None
        is_json = inner is not None and _text(inner).startswith("JSON.stringify(")
        return bool(is_json and first is not None and "<" in _text(first))  # escapes "</script>"
    return False


def _dangerous_html(caps: dict[str, list[Node]]) -> Node | None:
    node = _one(caps, "node")
    if node is None:
        return None
    return None if _html_is_safe(_html_value(node)) else node


def _ts_suppress(caps: dict[str, list[Node]]) -> Node | None:
    comment = _one(caps, "comment")
    return comment if comment is not None and _TS_SUPPRESS.search(_text(comment)) else None


def _always(caps: dict[str, list[Node]]) -> Node | None:
    return _one(caps, "node")


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "eval",
        Category.SECURITY,
        Severity.HIGH,
        0.80,
        "eval() with a non-literal argument",
        "eval executes its argument as code; if any part of it can be influenced by a user this is code injection.",
        "Avoid eval. Parse data with JSON.parse or use a lookup table or function instead.",
        '(call_expression function: (identifier) @fn (#eq? @fn "eval")) @call',
        _eval_like,
        True,
    ),
    _Rule(
        "new-function",
        Category.SECURITY,
        Severity.HIGH,
        0.80,
        "Function constructor with a non-literal argument",
        "new Function(...) compiles a string into code, which is equivalent to eval.",
        "Avoid generating code from strings; pass a real function instead.",
        '(new_expression constructor: (identifier) @c (#eq? @c "Function")) @node',
        _new_function,
        True,
    ),
    _Rule(
        "timer-string",
        Category.SECURITY,
        Severity.MEDIUM,
        0.70,
        "setTimeout/setInterval called with a string",
        "A string passed to a timer is evaluated like eval.",
        "Pass a function: setTimeout(() => { ... }, delay).",
        '(call_expression function: (identifier) @fn (#match? @fn "^(setTimeout|setInterval)$")) @call',
        _timer_string,
        True,
    ),
    _Rule(
        "inner-html",
        Category.SECURITY,
        Severity.MEDIUM,
        0.70,
        "Dynamic HTML assigned to innerHTML/outerHTML",
        "Assigning a non-literal string to innerHTML can allow cross-site scripting if the value contains user input.",
        "Use textContent, or sanitise the HTML first (for example with DOMPurify).",
        '(assignment_expression left: (member_expression property: (property_identifier) @p (#match? @p "^(innerHTML|outerHTML)$"))) @assign',
        _dynamic_html,
        True,
    ),
    _Rule(
        "document-write",
        Category.SECURITY,
        Severity.MEDIUM,
        0.70,
        "document.write with dynamic content",
        "document.write with a non-literal argument can inject markup or script.",
        "Create elements with DOM APIs and set textContent.",
        '(call_expression function: (member_expression object: (identifier) @o property: (property_identifier) @p (#eq? @o "document") (#match? @p "^(write|writeln)$"))) @call',
        _document_write,
        True,
    ),
    _Rule(
        "react-dangerous-html",
        Category.SECURITY,
        Severity.MEDIUM,
        0.70,
        "dangerouslySetInnerHTML used",
        "dangerouslySetInnerHTML renders raw HTML and bypasses React's escaping; unsanitised input allows cross-site scripting.",
        "Render text through React, or sanitise the HTML with a vetted library before passing it.",
        '(jsx_attribute (property_identifier) @a (#eq? @a "dangerouslySetInnerHTML")) @node',
        _dangerous_html,
        True,
    ),
    _Rule(
        "child-process-exec",
        Category.SECURITY,
        Severity.HIGH,
        0.70,
        "Shell command built from dynamic input",
        "child_process.exec runs a shell; interpolating variables into the command allows command injection.",
        "Use execFile/spawn with an argument array and no shell.",
        "(call_expression) @call",
        _exec_injection,
        True,
    ),
    _Rule(
        "tls-verification-off",
        Category.SECURITY,
        Severity.HIGH,
        0.85,
        "TLS certificate verification disabled",
        "rejectUnauthorized: false turns off certificate checks and exposes the connection to interception.",
        "Remove the option and fix the certificate chain instead.",
        '(pair key: (property_identifier) @k value: (false) (#eq? @k "rejectUnauthorized")) @pair',
        _tls_off_pair,
        True,
    ),
    _Rule(
        "tls-env-off",
        Category.SECURITY,
        Severity.HIGH,
        0.85,
        "TLS verification disabled through the environment",
        "Setting NODE_TLS_REJECT_UNAUTHORIZED to 0 disables certificate verification for the whole process.",
        "Do not disable verification; trust the correct certificate authority instead.",
        "(assignment_expression) @assign",
        _tls_env,
        True,
    ),
    _Rule(
        "hardcoded-secret",
        Category.SECURITY,
        Severity.MEDIUM,
        0.60,
        "Possible hardcoded credential",
        "A string literal is assigned to a name that suggests a password, key or token.",
        "Load secrets from the environment or a secret manager; never commit them.",
        "[(variable_declarator name: (identifier) @name value: (string) @value) (pair key: (property_identifier) @name value: (string) @value)]",
        _secret_value,
        True,
    ),
    _Rule(
        "secret-token-shape",
        Category.SECURITY,
        Severity.HIGH,
        0.80,
        "String that looks like a real secret token",
        "A string literal matches the format of a GitHub, AWS or API token or a private key.",
        "Revoke the credential, remove it from the code and history, and load it from a secret store.",
        "(string) @value",
        _token_shape,
        True,
    ),
    _Rule(
        "empty-catch",
        Category.RELIABILITY,
        Severity.LOW,
        0.70,
        "Empty catch block swallows errors",
        "The error is caught and ignored, so failures become invisible.",
        "Handle or log the error, or add a comment explaining why ignoring it is safe.",
        "(catch_clause body: (statement_block) @body)",
        _empty_catch,
    ),
    _Rule(
        "debugger",
        Category.MAINTAINABILITY,
        Severity.LOW,
        0.90,
        "debugger statement left in code",
        "A debugger statement pauses execution when developer tools are open.",
        "Remove the debugger statement.",
        "(debugger_statement) @node",
        _always,
    ),
    _Rule(
        "ts-suppress",
        Category.MAINTAINABILITY,
        Severity.LOW,
        0.60,
        "TypeScript checking suppressed",
        "@ts-ignore / @ts-nocheck hides type errors instead of fixing them.",
        "Fix the type error or use @ts-expect-error with an explanation.",
        "(comment) @comment",
        _ts_suppress,
    ),
)


@cache
def _compiled(kind: str, rule_id: str) -> Query | None:
    rule = next(r for r in _RULES if r.rule_id == rule_id)
    try:
        return Query(_language(kind), rule.query)
    except Exception:  # a node type missing from this grammar (for example JSX in plain TS)
        return None


def analyze_js_ts(
    path: str,
    source: str,
    *,
    added_lines: set[int] | None = None,
    include_noisy: bool = False,
) -> list[Finding]:
    kind = _kind_for(path)
    if kind is None:
        raise AnalyzerError(f"not a JavaScript/TypeScript file: {path}")
    try:
        tree = Parser(_language(kind)).parse(source.encode("utf-8"))
    except Exception as error:  # pragma: no cover - parser failure is not expected
        raise AnalyzerError(f"tree-sitter failed: {error}") from error

    lines = source.split("\n")
    skip_security = is_test_path(path)
    generated = is_generated(path, source)  # style rules are noise on generated code
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for rule in _RULES:
        if (rule.security and skip_security) or (generated and not rule.security):
            continue
        if rule.rule_id in NOISY_RULES and not include_noisy:
            continue
        query = _compiled(kind, rule.rule_id)
        if query is None:
            continue
        for _pattern, caps in QueryCursor(query).matches(tree.root_node):
            node = rule.accept(caps)
            if node is None:
                continue
            row = node.start_point[0] + 1
            if (rule.rule_id, row) in seen or row > len(lines):
                continue
            seen.add((rule.rule_id, row))
            end_row = min(node.end_point[0] + 1, row + MAX_SPAN_LINES)
            evidence = "\n".join(
                lines[row - 1 : min(end_row, row - 1 + MAX_EVIDENCE_LINES)]
            ).rstrip()
            if not evidence.strip():
                continue
            introduced = (
                True
                if added_lines is None
                else any(n in added_lines for n in range(row, end_row + 1))
            )
            findings.append(
                Finding(
                    category=rule.category,
                    severity=rule.severity,
                    confidence=rule.confidence,
                    origin=Origin.STATIC_ANALYSIS,
                    detection_source=f"lyvern-js:{rule.rule_id}",
                    file_path=path,
                    line_start=row,
                    line_end=max(row, end_row),
                    title=rule.title,
                    description=rule.description,
                    evidence=evidence,
                    impact="",
                    recommended_fix=rule.fix,
                    introduced_by_pr=introduced,
                )
            )
    findings.sort(key=lambda f: (f.line_start, f.detection_source))
    return findings
