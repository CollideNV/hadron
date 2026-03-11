import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import CostTracker from "./CostTracker";

describe("CostTracker", () => {
  it("renders formatted cost", () => {
    render(<CostTracker costUsd={1.2345} />);
    expect(screen.getByText("$1.2345")).toBeInTheDocument();
  });

  it("renders zero cost", () => {
    render(<CostTracker costUsd={0} />);
    expect(screen.getByText("$0.0000")).toBeInTheDocument();
  });

  it("renders cost label", () => {
    render(<CostTracker costUsd={0.5} />);
    expect(screen.getByText("Cost")).toBeInTheDocument();
  });
});
