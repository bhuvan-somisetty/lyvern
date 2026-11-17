"""Export the dashboard's real data as an anonymised, read-only snapshot for the web app.

Reads the same data the dashboard API serves (runs, findings, human verdicts) straight from the
database and writes ``apps/web/src/data/snapshot.json``. Nothing is invented. Names are hidden:
repositories become ``repo-A``, ``repo-B`` ..., file paths become ``file-N.ext``, commit ids become
a short hash, pull request links and free-text notes and errors are dropped.

Run from the repo root:  python -m uv run python scripts/export_dashboard_snapshot.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import string

from lyvern_api import dashboard

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "web" / "src" / "data" / "snapshot.json"


def _short(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:7]


def main() -> None:
    runs = dashboard.list_runs(limit=200, repo=None, status=None)
    stats = dashboard.stats()
    feedback = dashboard.feedback_summary()

    repo_names: dict[str, str] = {}
    file_names: dict[tuple[str, str], str] = {}
    out_runs, out_findings = [], {}
    for run in sorted(runs, key=lambda r: r.created_at):
        if run.repo not in repo_names:
            repo_names[run.repo] = "repo-" + string.ascii_uppercase[len(repo_names) % 26]
        row = run.model_dump(mode="json")
        row["repo"] = repo_names[run.repo]
        row["pr_url"] = ""
        row["head_sha"] = _short(run.head_sha)
        row["error"] = None
        out_runs.append(row)

        findings = []
        for f in dashboard.run_findings(run.id):
            key = (run.repo, f.file_path)
            if key not in file_names:
                ext = pathlib.PurePosixPath(f.file_path).suffix
                file_names[key] = f"file-{len(file_names) + 1}{ext}"
            item = f.model_dump(mode="json")
            item["file_path"] = file_names[key]
            item["note"] = None
            findings.append(item)
        out_findings[str(run.id)] = findings

    out_runs.sort(key=lambda r: r["created_at"], reverse=True)
    snapshot = {
        "stats": stats.model_dump(mode="json"),
        "feedback": feedback.model_dump(mode="json"),
        "runs": out_runs,
        "findings": out_findings,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(out_runs)} runs, {sum(map(len, out_findings.values()))} findings")


if __name__ == "__main__":
    main()
