"""Known-vulnerability check for dependencies pinned in a manifest, using the OSV database.

Only EXACT pinned versions are checked (``name==1.2.3``, ``"name": "1.2.3"``, a ``go.mod``
require line): a version range does not say which version will be installed, so claiming it is
vulnerable would be a guess. Only package names and versions are sent to the lookup service,
never source code. If the lookup fails, the caller gets ``DependencyLookupError`` and the
review is marked incomplete instead of silently skipping the check.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol

import httpx

from lyvern.engine.analyzers.errors import AnalyzerError
from lyvern.engine.contracts import Category, Finding, Origin, Severity

OSV_URL = "https://api.osv.dev"
MAX_DEPENDENCIES = 200
MAX_DETAIL_LOOKUPS = 25
MAX_VULNS_PER_PACKAGE = 3

_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9.!+_-]*)"
)
_NPM_EXACT = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$")
_GO_REQ = re.compile(r"^\s*(?:require\s+)?([A-Za-z0-9][\w./~-]*\.[\w./~-]+)\s+(v\d[\w.+-]*)")
_SEVERITY = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MODERATE": Severity.MEDIUM,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


class DependencyLookupError(AnalyzerError):
    """The vulnerability database could not be queried (network, timeout, bad answer)."""


@dataclass(frozen=True)
class Dependency:
    ecosystem: str  # OSV ecosystem name: PyPI, npm, Go
    name: str
    version: str
    line: int


@dataclass(frozen=True)
class Vulnerability:
    id: str
    summary: str
    severity: Severity
    fixed: str | None


class DependencyLookup(Protocol):
    def vulnerabilities(
        self, dependencies: Sequence[Dependency]
    ) -> dict[tuple[str, str, str], list[Vulnerability]]: ...


def is_manifest(path: str) -> bool:
    name = PurePosixPath(path.replace("\\", "/")).name.lower()
    return (
        name == "package.json"
        or name == "go.mod"
        or (name.startswith("requirements") and name.endswith(".txt"))
    )


def _normalise_pypi(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_manifest(path: str, text: str) -> list[Dependency]:
    name = PurePosixPath(path.replace("\\", "/")).name.lower()
    if name == "package.json":
        found = _parse_package_json(text)
    elif name == "go.mod":
        found = _parse_go_mod(text)
    elif name.startswith("requirements") and name.endswith(".txt"):
        found = _parse_requirements(text)
    else:
        raise AnalyzerError(f"not a supported dependency manifest: {path}")
    return found[:MAX_DEPENDENCIES]


def _parse_requirements(text: str) -> list[Dependency]:
    found: list[Dependency] = []
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.split("#", 1)[0]
        if not line.strip() or line.lstrip().startswith("-"):
            continue
        match = _REQ_LINE.match(line)
        if match:
            found.append(
                Dependency("PyPI", _normalise_pypi(match.group(1)), match.group(2), number)
            )
    return found


def _parse_go_mod(text: str) -> list[Dependency]:
    found: list[Dependency] = []
    in_block = False
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.split("//", 1)[0].rstrip()
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_block = True
            continue
        if in_block and stripped == ")":
            in_block = False
            continue
        if not (in_block or stripped.startswith("require ")):
            continue
        match = _GO_REQ.match(stripped)
        if match:
            found.append(Dependency("Go", match.group(1), match.group(2), number))
    return found


def _parse_package_json(text: str) -> list[Dependency]:
    try:
        data: Any = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    lines = text.split("\n")
    found: list[Dependency] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        table = data.get(section)
        if not isinstance(table, dict):
            continue
        for name, version in table.items():
            if not (isinstance(name, str) and isinstance(version, str)):
                continue
            if not _NPM_EXACT.match(version):
                continue  # a range such as ^1.2.0 does not say which version is installed
            key = f'"{name}"'
            row = next((i for i, ln in enumerate(lines, 1) if key in ln and version in ln), None)
            if row is not None:
                found.append(Dependency("npm", name, version, row))
    return found


class OsvClient:
    """Queries https://osv.dev (free, no key). Package names and versions only."""

    def __init__(
        self, *, base_url: str = OSV_URL, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=20.0)

    def close(self) -> None:
        self._http.close()

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise DependencyLookupError(
                f"vulnerability lookup failed ({type(error).__name__})"
            ) from None
        if response.status_code != 200:
            raise DependencyLookupError(
                f"vulnerability lookup returned HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError:
            raise DependencyLookupError("vulnerability lookup returned invalid JSON") from None

    def vulnerabilities(
        self, dependencies: Sequence[Dependency]
    ) -> dict[tuple[str, str, str], list[Vulnerability]]:
        unique = list(dict.fromkeys((d.ecosystem, d.name, d.version) for d in dependencies))
        if not unique:
            return {}
        queries = [
            {"package": {"name": name, "ecosystem": eco}, "version": version}
            for eco, name, version in unique
        ]
        data = self._call("POST", "/v1/querybatch", json={"queries": queries})
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or len(results) != len(unique):
            raise DependencyLookupError("vulnerability lookup returned an unexpected answer")

        details: dict[str, Vulnerability] = {}
        found: dict[tuple[str, str, str], list[Vulnerability]] = {}
        for key, result in zip(unique, results, strict=True):
            ids = [str(v["id"]) for v in (result or {}).get("vulns", []) if "id" in v]
            for vuln_id in ids[:MAX_VULNS_PER_PACKAGE]:
                if vuln_id not in details:
                    if len(details) >= MAX_DETAIL_LOOKUPS:
                        break
                    details[vuln_id] = self._detail(vuln_id, key[0], key[1])
                found.setdefault(key, []).append(details[vuln_id])
        return found

    def _detail(self, vuln_id: str, ecosystem: str, package: str) -> Vulnerability:
        data = self._call("GET", f"/v1/vulns/{vuln_id}")
        if not isinstance(data, dict):
            raise DependencyLookupError("vulnerability lookup returned an unexpected answer")
        summary = str(data.get("summary") or data.get("details") or "").strip().split("\n")[0]
        raw = (data.get("database_specific") or {}).get("severity")
        severity = _SEVERITY.get(str(raw).upper(), Severity.MEDIUM)
        return Vulnerability(
            vuln_id, summary[:300], severity, _fixed_version(data, ecosystem, package)
        )


def _fixed_version(data: dict[str, Any], ecosystem: str, package: str) -> str | None:
    for affected in data.get("affected") or []:
        pkg = affected.get("package") or {}
        if pkg.get("ecosystem") != ecosystem or str(pkg.get("name", "")).lower() != package.lower():
            continue
        for rng in affected.get("ranges") or []:
            for event in rng.get("events") or []:
                if event.get("fixed"):
                    return str(event["fixed"])
    return None


def analyze_manifest(
    path: str,
    text: str,
    lookup: DependencyLookup,
    *,
    added_lines: set[int] | None = None,
) -> list[Finding]:
    dependencies = parse_manifest(path, text)
    if not dependencies:
        return []
    vulnerable = lookup.vulnerabilities(dependencies)
    lines = text.split("\n")
    findings: list[Finding] = []
    for dep in dependencies:
        vulns = sorted(
            vulnerable.get((dep.ecosystem, dep.name, dep.version), []),
            key=lambda v: (-v.severity.rank, v.id),
        )
        evidence = lines[dep.line - 1].strip() if vulns and dep.line <= len(lines) else ""
        if not vulns or not evidence:
            continue
        top = vulns[0]
        fixed = next((v.fixed for v in vulns if v.fixed), None)
        fix = (
            f"Upgrade {dep.name} to {fixed} or later (see the advisories for exact fixed versions)."
            if fixed
            else f"Upgrade {dep.name} to a version that is not affected, or remove it."
        )
        listing = "; ".join(
            f"{v.id}: {v.summary or 'listed as vulnerable'} (https://osv.dev/vulnerability/{v.id})"
            for v in vulns
        )
        many = len(vulns) > 1
        findings.append(
            Finding(
                category=Category.SECURITY,
                severity=top.severity,
                confidence=0.9,
                origin=Origin.STATIC_ANALYSIS,
                detection_source=f"osv:{top.id}",
                file_path=path,
                line_start=dep.line,
                line_end=dep.line,
                title=(
                    f"{len(vulns)} known vulnerabilities in {dep.name} {dep.version}"
                    if many
                    else f"Known vulnerability in {dep.name} {dep.version} ({top.id})"
                ),
                description=listing,
                evidence=evidence,
                impact="",
                recommended_fix=fix,
                introduced_by_pr=added_lines is None or dep.line in added_lines,
            )
        )
    findings.sort(key=lambda f: (f.line_start, f.detection_source))
    return findings
