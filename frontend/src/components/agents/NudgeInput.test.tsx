import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NudgeInput from "./NudgeInput";
import { sendNudge } from "../../api/client";

vi.mock("../../api/client", () => ({
  sendNudge: vi.fn().mockResolvedValue({ status: "nudge_set" }),
}));

const mockedSendNudge = vi.mocked(sendNudge);

describe("NudgeInput", () => {
  beforeEach(() => {
    mockedSendNudge.mockClear();
    mockedSendNudge.mockResolvedValue({ status: "nudge_set" });
  });

  it("renders input and send button", () => {
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    expect(screen.getByPlaceholderText(/guide this agent/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("send button disabled when input empty", () => {
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("calls sendNudge with correct args on button click", async () => {
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    await user.type(screen.getByPlaceholderText(/guide this agent/i), "focus on tests");
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(mockedSendNudge).toHaveBeenCalledWith("cr-1", "tdd_developer", "focus on tests");
  });

  it("calls sendNudge on Enter key press", async () => {
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "focus on tests{Enter}");
    expect(mockedSendNudge).toHaveBeenCalledWith("cr-1", "tdd_developer", "focus on tests");
  });

  it("does NOT call sendNudge on Shift+Enter", async () => {
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "focus on tests{Shift>}{Enter}{/Shift}");
    expect(mockedSendNudge).not.toHaveBeenCalled();
  });

  it("clears input after successful send", async () => {
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "focus on tests");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(input).toHaveValue("");
    });
  });

  it("send button disabled while sending", async () => {
    let resolveNudge!: (v: { status: string }) => void;
    mockedSendNudge.mockImplementation(
      () => new Promise<{ status: string }>((resolve) => { resolveNudge = resolve; }),
    );
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "focus on tests");
    await user.click(screen.getByRole("button", { name: /send/i }));
    // While the promise is pending, button and input should be disabled
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
    expect(input).toBeDisabled();
    // Resolve to clean up
    resolveNudge({ status: "nudge_set" });
    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
  });

  it("does not send whitespace-only text", async () => {
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "   ");
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(mockedSendNudge).not.toHaveBeenCalled();
  });

  it("keeps text and re-enables on sendNudge rejection", async () => {
    mockedSendNudge.mockRejectedValueOnce(new Error("network error"));
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "retry this");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
    // Text should be preserved so user can retry
    expect(input).toHaveValue("retry this");
    expect(screen.getByRole("button", { name: /send/i })).not.toBeDisabled();
  });

  it("can send again after a failed attempt", async () => {
    mockedSendNudge
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce({ status: "nudge_set" });
    const user = userEvent.setup();
    render(<NudgeInput crId="cr-1" role="tdd_developer" />);
    const input = screen.getByPlaceholderText(/guide this agent/i);
    await user.type(input, "retry this");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
    // Second attempt succeeds
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(input).toHaveValue("");
    });
    expect(mockedSendNudge).toHaveBeenCalledTimes(2);
  });
});
