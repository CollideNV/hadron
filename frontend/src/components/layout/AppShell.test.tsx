import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AppShell from "./AppShell";

describe("AppShell", () => {
  it("renders Hadron branding", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("Hadron")).toBeInTheDocument();
    expect(screen.getByText("by Collide")).toBeInTheDocument();
  });

  it("renders navigation links", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("Pipelines")).toBeInTheDocument();
    expect(screen.getByText("+ New CR")).toBeInTheDocument();
  });

  it("renders children", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div>Test content here</div>
        </AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("Test content here")).toBeInTheDocument();
  });

  it("links to correct paths", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div />
        </AppShell>
      </MemoryRouter>,
    );
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/");
    expect(hrefs).toContain("/new");
  });
});
