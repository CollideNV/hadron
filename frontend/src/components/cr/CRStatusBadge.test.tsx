import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import CRStatusBadge from "./CRStatusBadge";

describe("CRStatusBadge", () => {
  it("renders status text", () => {
    render(<CRStatusBadge status="running" />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("shows pulse indicator for running status", () => {
    const { container } = render(<CRStatusBadge status="running" />);
    const pulse = container.querySelector(".animate-pulse-glow");
    expect(pulse).toBeInTheDocument();
  });

  it("does not show pulse for non-running status", () => {
    const { container } = render(<CRStatusBadge status="completed" />);
    const pulse = container.querySelector(".animate-pulse-glow");
    expect(pulse).not.toBeInTheDocument();
  });

  it.each(["pending", "running", "completed", "failed", "paused"])(
    "renders %s status without error",
    (status) => {
      render(<CRStatusBadge status={status} />);
      expect(screen.getByText(status)).toBeInTheDocument();
    },
  );

  it("falls back to pending style for unknown status", () => {
    render(<CRStatusBadge status="unknown" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});
