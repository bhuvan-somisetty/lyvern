"""Dependency vulnerability check: manifest parsing, OSV client, findings, pipeline behaviour."""

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from lyvern.engine.analyzers import AnalyzerError
from lyvern.engine.analyzers.deps import (
    Dependency,
    DependencyLookupError,
    OsvClient,
    Vulnerability,
    analyze_manifest,
    is_manifest,
    parse_manifest,
)
from lyvern.engine.contracts import Category, Origin, ReviewEvent, RunStatus, Severity
from lyvern.engine.decision import StageState
from lyvern.engine.policy import ReviewPolicy
from lyvern.github.models import ChangedFileInfo, PullRequestInfo
from lyvern.github.refs import PullRequestRef
from lyvern.review_pipeline import review_pull_request

# ------------------------------------------------------------------------------- parsing


def test_manifest_names_are_recognised() -> None:
    for path in ("requirements.txt", "api/requirements-dev.txt", "package.json", "svc/go.mod"):
        assert is_manifest(path)
    for path in ("README.txt", "package-lock.json", "tsconfig.json", "go.sum", "a.py"):
        assert not is_manifest(path)


def test_requirements_only_exact_pins_are_taken_with_their_line_numbers() -> None:
    text = (
        "# pinned\n"
        "Requests==2.19.0\n"
        "Django[argon2]==3.0.0 ; python_version > '3.8'\n"
        "flask>=1.0\n"
        "-r base.txt\n"
        "--hash=sha256:abc\n"
        "\n"
        "PyYAML_extra==5.1  # trailing comment\n"
        "numpy==1.20.0 \\\n"
        "    --hash=sha256:def\n"
    )
    deps = parse_manifest("requirements.txt", text)
    assert [(d.name, d.version, d.line) for d in deps] == [
        ("requests", "2.19.0", 2),
        ("django", "3.0.0", 3),
        ("pyyaml-extra", "5.1", 8),
        ("numpy", "1.20.0", 9),
    ]
    assert all(d.ecosystem == "PyPI" for d in deps)


def test_package_json_only_exact_versions_are_taken() -> None:
    text = (
        "{\n"
        '  "name": "app",\n'
        '  "dependencies": {\n'
        '    "lodash": "4.17.20",\n'
        '    "react": "^18.2.0",\n'
        '    "left-pad": "~1.3.0",\n'
        '    "tar": "*"\n'
        "  },\n"
        '  "devDependencies": {\n'
        '    "minimist": "1.2.5"\n'
        "  }\n"
        "}\n"
    )
    deps = parse_manifest("web/package.json", text)
    assert [(d.ecosystem, d.name, d.version, d.line) for d in deps] == [
        ("npm", "lodash", "4.17.20", 4),
        ("npm", "minimist", "1.2.5", 10),
    ]
    assert parse_manifest("package.json", "not json") == []
    assert parse_manifest("package.json", "[1, 2]") == []
    assert parse_manifest("package.json", '{"dependencies": {"a": 1, "b": "1.0.0"}}')[0].name == "b"


def test_go_mod_block_and_single_requires_are_taken() -> None:
    text = (
        "module example.com/app\n\n"
        "go 1.22\n\n"
        "require golang.org/x/text v0.3.0\n\n"
        "require (\n"
        "\tgithub.com/gin-gonic/gin v1.6.0\n"
        "\tgopkg.in/yaml.v2 v2.2.0 // indirect\n"
        ")\n\n"
        "replace github.com/x/y => ../y\n"
    )
    deps = parse_manifest("go.mod", text)
    assert [(d.name, d.version, d.line) for d in deps] == [
        ("golang.org/x/text", "v0.3.0", 5),
        ("github.com/gin-gonic/gin", "v1.6.0", 8),
        ("gopkg.in/yaml.v2", "v2.2.0", 9),
    ]
    assert all(d.ecosystem == "Go" for d in deps)


def test_unsupported_manifest_and_the_size_cap() -> None:
    with pytest.raises(AnalyzerError):
        parse_manifest("Cargo.toml", "x")
    many = "".join(f"pkg{i}==1.0.{i}\n" for i in range(500))
    assert len(parse_manifest("requirements.txt", many)) == 200


# ------------------------------------------------------------------------------ OSV client


def osv_handler(
    vulns: dict[str, list[str]], details: dict[str, dict[str, Any]], seen: list[httpx.Request]
) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            queries = json.loads(request.content)["queries"]
            results = [
                {"vulns": [{"id": i} for i in vulns.get(q["package"]["name"], [])]}
                if vulns.get(q["package"]["name"])
                else {}
                for q in queries
            ]
            return httpx.Response(200, json={"results": results})
        return httpx.Response(200, json=details[request.url.path.rsplit("/", 1)[1]])

    return handler


DETAIL = {
    "GHSA-1": {
        "id": "GHSA-1",
        "summary": "Request smuggling\nmore text on a second line",
        "database_specific": {"severity": "HIGH"},
        "affected": [
            {
                "package": {"ecosystem": "PyPI", "name": "requests"},
                "ranges": [
                    {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.20.0"}]}
                ],
            }
        ],
    },
    "GHSA-2": {
        "id": "GHSA-2",
        "details": "Something bad",
        "database_specific": {"severity": "MODERATE"},
    },
}


def test_client_batches_one_query_then_fetches_each_distinct_vulnerability_once() -> None:
    seen: list[httpx.Request] = []
    client = OsvClient(
        transport=httpx.MockTransport(
            osv_handler({"requests": ["GHSA-1", "GHSA-2"], "django": ["GHSA-1"]}, DETAIL, seen)
        )
    )
    deps = [
        Dependency("PyPI", "requests", "2.19.0", 2),
        Dependency("PyPI", "django", "3.0.0", 3),
        Dependency("PyPI", "requests", "2.19.0", 9),  # duplicate pin: asked once
        Dependency("PyPI", "clean", "1.0.0", 4),
    ]
    found = client.vulnerabilities(deps)
    posts = [r for r in seen if r.method == "POST"]
    gets = [r for r in seen if r.method == "GET"]
    assert len(posts) == 1 and len(json.loads(posts[0].content)["queries"]) == 3
    assert sorted(r.url.path.rsplit("/", 1)[1] for r in gets) == ["GHSA-1", "GHSA-2"]
    requests_vulns = found[("PyPI", "requests", "2.19.0")]
    assert [(v.id, v.severity, v.fixed) for v in requests_vulns] == [
        ("GHSA-1", Severity.HIGH, "2.20.0"),
        ("GHSA-2", Severity.MEDIUM, None),
    ]
    assert requests_vulns[0].summary == "Request smuggling"  # first line only
    assert ("PyPI", "clean", "1.0.0") not in found
    assert client.vulnerabilities([]) == {}


def test_lookup_failures_are_clean_errors_without_urls() -> None:
    dep = [Dependency("PyPI", "requests", "2.19.0", 1)]

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out reaching " + str(request.url), request=request)

    with pytest.raises(DependencyLookupError, match="ConnectTimeout") as info:
        OsvClient(transport=httpx.MockTransport(boom)).vulnerabilities(dep)
    assert "http" not in str(info.value)
    with pytest.raises(DependencyLookupError, match="HTTP 500"):
        OsvClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))).vulnerabilities(dep)
    with pytest.raises(DependencyLookupError, match="invalid JSON"):
        OsvClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x"))
        ).vulnerabilities(dep)
    wrong_count = httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []}))
    with pytest.raises(DependencyLookupError, match="unexpected"):
        OsvClient(transport=wrong_count).vulnerabilities(dep)
    assert issubclass(DependencyLookupError, AnalyzerError)


# ---------------------------------------------------------------------------- findings


class FakeLookup:
    def __init__(self, table: dict[tuple[str, str, str], list[Vulnerability]] | Exception) -> None:
        self.table = table

    def vulnerabilities(
        self, dependencies: Sequence[Dependency]
    ) -> dict[tuple[str, str, str], list[Vulnerability]]:
        if isinstance(self.table, Exception):
            raise self.table
        return self.table


HIGH = Vulnerability("GHSA-1", "Request smuggling", Severity.HIGH, "2.20.0")
KEY = ("PyPI", "requests", "2.19.0")


def test_a_vulnerable_pin_becomes_an_evidence_backed_static_finding() -> None:
    text = "flask==2.0.0\nrequests==2.19.0\n"
    (f,) = analyze_manifest("requirements.txt", text, FakeLookup({KEY: [HIGH]}), added_lines={2})
    assert (f.line_start, f.line_end, f.evidence) == (2, 2, "requests==2.19.0")
    assert f.origin == Origin.STATIC_ANALYSIS and f.category == Category.SECURITY
    assert f.severity == Severity.HIGH and f.confidence == 0.9
    assert f.detection_source == "osv:GHSA-1" and f.introduced_by_pr is True
    assert "2.20.0" in f.recommended_fix and "osv.dev/vulnerability/GHSA-1" in f.description
    assert "requests 2.19.0" in f.title


def test_an_untouched_vulnerable_pin_is_marked_pre_existing_and_a_clean_manifest_is_quiet() -> None:
    text = "requests==2.19.0\n"
    (f,) = analyze_manifest("requirements.txt", text, FakeLookup({KEY: [HIGH]}), added_lines={7})
    assert f.introduced_by_pr is False
    assert analyze_manifest("requirements.txt", text, FakeLookup({})) == []
    assert (
        analyze_manifest("requirements.txt", "flask>=1\n", FakeLookup(RuntimeError("unused"))) == []
    )


# ---------------------------------------------------------------------------- pipeline

REF = PullRequestRef("octo", "repo", 7)


def pr_info() -> PullRequestInfo:
    return PullRequestInfo(
        owner="octo", repo="repo", number=7, title="t", body="", author="a", state="open",
        draft=False, html_url="u", base_ref="main", base_sha="b" * 40, head_ref="x",
        head_sha="a" * 40, head_repo_full_name="octo/repo", changed_files=1, additions=1,
        deletions=0,
    )  # fmt: skip


class Source:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def get_pull_request(self, ref: PullRequestRef) -> PullRequestInfo:
        return pr_info()

    def list_changed_files(self, ref: PullRequestRef) -> list[ChangedFileInfo]:
        out = []
        for name, text in self.files.items():
            count = len(text.splitlines())
            patch = f"@@ -0,0 +1,{count} @@\n" + "".join(f"+{ln}\n" for ln in text.splitlines())
            out.append(
                ChangedFileInfo(
                    filename=name, status="added", additions=count, deletions=0, patch=patch
                )
            )
        return out

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.files[path]


REQ = {"requirements.txt": "requests==2.19.0\n"}


def test_a_vulnerable_new_pin_is_reported_inline_and_blocks_a_high_severity_one() -> None:
    draft = review_pull_request(Source(REQ), REF, deps=FakeLookup({KEY: [HIGH]}))
    assert [f.detection_source for f in draft.findings] == ["osv:GHSA-1"]
    assert {(p, ln) for p, ln, _s, _t in draft.inline} == {("requirements.txt", 1)}
    assert draft.decision.event == ReviewEvent.REQUEST_CHANGES
    assert draft.state.stages["dependencies"] == StageState.COMPLETED and draft.unanalyzed == ()


def test_a_clean_manifest_can_be_approved_only_when_the_check_ran() -> None:
    policy = ReviewPolicy(allow_approve=True)
    ok = review_pull_request(Source(REQ), REF, policy, deps=FakeLookup({}))
    assert (
        ok.decision.event == ReviewEvent.APPROVE
        and ok.state.stages["dependencies"] == StageState.COMPLETED
    )


def test_a_failed_lookup_makes_the_review_partial_and_never_approves() -> None:
    policy = ReviewPolicy(allow_approve=True)
    draft = review_pull_request(
        Source(REQ),
        REF,
        policy,
        deps=FakeLookup(DependencyLookupError("vulnerability lookup failed (ReadTimeout)")),
    )
    assert draft.state.run_status == RunStatus.PARTIAL
    assert draft.state.stages["dependencies"] == StageState.FAILED
    assert draft.decision.event == ReviewEvent.COMMENT
    assert "dependency check failed" in dict(draft.unanalyzed)["requirements.txt"]


def test_without_a_lookup_nothing_changes_for_manifests() -> None:
    draft = review_pull_request(
        Source({**REQ, "go.mod": "module x\n\nrequire golang.org/x/text v0.3.0\n"}), REF
    )
    assert "dependencies" not in draft.state.stages
    assert "requirements.txt" not in dict(draft.unanalyzed)  # plain text, as before
    assert dict(draft.unanalyzed)["go.mod"] == "no analyser for this file type yet"


def test_several_advisories_for_one_pin_become_one_finding_with_the_highest_severity() -> None:
    low = Vulnerability("GHSA-LOW", "Minor leak", Severity.LOW, None)
    crit = Vulnerability("GHSA-CRIT", "Remote code execution", Severity.CRITICAL, "3.1.0")
    (f,) = analyze_manifest(
        "requirements.txt", "requests==2.19.0\n", FakeLookup({KEY: [low, crit, HIGH]})
    )
    assert f.severity == Severity.CRITICAL and f.detection_source == "osv:GHSA-CRIT"
    assert f.title == "3 known vulnerabilities in requests 2.19.0"
    for vuln_id in ("GHSA-LOW", "GHSA-CRIT", "GHSA-1"):
        assert vuln_id in f.description
    assert "3.1.0" in f.recommended_fix
    no_fix = Vulnerability("GHSA-X", "No patch yet", Severity.HIGH, None)
    (g,) = analyze_manifest("requirements.txt", "requests==2.19.0\n", FakeLookup({KEY: [no_fix]}))
    assert "not affected" in g.recommended_fix
