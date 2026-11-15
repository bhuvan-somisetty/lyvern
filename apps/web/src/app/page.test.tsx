import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("shows an honest empty state and no fabricated metrics", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/No repositories are connected yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/\d+\s*(PRs|findings)/i)).not.toBeInTheDocument();
  });
});
