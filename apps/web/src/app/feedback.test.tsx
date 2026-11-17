import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FeedbackCard } from "@/components/FeedbackCard";
import { Findings } from "@/components/Findings";
import { LoginForm } from "@/components/LoginForm";
import { Overview } from "@/components/Overview";
import { RunDetail } from "@/components/RunDetail";
import type { FeedbackSummary, Finding } from "@/lib/api";

const finding = (over: Partial<Finding> = {}): Finding => ({
  id: "22222222-2222-2222-2222-222222222222",
  run_id: "11111111-1111-1111-1111-111111111111",
  file_path: "app.py",
  line_start: 5,
  line_end: 5,
  severity: "high",
  category: "security",
  origin: "static_analysis",
  detection_source: "ruff:S307",
  title: "Use of possibly insecure function",
  confidence: 0.9,
  blocking: true,
  placed_inline: true,
  verdict: null,
  note: null,
  ...over,
});

describe("Findings", () => {
  it("says so honestly when nothing was stored", () => {
    render(<Findings findings={[]} runId="r" />);
    expect(screen.getByText(/stored no findings/i)).toBeInTheDocument();
  });

  it("shows each finding with its verdict state and submits the chosen verdict", () => {
    const action = vi.fn();
    render(
      <Findings
        findings={[finding({ verdict: "false_positive" })]}
        runId="run-1"
        action={action}
      />,
    );
    const list = screen.getByRole("list", { name: "Findings" });
    expect(
      within(list).getByText("app.py:5", { exact: false }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("verdict-22222222-2222-2222-2222-222222222222"),
    ).toHaveTextContent("False alarm");
    expect(screen.getByRole("button", { name: "False alarm" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByRole("button", { name: "Real problem" }),
    ).toHaveAttribute("aria-pressed", "false");

    const form = screen
      .getByRole("button", { name: "Real problem" })
      .closest("form");
    expect(form).not.toBeNull();
    expect(
      (form!.querySelector("input[name=finding_id]") as HTMLInputElement).value,
    ).toBe("22222222-2222-2222-2222-222222222222");
    expect(
      (form!.querySelector("input[name=run_id]") as HTMLInputElement).value,
    ).toBe("run-1");
    expect(
      screen.getAllByRole("button").map((b) => (b as HTMLButtonElement).value),
    ).toEqual(["true_positive", "false_positive", "unsure"]);
    fireEvent.submit(form!);
  });

  it("shows no buttons when no action is given (read-only view)", () => {
    render(<Findings findings={[finding()]} runId="r" />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText("Not reviewed yet")).toBeInTheDocument();
  });
});

const summary: FeedbackSummary = {
  findings_total: 10,
  labelled: 7,
  true_positive: 3,
  false_positive: 3,
  unsure: 1,
  precision: 0.5,
  precision_ci_low: 0.19,
  precision_ci_high: 0.81,
  by_source: [
    {
      source: "ruff:S307",
      true_positive: 3,
      false_positive: 0,
      unsure: 0,
      precision: 1,
    },
    {
      source: "llm:x",
      true_positive: 0,
      false_positive: 3,
      unsure: 1,
      precision: 0,
    },
  ],
};

describe("FeedbackCard", () => {
  it("shows no number when nothing has been labelled", () => {
    render(<FeedbackCard summary={null} />);
    expect(screen.getByText(/no precision number/i)).toBeInTheDocument();
    render(
      <FeedbackCard
        summary={{ ...summary, true_positive: 0, false_positive: 0, unsure: 2 }}
      />,
    );
    expect(screen.getAllByText(/no precision number/i)).toHaveLength(2);
  });

  it("shows precision with its interval and the sample, and leaves unsure out", () => {
    render(<FeedbackCard summary={summary} />);
    expect(screen.getByText(/50\.0%/)).toBeInTheDocument();
    expect(
      screen.getByText(/95% interval 19\.0% to 81\.0%/),
    ).toBeInTheDocument();
    expect(screen.getByText(/From 6 labelled findings/)).toBeInTheDocument();
    expect(
      screen.getByText(/1 marked not sure are left out/),
    ).toBeInTheDocument();
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText("100.0%")).toBeInTheDocument();
  });

  it("is part of the overview", () => {
    render(<Overview stats={null} runs={[]} feedback={summary} />);
    expect(
      screen.getByRole("heading", { name: "Measured precision" }),
    ).toBeInTheDocument();
  });
});

describe("LoginForm", () => {
  it("has a labelled password field and no message by default", () => {
    render(<LoginForm action={vi.fn()} />);
    expect(screen.getByLabelText("Username")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "type",
      "password",
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a clear message for each failure and a generic one for unknown codes", () => {
    for (const [code, text] of [
      ["bad", /Wrong username or password/],
      ["api", /not reachable/],
      ["wait", /Too many attempts/],
      ["config", /not configured/],
      ["weird", /Could not sign in/],
    ] as const) {
      const { unmount } = render(<LoginForm action={vi.fn()} error={code} />);
      expect(screen.getByRole("alert")).toHaveTextContent(text);
      unmount();
    }
  });
});

describe("role-based views", () => {
  it("a viewer sees the findings but no verdict buttons and a clear explanation", () => {
    render(
      <RunDetail
        run={{
          id: "11111111-1111-1111-1111-111111111111",
          repo: "o/r",
          pr_number: 1,
          pr_url: "https://github.com/o/r/pull/1",
          head_sha: "abcdef0123456789",
          status: "succeeded",
          event_posted: "COMMENT",
          findings_count: 1,
          inline_posted: 1,
          changes_dismissed: false,
          error: null,
          created_at: "2026-11-16T08:00:00Z",
          started_at: null,
          finished_at: null,
        }}
        findings={[finding()]}
        verdictAction={vi.fn()}
        canLabel={false}
      />,
    );
    expect(
      screen.getByText(/can read reviews but not mark findings/i),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(
      screen.getByText("Use of possibly insecure function"),
    ).toBeInTheDocument();
  });

  it("shows who is signed in on the overview", () => {
    render(
      <Overview
        stats={null}
        runs={[]}
        who={{ username: "alice", role: "reviewer" }}
        logout={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Signed in as alice (reviewer)"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign out" }),
    ).toBeInTheDocument();
  });
});
