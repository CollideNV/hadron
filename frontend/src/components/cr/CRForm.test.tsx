import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CRForm from "./CRForm";

describe("CRForm", () => {
  it("renders all form fields", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    expect(screen.getByPlaceholderText(/health check/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/describe the change/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/github\.com/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /trigger pipeline/i })).toBeInTheDocument();
  });

  it("disables submit when title or description empty", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);
    const button = screen.getByRole("button", { name: /trigger pipeline/i });
    expect(button).toBeDisabled();
  });

  it("enables submit when title and description filled", async () => {
    const user = userEvent.setup();
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    await user.type(screen.getByPlaceholderText(/health check/i), "My CR");
    await user.type(screen.getByPlaceholderText(/describe the change/i), "Details");

    const button = screen.getByRole("button", { name: /trigger pipeline/i });
    expect(button).toBeEnabled();
  });

  it("calls onSubmit with form data", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<CRForm onSubmit={onSubmit} submitting={false} />);

    await user.type(screen.getByPlaceholderText(/health check/i), "My CR");
    await user.type(screen.getByPlaceholderText(/describe the change/i), "Details");
    await user.type(screen.getByPlaceholderText(/github\.com/i), "https://github.com/org/repo");

    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      title: "My CR",
      description: "Details",
      repo_urls: ["https://github.com/org/repo"],
      repo_default_branch: "main",
    });
  });

  it("submits without repo_urls when repo field empty", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<CRForm onSubmit={onSubmit} submitting={false} />);

    await user.type(screen.getByPlaceholderText(/health check/i), "My CR");
    await user.type(screen.getByPlaceholderText(/describe the change/i), "Details");
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ repo_urls: undefined }),
    );
  });

  it("shows submitting state", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={true} />);
    expect(screen.getByRole("button", { name: /submitting/i })).toBeDisabled();
  });
});
