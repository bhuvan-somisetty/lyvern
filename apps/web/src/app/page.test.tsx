import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Overview, eventLabel } from "@/components/Overview";
import { RunDetail } from "@/components/RunDetail";
import type { Run, Stats } from "@/lib/api";

const stats: Stats = {
  runs_total: 3,
  runs_by_status: { succeeded: 2, failed: 1 },
  runs_by_event: { REQUEST_CHANGES: 1 },
  findings_total: 5,
  inline_comments_total: 4,
  deliveries_total: 7,
  deliveries_by_status: { queued: 3 },
  last_run_at: "2026-11-16T08:00:00Z",
};

const run: Run = {
  id: "11111111-1111-1111-1111-111111111111",
  repo: "owner/repo",
  pr_number: 12,
  pr_url: "https://github.com/owner/repo/pull/12",
  head_sha: "abcdef0123456789",
  status: "succeeded",
  event_posted: "REQUEST_CHANGES",
  findings_count: 5,
  inline_posted: 4,
  changes_dismissed: true,
  error: null,
  created_at: "2026-11-16T08:00:00Z",
  started_at: "2026-11-16T08:00:01Z",
  finished_at: "2026-11-16T08:00:09Z",
};

describe("Overview", () => {
  it("shows an honest empty state and zero totals when there are no reviews", () => {
    render(<Overview stats={null} runs={[]} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/No reviews yet/i)).toBeInTheDocument();
    const totals = screen.getByLabelText("Totals");
    expect(within(totals).getAllByText("0")).toHaveLength(4);
  });

  it("renders real numbers and a table of runs with accessible structure", () => {
    render(<Overview stats={stats} runs={[run]} />);
    const totals = screen.getByLabelText("Totals");
    expect(within(totals).getByText("5")).toBeInTheDocument();
    expect(within(totals).getByText("7")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(
      within(table).getByRole("link", { name: "owner/repo#12" }),
    ).toHaveAttribute("href", "/runs/11111111-1111-1111-1111-111111111111");
    expect(within(table).getByText("abcdef01")).toBeInTheDocument();
    expect(within(table).getByText("Changes requested")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(5);
  });

  it("shows an error alert instead of numbers when the API cannot be reached", () => {
    render(
      <Overview
        stats={null}
        runs={null}
        error="The API is not reachable. Is it running?"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("could not load");
    expect(screen.queryByLabelText("Totals")).not.toBeInTheDocument();
  });

  it("never shows invented activity", () => {
    render(<Overview stats={null} runs={[]} />);
    expect(
      screen.queryByText(/\d+\s*(PRs|findings) reviewed/i),
    ).not.toBeInTheDocument();
  });
});

describe("RunDetail", () => {
  it("shows the fields of one run, the dismissal note and a link to GitHub", () => {
    render(<RunDetail run={run} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "owner/repo#12",
    );
    expect(screen.getByText(/Dismissed by this bot/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open on GitHub" }),
    ).toHaveAttribute("href", "https://github.com/owner/repo/pull/12");
    expect(screen.queryByText("Error")).not.toBeInTheDocument();
  });

  it("shows the error and says when data is not available", () => {
    render(
      <RunDetail
        run={{
          ...run,
          status: "failed",
          error: "PublishError: boom",
          findings_count: null,
          event_posted: null,
        }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("PublishError: boom");
    expect(screen.getByText("No review posted")).toBeInTheDocument();
    expect(screen.getAllByText("not available").length).toBeGreaterThan(0);
  });
});

describe("eventLabel", () => {
  it("maps events to plain words", () => {
    expect(eventLabel("COMMENT")).toBe("Comment only");
    expect(eventLabel("APPROVE")).toBe("Approved by policy");
    expect(eventLabel(null)).toBe("No review posted");
  });
});
