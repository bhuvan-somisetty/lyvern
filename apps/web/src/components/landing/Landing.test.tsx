import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Landing } from "@/components/landing/Landing";
import type { Stats } from "@/lib/api";

const stats: Stats = {
  runs_total: 19,
  runs_by_status: { succeeded: 19 },
  runs_by_event: { REQUEST_CHANGES: 7, COMMENT: 7, APPROVE: 5 },
  findings_total: 76,
  inline_comments_total: 75,
  deliveries_total: 30,
  deliveries_by_status: {},
  last_run_at: null,
};

describe("Landing", () => {
  it("has one main heading, a link to the dashboard and the real totals", () => {
    render(<Landing stats={stats} feedback={null} samples={[]} />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(
      screen.getAllByRole("link", { name: /dashboard|open the data/i }).length,
    ).toBeGreaterThan(0);
    expect(screen.getByLabelText("19")).toBeInTheDocument();
    expect(screen.getByLabelText("76")).toBeInTheDocument();
  });

  it("states that approval is earned and that it never merges", () => {
    render(<Landing stats={stats} feedback={null} samples={[]} />);
    expect(screen.getAllByText(/never merges/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/zero findings of any severity/i),
    ).toBeInTheDocument();
  });

  it("shows a real finding on the hero card when one is given", () => {
    render(
      <Landing
        stats={stats}
        feedback={null}
        samples={[
          {
            id: "f",
            run_id: "r",
            file_path: "file-1.js",
            line_start: 4,
            line_end: 4,
            severity: "high",
            category: "security",
            origin: "static_analysis",
            detection_source: "lyvern-js:eval",
            title: "eval() with a non-literal argument",
            confidence: 0.9,
            blocking: true,
            placed_inline: true,
            verdict: null,
            note: null,
          },
        ]}
      />,
    );
    expect(
      screen.getByText("eval() with a non-literal argument"),
    ).toBeInTheDocument();
    expect(screen.getByText(/file-1\.js/)).toBeInTheDocument();
  });
});
