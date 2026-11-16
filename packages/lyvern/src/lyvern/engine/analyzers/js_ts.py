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
from lyvern.engine.contracts import Category, Finding, Origin, Severity

JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs"}
TS_SUFFIXES = {".ts", ".mts", ".cts"}
TSX_SUFFIXES = {".tsx"}
SUPPORTED_SUFFIXES = JS_SUFFIXES | TS_SUFFIXES | TSX_SUFFIXES
MAX_EVIDENCE_LINES = 5
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


def _empty_catch(caps: dict[str, list[Node]]) -> Node | None:
    body = _one(caps, "body")
    if body is None or body.named_children:
        return None
    inner = _text(body).strip()[1:-1].strip()
    return body if not inner else None  # a comment inside means it was deliberate


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
        _always,
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
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for rule in _RULES:
        if rule.security and skip_security:
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
