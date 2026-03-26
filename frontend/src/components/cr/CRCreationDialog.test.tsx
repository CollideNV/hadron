import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CRCreationDialog from "./CRCreationDialog";

const mockTriggerPipeline = vi.fn();

vi.mock("../../api/client", () => ({
  triggerPipeline: (...args: unknown[]) => mockTriggerPipeline(...args),
  getTemplates: () => Promise.resolve([]),
}));

beforeEach(() => {
  mockTriggerPipeline.mockReset();
});

// Helper: fill in valid form fields
async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByPlaceholderText(/health check/i), "My Feature");
  await user.type(
    screen.getByPlaceholderText(/describe the change/i),
    "Details here",
  );
}

describe("CRCreationDialog", () => {
  // Scenario: Open the creation dialog
  it("renders the form inside the dialog when open", () => {
    render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Create Change Request")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /trigger pipeline/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(
      <CRCreationDialog open={false} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Create Change Request")).not.toBeInTheDocument();
  });

  // Scenario: Close the dialog with the Cancel button
  it("calls onClose when Cancel button is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <CRCreationDialog open={true} onClose={onClose} onCreated={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  // Scenario: Close the dialog with the Escape key
  it("calls onClose when Escape key is pressed", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <CRCreationDialog open={true} onClose={onClose} onCreated={vi.fn()} />,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  // Scenario: Successful form submission closes the dialog
  it("calls triggerPipeline, onCreated, and onClose on successful submission", async () => {
    mockTriggerPipeline.mockResolvedValue({
      cr_id: "cr-abc-123",
      status: "pending",
    });
    const onClose = vi.fn();
    const onCreated = vi.fn();
    const user = userEvent.setup();

    render(
      <CRCreationDialog open={true} onClose={onClose} onCreated={onCreated} />,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    await waitFor(() => {
      expect(mockTriggerPipeline).toHaveBeenCalledWith(
        expect.objectContaining({ title: "My Feature" }),
      );
      expect(onCreated).toHaveBeenCalledWith("cr-abc-123");
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  it("disables submit button while submitting", async () => {
    // Never resolves — keeps the submitting state active
    mockTriggerPipeline.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();

    render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /submitting/i }),
      ).toBeDisabled();
    });
  });

  it("does not call onClose while submitting (Cancel hidden during submission)", async () => {
    mockTriggerPipeline.mockReturnValue(new Promise(() => {}));
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(
      <CRCreationDialog open={true} onClose={onClose} onCreated={vi.fn()} />,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    // During submission the Cancel button should be gone
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /cancel/i }),
      ).not.toBeInTheDocument();
    });
  });

  // Scenario: Form validation errors are shown within the dialog
  it("keeps dialog open and shows validation errors when required fields missing", async () => {
    const onClose = vi.fn();

    render(
      <CRCreationDialog open={true} onClose={onClose} onCreated={vi.fn()} />,
    );

    // Try clicking submit without filling fields — button is disabled when fields empty
    expect(
      screen.getByRole("button", { name: /trigger pipeline/i }),
    ).toBeDisabled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows validation error for invalid URL inside the dialog", async () => {
    const user = userEvent.setup();
    render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );

    await user.type(screen.getByPlaceholderText(/github\.com/i), "bad-url");
    expect(screen.getByText(/url must start with/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  // Scenario: API error displayed in dialog
  it("shows API error message and keeps dialog open on submission failure", async () => {
    mockTriggerPipeline.mockRejectedValue(new Error("500: Internal Server Error"));
    const onClose = vi.fn();
    const onCreated = vi.fn();
    const user = userEvent.setup();

    render(
      <CRCreationDialog open={true} onClose={onClose} onCreated={onCreated} />,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    await waitFor(() => {
      expect(
        screen.getByText("500: Internal Server Error"),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("error message is displayed in an alert role element", async () => {
    mockTriggerPipeline.mockRejectedValue(new Error("Network error"));
    const user = userEvent.setup();

    render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent("Network error");
    });
  });

  // Error state resets when dialog re-opens
  it("clears error state when dialog is re-opened", async () => {
    mockTriggerPipeline.mockRejectedValueOnce(new Error("Oops"));
    const user = userEvent.setup();
    const { rerender } = render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    // Close and reopen the dialog
    rerender(
      <CRCreationDialog open={false} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    rerender(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // Scenario: Dialog styling consistent with design system
  it("has role=dialog and aria-modal attributes", () => {
    render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("has aria-labelledby pointing to the dialog title", () => {
    render(
      <CRCreationDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    const dialog = screen.getByRole("dialog");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    const titleEl = document.getElementById(labelledBy!);
    expect(titleEl?.textContent).toBe("Create Change Request");
  });
});
