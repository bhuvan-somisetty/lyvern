// @vitest-environment node
import { describe, expect, it } from "vitest";
import { demoFeedback, demoFindings, demoRun, demoRuns, demoStats, wilson } from "@/lib/demo";

describe("demo data", () => {
  it("is internally consistent: totals are computed from the findings and runs", () => {
    const stats = demoStats();
    const runs = demoRuns(100);
    expect(stats.runs_total).toBe(runs.length);
    const findings = runs.flatMap((r) => demoFindings(r.id));
    expect(stats.findings_total).toBe(findings.length);
    expect(stats.inline_comments_total).toBe(findings.filter((f) => f.placed_inline).length);
    expect(Object.values(stats.runs_by_event).reduce((a, b) => a + b, 0)).toBe(runs.length);
    for (const run of runs) {
      if (run.findings_count !== null) expect(demoFindings(run.id)).toHaveLength(run.findings_count);
    }
  });

  it("builds the precision summary from labelled findings only, leaving 'unsure' out", () => {
    const fb = demoFeedback();
    const all = demoRuns(100).flatMap((r) => demoFindings(r.id));
    const tp = all.filter((f) => f.verdict === "true_positive").length;
    const fp = all.filter((f) => f.verdict === "false_positive").length;
    expect(fb.true_positive).toBe(tp);
    expect(fb.false_positive).toBe(fp);
    expect(fb.precision).toBeCloseTo(tp / (tp + fp), 10);
    expect(fb.precision_ci_low!).toBeLessThan(fb.precision!);
    expect(fb.precision_ci_high!).toBeGreaterThan(fb.precision!);
    expect(fb.by_source.reduce((s, r) => s + r.true_positive, 0)).toBe(tp);
  });

  it("only uses invented repositories and ids that look like ids", () => {
    for (const run of demoRuns(100)) {
      expect(run.repo.startsWith("acme/")).toBe(true);
      expect(run.id).toMatch(/^[0-9a-f-]{36}$/);
      expect(demoRun(run.id)).toEqual(run);
    }
    expect(demoRun("not-a-run")).toBeUndefined();
    expect(demoRuns(3)).toHaveLength(3);
  });

  it("wilson interval matches known values and handles no data", () => {
    expect(wilson(0, 0)).toEqual([0, 1]);
    const [lo, hi] = wilson(7, 10);
    expect(lo).toBeCloseTo(0.397, 2);
    expect(hi).toBeCloseTo(0.892, 2);
  });
});
