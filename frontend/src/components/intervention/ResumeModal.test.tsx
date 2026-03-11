import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResumeModal from "./ResumeModal";

const mockResumePipeline = vi.fn();

vi.mock("../../api/client", () => ({
  resumePipeline: (...args: unknown[]) => mockResumePipeline(...args),
}));

beforeEach(() => {
  mockResumePipeline.mockReset();
});

describe("ResumeModal", () => {
  it("renders nothing for running status", () => {
    const { container } = render(
      <ResumeModal crId="cr-1" status="running" />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing for completed status", () => {
    const { container } = render(
      <ResumeModal crId="cr-1" status="completed" />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders Resume button for paused status", () => {
    render(<ResumeModal crId="cr-1" status="paused" />);
    expect(
      screen.getByRole("button", { name: /resume/i }),
    ).toBeInTheDocument();
  });

  it("renders Resume button for failed status", () => {
    render(<ResumeModal crId="cr-1" status="failed" />);
    expect(
      screen.getByRole("button", { name: /resume/i }),
    ).toBeInTheDocument();
  });

  it("opens modal showing preset actions", async () => {
    const user = userEvent.setup();
    render(<ResumeModal crId="cr-1" status="paused" />);

    await user.click(screen.getByRole("button", { name: /resume/i }));

    expect(screen.getByText("Resume Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Skip rebase conflicts")).toBeInTheDocument();
    expect(screen.getByText("Skip code review")).toBeInTheDocument();
    expect(screen.getByText("Retry from checkpoint")).toBeInTheDocument();
  });

  it("calls resumePipeline with preset overrides", async () => {
    mockResumePipeline.mockResolvedValue({ status: "resumed" });
    const user = userEvent.setup();
    render(<ResumeModal crId="cr-1" status="paused" />);

    await user.click(screen.getByRole("button", { name: /resume/i }));
    await user.click(screen.getByText("Skip rebase conflicts"));

    expect(mockResumePipeline).toHaveBeenCalledWith("cr-1", {
      rebase_clean: true,
    });
  });

  it("calls resumePipeline with empty overrides for retry", async () => {
    mockResumePipeline.mockResolvedValue({ status: "resumed" });
    const user = userEvent.setup();
    render(<ResumeModal crId="cr-1" status="failed" />);

    await user.click(screen.getByRole("button", { name: /resume/i }));
    await user.click(screen.getByText("Retry from checkpoint"));

    expect(mockResumePipeline).toHaveBeenCalledWith("cr-1", {});
  });

  it("shows error on resume failure", async () => {
    mockResumePipeline.mockRejectedValue(new Error("409: conflict"));
    const user = userEvent.setup();
    render(<ResumeModal crId="cr-1" status="paused" />);

    await user.click(screen.getByRole("button", { name: /resume/i }));
    await user.click(screen.getByText("Retry from checkpoint"));

    await waitFor(() => {
      expect(screen.getByText("409: conflict")).toBeInTheDocument();
    });
  });

  it("closes modal on cancel", async () => {
    const user = userEvent.setup();
    render(<ResumeModal crId="cr-1" status="paused" />);

    await user.click(screen.getByRole("button", { name: /resume/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.queryByText("Resume Pipeline")).not.toBeInTheDocument();
  });

  it("shows status text for paused", async () => {
    const user = userEvent.setup();
    render(<ResumeModal crId="cr-1" status="paused" />);

    await user.click(screen.getByRole("button", { name: /resume/i }));
    expect(screen.getByText(/paused pipeline/i)).toBeInTheDocument();
  });
});
