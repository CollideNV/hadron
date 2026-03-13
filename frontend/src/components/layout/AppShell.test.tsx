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

  it("renders Pipelines navigation link", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("Pipelines")).toBeInTheDocument();
  });

  it("does not render a /new link in the header", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    );
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).not.toContain("/new");
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

  it("links to the root path", () => {
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
  });
});
