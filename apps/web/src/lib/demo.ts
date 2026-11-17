// Demo mode (LYVERN_DEMO=1): built-in SAMPLE data so the dashboard can be shown publicly without
// a database, an API, a login or any real review. Repositories, pull requests and findings are
// invented for illustration, and the pages say so. All totals are computed from the findings below,
// so the numbers on screen always agree with each other.

import type { FeedbackSummary, Finding, Run, Stats, Verdict } from "@/lib/api";

export const DEMO_MODE = process.env.LYVERN_DEMO === "1";

const uuid = (kind: number, n: number) =>
  `${String(kind).padStart(8, "0")}-0000-4000-8000-${String(n).padStart(12, "0")}`;

type Template = {
  rule: string;
  title: string;
  severity: Finding["severity"];
  category: string;
  origin: string;
  file: string;
  line: number;
  blocking: boolean;
  inline: boolean;
  confidence: number;
};

const T: Record<string, Template> = {
  eval: { rule: "ruff:S307", title: "Use of possibly insecure function; consider ast.literal_eval", severity: "high", category: "security", origin: "static_analysis", file: "app/jobs/render.py", line: 41, blocking: true, inline: true, confidence: 0.9 },
  undefinedName: { rule: "ruff:F821", title: "Undefined name `vals`", severity: "high", category: "bug", origin: "static_analysis", file: "app/jobs/render.py", line: 57, blocking: true, inline: true, confidence: 0.95 },
  mutableDefault: { rule: "ruff:B006", title: "Do not use mutable data structures for argument defaults", severity: "medium", category: "bug", origin: "static_analysis", file: "app/utils/cache.py", line: 12, blocking: false, inline: true, confidence: 0.85 },
  unusedImport: { rule: "ruff:F401", title: "`os` imported but unused", severity: "low", category: "maintainability", origin: "static_analysis", file: "app/utils/cache.py", line: 1, blocking: false, inline: true, confidence: 0.95 },
  tlsOff: { rule: "lyvern-js:tls-verification-off", title: "TLS certificate verification disabled", severity: "high", category: "security", origin: "static_analysis", file: "src/lib/http.ts", line: 23, blocking: true, inline: true, confidence: 0.85 },
  dangerousHtml: { rule: "lyvern-js:react-dangerous-html", title: "dangerouslySetInnerHTML used", severity: "medium", category: "security", origin: "static_analysis", file: "src/components/Notice.tsx", line: 18, blocking: false, inline: true, confidence: 0.7 },
  emptyCatch: { rule: "lyvern-js:empty-catch", title: "Empty catch block swallows errors", severity: "low", category: "reliability", origin: "static_analysis", file: "src/hooks/useSync.ts", line: 64, blocking: false, inline: true, confidence: 0.7 },
  sqlConcat: { rule: "lyvern-go:sql-string-building", title: "SQL query built by string concatenation or Sprintf", severity: "high", category: "security", origin: "static_analysis", file: "store/orders.go", line: 88, blocking: true, inline: true, confidence: 0.75 },
  deferLoop: { rule: "lyvern-go:defer-in-loop", title: "defer inside a loop", severity: "low", category: "reliability", origin: "static_analysis", file: "store/orders.go", line: 140, blocking: false, inline: true, confidence: 0.7 },
  vulnDep: { rule: "osv:GHSA-35jh-r3h4-6jhm", title: "3 known vulnerabilities in lodash 4.17.20", severity: "high", category: "security", origin: "static_analysis", file: "package.json", line: 14, blocking: true, inline: true, confidence: 0.9 },
  xref: { rule: "lyvern-xref:removed-symbol-still-referenced", title: "`legacy_helper` is removed but still referenced elsewhere", severity: "medium", category: "bug", origin: "static_analysis", file: "app/helpers.py", line: 1, blocking: false, inline: false, confidence: 0.7 },
};

type RunSpec = {
  repo: string;
  pr: number;
  event: "REQUEST_CHANGES" | "COMMENT" | "APPROVE" | null;
  status: string;
  hoursAgo: number;
  dismissed?: boolean;
  findings: [keyof typeof T, Verdict | null][];
};

const SPECS: RunSpec[] = [
  { repo: "acme/payments-api", pr: 412, event: "REQUEST_CHANGES", status: "succeeded", hoursAgo: 2, findings: [["eval", "true_positive"], ["undefinedName", "true_positive"], ["mutableDefault", "true_positive"], ["unusedImport", null]] },
  { repo: "acme/web-dashboard", pr: 188, event: "COMMENT", status: "succeeded", hoursAgo: 5, findings: [["dangerousHtml", "false_positive"], ["emptyCatch", "false_positive"]] },
  { repo: "acme/edge-gateway", pr: 93, event: "REQUEST_CHANGES", status: "succeeded", hoursAgo: 9, findings: [["sqlConcat", "true_positive"], ["deferLoop", "unsure"]] },
  { repo: "acme/payments-api", pr: 411, event: "APPROVE", status: "succeeded", hoursAgo: 14, dismissed: true, findings: [] },
  { repo: "acme/web-dashboard", pr: 187, event: "REQUEST_CHANGES", status: "succeeded", hoursAgo: 20, findings: [["tlsOff", "true_positive"], ["vulnDep", "true_positive"]] },
  { repo: "acme/ml-pipeline", pr: 57, event: "COMMENT", status: "succeeded", hoursAgo: 26, findings: [["xref", "true_positive"]] },
  { repo: "acme/edge-gateway", pr: 92, event: "APPROVE", status: "succeeded", hoursAgo: 31, findings: [] },
  { repo: "acme/web-dashboard", pr: 186, event: "COMMENT", status: "succeeded", hoursAgo: 40, findings: [["emptyCatch", null], ["unusedImport", "true_positive"]] },
  { repo: "acme/ml-pipeline", pr: 56, event: null, status: "failed", hoursAgo: 48, findings: [] },
  { repo: "acme/payments-api", pr: 410, event: "COMMENT", status: "succeeded", hoursAgo: 55, findings: [["mutableDefault", "false_positive"]] },
  { repo: "acme/edge-gateway", pr: 91, event: "REQUEST_CHANGES", status: "partial", hoursAgo: 70, findings: [["sqlConcat", null]] },
  { repo: "acme/ml-pipeline", pr: 55, event: "APPROVE", status: "succeeded", hoursAgo: 96, findings: [] },
];

const NOW = Date.parse("2026-11-17T09:00:00Z");

function build() {
  const runs: Run[] = [];
  const findings: Finding[] = [];
  SPECS.forEach((spec, i) => {
    const id = uuid(1, i + 1);
    const created = new Date(NOW - spec.hoursAgo * 3600_000).toISOString();
    const finished = new Date(NOW - spec.hoursAgo * 3600_000 + 14_000).toISOString();
    runs.push({
      id,
      repo: spec.repo,
      pr_number: spec.pr,
      pr_url: `https://github.com/${spec.repo}/pull/${spec.pr}`,
      head_sha: (spec.pr * 7919).toString(16).padStart(8, "0") + "cafe" + String(i).padStart(4, "0"),
      status: spec.status,
      event_posted: spec.event,
      findings_count: spec.status === "failed" ? null : spec.findings.length,
      inline_posted: spec.status === "failed" ? null : spec.findings.filter(([k]) => T[k].inline).length,
      changes_dismissed: Boolean(spec.dismissed),
      error: spec.status === "failed" ? "GitHubError: 502 while reading the pull request (retry limit reached)" : null,
      created_at: created,
      started_at: created,
      finished_at: finished,
    });
    spec.findings.forEach(([key, verdict], j) => {
      const t = T[key];
      findings.push({
        id: uuid(2, i * 10 + j + 1),
        run_id: id,
        file_path: t.file,
        line_start: t.line,
        line_end: t.line,
        severity: t.severity,
        category: t.category,
        origin: t.origin,
        detection_source: t.rule,
        title: t.title,
        confidence: t.confidence,
        blocking: t.blocking,
        placed_inline: t.inline,
        verdict,
        note: null,
      });
    });
  });
  return { runs, findings };
}

const { runs: RUNS, findings: FINDINGS } = build();

export function wilson(successes: number, total: number): [number, number] {
  if (total <= 0) return [0, 1];
  const z = 1.96;
  const p = successes / total;
  const denom = 1 + (z * z) / total;
  const centre = (p + (z * z) / (2 * total)) / denom;
  const margin = (z * Math.sqrt((p * (1 - p)) / total + (z * z) / (4 * total * total))) / denom;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

function count<T>(items: T[], key: (item: T) => string | null): Record<string, number> {
  const out: Record<string, number> = {};
  for (const item of items) {
    const k = key(item) ?? "none";
    out[k] = (out[k] ?? 0) + 1;
  }
  return out;
}

export function demoStats(): Stats {
  return {
    runs_total: RUNS.length,
    runs_by_status: count(RUNS, (r) => r.status),
    runs_by_event: count(RUNS, (r) => r.event_posted),
    findings_total: FINDINGS.length,
    inline_comments_total: FINDINGS.filter((f) => f.placed_inline).length,
    deliveries_total: RUNS.length + 5,
    deliveries_by_status: { queued: RUNS.length, ignored: 5 },
    last_run_at: RUNS[0].created_at,
  };
}

export function demoFeedback(): FeedbackSummary {
  const labelled = FINDINGS.filter((f) => f.verdict);
  const tp = labelled.filter((f) => f.verdict === "true_positive").length;
  const fp = labelled.filter((f) => f.verdict === "false_positive").length;
  const unsure = labelled.filter((f) => f.verdict === "unsure").length;
  const [low, high] = wilson(tp, tp + fp);
  const sources = [...new Set(labelled.map((f) => f.detection_source))].sort();
  return {
    findings_total: FINDINGS.length,
    labelled: labelled.length,
    true_positive: tp,
    false_positive: fp,
    unsure,
    precision: tp + fp ? tp / (tp + fp) : null,
    precision_ci_low: tp + fp ? low : null,
    precision_ci_high: tp + fp ? high : null,
    by_source: sources.map((source) => {
      const rows = labelled.filter((f) => f.detection_source === source);
      const a = rows.filter((f) => f.verdict === "true_positive").length;
      const b = rows.filter((f) => f.verdict === "false_positive").length;
      return {
        source,
        true_positive: a,
        false_positive: b,
        unsure: rows.filter((f) => f.verdict === "unsure").length,
        precision: a + b ? a / (a + b) : null,
      };
    }),
  };
}

export const demoRuns = (limit: number): Run[] => RUNS.slice(0, limit);
export const demoRun = (id: string): Run | undefined => RUNS.find((r) => r.id === id);
export const demoFindings = (runId: string): Finding[] => FINDINGS.filter((f) => f.run_id === runId);
