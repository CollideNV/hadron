import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InterventionModal from "./InterventionModal";

const mockSendIntervention = vi.fn();

vi.mock("../../api/client", () => ({
  sendIntervention: (...args: unknown[]) => mockSendIntervention(...args),
}));

beforeEach(() => {
  mockSendIntervention.mockReset();
});

describe("InterventionModal", () => {
  it("renders Intervene button", () => {
    render(<InterventionModal crId="cr-1" />);
    expect(
      screen.getByRole("button", { name: /intervene/i }),
    ).toBeInTheDocument();
  });

  it("opens modal on button click", async () => {
    const user = userEvent.setup();
    render(<InterventionModal crId="cr-1" />);

    await user.click(screen.getByRole("button", { name: /intervene/i }));

    expect(screen.getByText("Send Intervention")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/focus on error handling/i),
    ).toBeInTheDocument();
  });

  it("closes modal on cancel", async () => {
    const user = userEvent.setup();
    render(<InterventionModal crId="cr-1" />);

    await user.click(screen.getByRole("button", { name: /intervene/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.queryByText("Send Intervention")).not.toBeInTheDocument();
  });

  it("sends intervention and shows confirmation", async () => {
    mockSendIntervention.mockResolvedValue({ status: "intervention_set" });
    const user = userEvent.setup();
    render(<InterventionModal crId="cr-1" />);

    await user.click(screen.getByRole("button", { name: /intervene/i }));
    await user.type(
      screen.getByPlaceholderText(/focus on error handling/i),
      "Fix the tests first",
    );
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(mockSendIntervention).toHaveBeenCalledWith(
      "cr-1",
      "Fix the tests first",
    );

    await waitFor(() => {
      expect(screen.getByText("Sent!")).toBeInTheDocument();
    });
  });

  it("disables send when textarea is empty", async () => {
    const user = userEvent.setup();
    render(<InterventionModal crId="cr-1" />);

    await user.click(screen.getByRole("button", { name: /intervene/i }));

    const sendButton = screen.getByRole("button", { name: /^send$/i });
    expect(sendButton).toBeDisabled();
  });

  it("keeps modal open on send error", async () => {
    mockSendIntervention.mockRejectedValue(new Error("network error"));
    const user = userEvent.setup();
    render(<InterventionModal crId="cr-1" />);

    await user.click(screen.getByRole("button", { name: /intervene/i }));
    await user.type(
      screen.getByPlaceholderText(/focus on error handling/i),
      "instructions",
    );
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      // Modal should still be open
      expect(screen.getByText("Send Intervention")).toBeInTheDocument();
    });
  });
});
