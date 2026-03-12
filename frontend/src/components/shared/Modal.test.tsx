import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Modal from "./Modal";

describe("Modal", () => {
  it("renders nothing when closed", () => {
    render(
      <Modal open={false} onClose={vi.fn()} title="Test">
        <p>Content</p>
      </Modal>,
    );
    expect(screen.queryByText("Test")).not.toBeInTheDocument();
  });

  it("renders title and children when open", () => {
    render(
      <Modal open={true} onClose={vi.fn()} title="My Modal">
        <p>Body text</p>
      </Modal>,
    );
    expect(screen.getByText("My Modal")).toBeInTheDocument();
    expect(screen.getByText("Body text")).toBeInTheDocument();
  });

  it("calls onClose on Escape key", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Test">
        <p>Content</p>
      </Modal>,
    );
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on backdrop click", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Test">
        <p>Content</p>
      </Modal>,
    );
    // Click the backdrop (the outer fixed div)
    const backdrop = screen.getByText("Test").closest(".fixed")!;
    await user.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });

  it("does not close on content click", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Test">
        <p>Content</p>
      </Modal>,
    );
    await user.click(screen.getByText("Content"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("has role=dialog and aria-modal", () => {
    render(
      <Modal open={true} onClose={vi.fn()} title="Accessible Modal">
        <p>Content</p>
      </Modal>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("has aria-labelledby pointing to the title", () => {
    render(
      <Modal open={true} onClose={vi.fn()} title="My Title">
        <p>Content</p>
      </Modal>,
    );
    const dialog = screen.getByRole("dialog");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    const titleEl = document.getElementById(labelledBy!);
    expect(titleEl?.textContent).toBe("My Title");
  });

  it("traps focus within the modal on Tab", async () => {
    const user = userEvent.setup();
    render(
      <Modal open={true} onClose={vi.fn()} title="Focus Trap">
        <button>First</button>
        <button>Last</button>
      </Modal>,
    );

    // Focus the first button
    const first = screen.getByText("First");
    const last = screen.getByText("Last");
    first.focus();

    // Tab from last should cycle to first
    last.focus();
    await user.tab();
    expect(document.activeElement).toBe(first);
  });

  it("traps focus on Shift+Tab from first element", async () => {
    const user = userEvent.setup();
    render(
      <Modal open={true} onClose={vi.fn()} title="Focus Trap">
        <button>First</button>
        <button>Last</button>
      </Modal>,
    );

    const first = screen.getByText("First");
    const last = screen.getByText("Last");
    first.focus();

    await user.tab({ shift: true });
    expect(document.activeElement).toBe(last);
  });
});
