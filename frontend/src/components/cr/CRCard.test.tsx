import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import CRCard from "./CRCard";
import type { CRRun } from "../../api/types";

function renderCard(overrides: Partial<CRRun> = {}) {
  const run: CRRun = {
    cr_id: "cr-1",
    title: "Add feature X",
    status: "running",
    source: "api",
    external_id: null,
    cost_usd: 0.1234,
    error: null,
    created_at: new Date().toISOString(),
    updated_at: null,
    ...overrides,
  };
  return render(
    <MemoryRouter>
      <CRCard run={run} />
    </MemoryRouter>,
  );
}

describe("CRCard", () => {
  it("renders cr_id and title", () => {
    renderCard();
    expect(screen.getByText("cr-1")).toBeInTheDocument();
    expect(screen.getByText("Add feature X")).toBeInTheDocument();
  });

  it("shows 'Untitled CR' when title is empty", () => {
    renderCard({ title: "" });
    expect(screen.getByText("Untitled CR")).toBeInTheDocument();
  });

  it("displays cost when > 0", () => {
    renderCard({ cost_usd: 0.5678 });
    expect(screen.getByText("$0.5678")).toBeInTheDocument();
  });

  it("hides cost when 0", () => {
    renderCard({ cost_usd: 0 });
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("links to detail page", () => {
    renderCard();
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/cr/cr-1");
  });

  it("shows relative time for recent creation", () => {
    renderCard({ created_at: new Date().toISOString() });
    expect(screen.getByText("just now")).toBeInTheDocument();
  });

  it("shows status badge", () => {
    renderCard({ status: "completed" });
    expect(screen.getByText("completed")).toBeInTheDocument();
  });
});
