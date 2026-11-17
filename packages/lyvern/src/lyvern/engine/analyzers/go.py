"""Go analyser built on tree-sitter (no execution, no network, no type information).

Conservative by design, like the JavaScript analyser: every rule looks for a pattern that is
risky or wrong on its face, and evidence is always taken from our own copy of the source.
Without type information some checks are deliberately narrow (for example the SQL rule only
fires when the built string visibly contains an SQL keyword). Security rules are skipped in
``_test.go`` files and ``testdata`` directories.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import PurePosixPath

import tree_sitter_go as ts_go
from tree_sitter import Language, Node, Parser

from lyvern.engine.analyzers.errors import AnalyzerError
from lyvern.engine.analyzers.generated import is_generated
from lyvern.engine.contracts import Category, Finding, Origin, Severity

MAX_EVIDENCE_LINES = 5
MAX_SPAN_LINES = 20

_SECRET_NAME = re.compile(
    r"(password|passwd|secret|api_?key|access_?token|auth_?token)", re.IGNORECASE
)
_PLACEHOLDER = re.compile(
    r"(example|changeme|change_me|your|xxx|placeholder|dummy|test|<.+>)", re.I
)
_TOKEN_SHAPES = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_HASH_LIKE = re.compile(r"^[0-9a-fA-F]{32,}$")  # a digest, not a credential
# a flag, config key or environment variable name ("es.password", "DB_PASSWORD"), not a credential
_KEY_NAME = re.compile(r"^([a-z][a-z0-9]*([._/-][a-z][a-z0-9]*)+|[A-Z][A-Z0-9]*(_[A-Z0-9]+)+)$")
_SUPPRESSED = re.compile(r"#nosec|nolint:[a-z0-9,]*gosec", re.IGNORECASE)
_SQL_WORD = re.compile(r"\b(select|insert|update|delete|drop|create|alter)\b", re.IGNORECASE)
_SHELLS = {"sh", "bash", "/bin/sh", "/bin/bash", "cmd", "cmd.exe", "powershell", "pwsh"}
_SHELL_FLAGS = {"-c", "/c", "/C", "-Command", "-command"}
_QUERY_METHODS = {"Query": 0, "QueryRow": 0, "Exec": 0, "Prepare": 0}
_QUERY_CONTEXT_METHODS = {
    "QueryContext": 1,
    "QueryRowContext": 1,
    "ExecContext": 1,
    "PrepareContext": 1,
}
_LITERAL_TYPES = {"interpreted_string_literal", "raw_string_literal"}


def is_supported(path: str) -> bool:
    return path.lower().endswith(".go")


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    return p.name.endswith("_test.go") or any(part in {"testdata", "vendor"} for part in p.parts)


@cache
def _language() -> Language:
    return Language(ts_go.language())


def _text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _unquote(node: Node) -> str:
    value = _text(node)
    return value[1:-1] if len(value) >= 2 else value


def _walk(root: Node) -> Iterator[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _arguments(call: Node) -> list[Node]:
    args = call.child_by_field_name("arguments")
    return list(args.named_children) if args is not None else []


def _callee(call: Node) -> tuple[str, str]:
    """('pkg', 'Name') for pkg.Name(...), ('', 'Name') for a plain call."""
    fn = call.child_by_field_name("function")
    if fn is None:
        return ("", "")
    if fn.type == "selector_expression":
        operand = fn.child_by_field_name("operand")
        field = fn.child_by_field_name("field")
        return (_text(operand), _text(field))
    return ("", _text(fn))


def _is_literal(node: Node | None) -> bool:
    return node is not None and node.type in _LITERAL_TYPES


def _contains_dynamic_part(node: Node) -> bool:
    """A string built with + or Sprintf that is not made only of literals."""
    if node.type == "binary_expression" and _text(node.child_by_field_name("operator")) == "+":
        return any(
            not _is_literal(part)
            and (part.type != "binary_expression" or _contains_dynamic_part(part))
            for part in (node.child_by_field_name("left"), node.child_by_field_name("right"))
            if part is not None
        )
    if node.type == "call_expression":
        pkg, name = _callee(node)
        args = _arguments(node)
        return (pkg, name) == ("fmt", "Sprintf") and len(args) >= 2 and _is_literal(args[0])
    return False


def _literal_text(node: Node) -> str:
    """All the literal text inside a built string (used to look for SQL keywords)."""
    return " ".join(_unquote(n) for n in _walk(node) if n.type in _LITERAL_TYPES)


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    category: Category
    severity: Severity
    confidence: float
    title: str
    description: str
    fix: str
    security: bool = False


_RULES = {
    r.rule_id: r
    for r in (
        _Rule(
            "tls-verification-off",
            Category.SECURITY,
            Severity.HIGH,
            0.85,
            "TLS certificate verification disabled",
            "InsecureSkipVerify: true turns off certificate checks and exposes the connection to interception.",
            "Remove the option and fix the certificate chain or trust store instead.",
            True,
        ),
        _Rule(
            "shell-command-injection",
            Category.SECURITY,
            Severity.HIGH,
            0.75,
            "Shell command built from dynamic input",
            "A shell is started with -c and a command assembled from non-constant values; shell metacharacters in those values run extra commands.",
            'Call the program directly with an argument list (exec.Command("prog", arg1, arg2)) and no shell.',
            True,
        ),
        _Rule(
            "sql-string-building",
            Category.SECURITY,
            Severity.HIGH,
            0.75,
            "SQL query built by string concatenation or Sprintf",
            "The query text is assembled from non-constant values, which allows SQL injection.",
            'Use placeholders and pass the values as arguments (db.Query("... WHERE id = ?", id)).',
            True,
        ),
        _Rule(
            "weak-hash",
            Category.SECURITY,
            Severity.LOW,
            0.50,
            "MD5 or SHA-1 used",
            "MD5 and SHA-1 are not collision resistant; do not use them for passwords, signatures or integrity checks.",
            "Use SHA-256 or better, and a password hashing function (bcrypt, scrypt, argon2) for passwords.",
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
            True,
        ),
        _Rule(
            "defer-in-loop",
            Category.RELIABILITY,
            Severity.LOW,
            0.70,
            "defer inside a loop",
            "Deferred calls run when the function returns, not at the end of each iteration, so resources pile up until then.",
            "Move the loop body into a function, or release the resource explicitly at the end of each iteration.",
        ),
        _Rule(
            "empty-error-branch",
            Category.RELIABILITY,
            Severity.LOW,
            0.75,
            "Error checked and then ignored",
            "The `if err != nil` branch is empty, so the failure is silently dropped.",
            "Return or log the error, or add a comment explaining why ignoring it is safe.",
        ),
    )
}


def _hardcoded(name: str, value: Node) -> bool:
    if not _SECRET_NAME.search(name) or value.type not in _LITERAL_TYPES:
        return False
    text = _unquote(value)
    return (
        len(text) >= 8
        and not _PLACEHOLDER.search(text)
        and not _HASH_LIKE.match(text)
        and not _KEY_NAME.match(text)
    )


def _check_node(node: Node) -> Iterator[tuple[str, Node]]:
    kind = node.type

    if kind == "keyed_element":
        parts = [c for c in node.named_children if c.type == "literal_element"]
        if len(parts) == 2:
            key, value = _text(parts[0]), parts[1]
            if key == "InsecureSkipVerify" and _text(value) == "true":
                yield "tls-verification-off", node
            inner = value.named_children[0] if value.named_children else None
            if inner is not None and _hardcoded(key, inner):
                yield "hardcoded-secret", node

    elif kind == "assignment_statement":
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        if left is not None and right is not None:
            if _text(left).endswith(".InsecureSkipVerify") and _text(right) == "true":
                yield "tls-verification-off", node
            if (
                left.named_children
                and right.named_children
                and _hardcoded(_text(left.named_children[0]), right.named_children[0])
            ):
                yield "hardcoded-secret", node

    elif kind in {"short_var_declaration", "var_spec", "const_spec"}:
        left = node.child_by_field_name("left") or node.child_by_field_name("name")
        right = node.child_by_field_name("right") or node.child_by_field_name("value")
        names = [
            c for c in (left.named_children if left is not None else []) if c.type == "identifier"
        ]
        if left is not None and left.type == "identifier":
            names = [left]
        values = list(right.named_children) if right is not None else []
        for ident, value in zip(names, values, strict=False):
            if _hardcoded(_text(ident), value):
                yield "hardcoded-secret", node
                break

    elif kind == "call_expression":
        pkg, name = _callee(node)
        args = _arguments(node)
        if pkg == "exec" and name in {"Command", "CommandContext"}:
            shift = 1 if name == "CommandContext" else 0
            if len(args) >= shift + 3:
                program, flag, command = args[shift], args[shift + 1], args[shift + 2]
                if (
                    _is_literal(program)
                    and _unquote(program) in _SHELLS
                    and _is_literal(flag)
                    and _unquote(flag) in _SHELL_FLAGS
                    and not _is_literal(command)
                ):
                    yield "shell-command-injection", node
        if pkg in {"md5", "sha1"} and name in {"New", "Sum"}:
            yield "weak-hash", node
        method_index = {**_QUERY_METHODS, **_QUERY_CONTEXT_METHODS}.get(name)
        if method_index is not None and pkg != "" and len(args) > method_index:
            query = args[method_index]
            if _contains_dynamic_part(query) and _SQL_WORD.search(_literal_text(query)):
                yield "sql-string-building", node

    elif kind in _LITERAL_TYPES:
        if _TOKEN_SHAPES.search(_text(node)):
            yield "secret-token-shape", node

    elif kind == "defer_statement":
        parent = node.parent
        while parent is not None and parent.type not in {"function_declaration", "func_literal"}:
            if parent.type == "for_statement":
                yield "defer-in-loop", node
                break
            parent = parent.parent

    elif kind == "if_statement":
        condition = node.child_by_field_name("condition")
        body = node.child_by_field_name("consequence")
        if condition is not None and body is not None and condition.type == "binary_expression":
            op = _text(condition.child_by_field_name("operator"))
            lhs = _text(condition.child_by_field_name("left"))
            rhs = _text(condition.child_by_field_name("right"))
            is_err_check = op == "!=" and rhs == "nil" and (lhs == "err" or lhs.endswith("Err"))
            empty = not any(
                c.type != "comment" for c in _walk(body) if c is not body and c.is_named
            )
            if is_err_check and empty and "comment" not in {c.type for c in _walk(body)}:
                yield "empty-error-branch", node


def _is_suppressed(lines: list[str], row: int) -> bool:
    """The author marked this line as reviewed for gosec (same line or the line above)."""
    here = lines[row - 1]
    above = lines[row - 2] if row >= 2 else ""
    return bool(_SUPPRESSED.search(here) or _SUPPRESSED.search(above))


def analyze_go(
    path: str,
    source: str,
    *,
    added_lines: set[int] | None = None,
) -> list[Finding]:
    if not is_supported(path):
        raise AnalyzerError(f"not a Go file: {path}")
    try:
        tree = Parser(_language()).parse(source.encode("utf-8"))
    except Exception as error:  # pragma: no cover - parser failure is not expected
        raise AnalyzerError(f"tree-sitter failed: {error}") from error

    lines = source.split("\n")
    skip_security = is_test_path(path)
    generated = is_generated(path, source)  # style rules are noise on generated code
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for node in _walk(tree.root_node):
        for rule_id, target in _check_node(node):
            rule = _RULES[rule_id]
            if (rule.security and skip_security) or (generated and not rule.security):
                continue
            row = target.start_point[0] + 1
            if (rule_id, row) in seen or row > len(lines):
                continue
            if rule.security and _is_suppressed(lines, row):
                continue
            seen.add((rule_id, row))
            end_row = min(target.end_point[0] + 1, row + MAX_SPAN_LINES)
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
                    detection_source=f"lyvern-go:{rule_id}",
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
