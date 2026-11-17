import { describe, expect, it } from "vitest";
import snapshot from "@/data/snapshot.json";

// The public snapshot must hold real counts but no names that identify a repository or its files.
describe("dashboard snapshot", () => {
  const text = JSON.stringify(snapshot);

  it("hides repository names, links and commit ids", () => {
    for (const run of snapshot.runs) {
      expect(run.repo).toMatch(/^repo-[A-Z]$/);
      expect(run.pr_url).toBe("");
      expect(run.head_sha).toMatch(/^[0-9a-f]{7}$/);
    }
    expect(text).not.toMatch(/github\.com/i);
  });

  it("hides file paths and free-text notes", () => {
    for (const findings of Object.values(snapshot.findings)) {
      for (const f of findings) {
        expect(f.file_path).toMatch(/^file-\d+(\.\w+)?$/);
        expect(f.note).toBeNull();
      }
    }
  });

  it("keeps the counts consistent with the findings", () => {
    const total = Object.values(snapshot.findings).reduce(
      (n, list) => n + list.length,
      0,
    );
    // Run counters also include runs from before findings were stored, so they can only be larger.
    expect(snapshot.stats.findings_total).toBeGreaterThanOrEqual(total);
    expect(snapshot.feedback.findings_total).toBe(total);
    expect(snapshot.runs.length).toBe(snapshot.stats.runs_total);
  });
});
