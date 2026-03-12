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

  // URL validation tests
  it("shows error for invalid URL", async () => {
    const user = userEvent.setup();
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    await user.type(screen.getByPlaceholderText(/github\.com/i), "not-a-url");
    expect(screen.getByText(/url must start with/i)).toBeInTheDocument();
  });

  it("clears error when URL becomes valid", async () => {
    const user = userEvent.setup();
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    const urlInput = screen.getByPlaceholderText(/github\.com/i);
    await user.type(urlInput, "not-a-url");
    expect(screen.getByText(/url must start with/i)).toBeInTheDocument();

    await user.clear(urlInput);
    await user.type(urlInput, "https://github.com/org/repo");
    expect(screen.queryByText(/url must start with/i)).not.toBeInTheDocument();
  });

  it("allows empty URL (optional field)", async () => {
    const user = userEvent.setup();
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    // Empty URL should not show error
    expect(screen.queryByText(/url must start with/i)).not.toBeInTheDocument();

    // Type something invalid, then clear
    const urlInput = screen.getByPlaceholderText(/github\.com/i);
    await user.type(urlInput, "x");
    expect(screen.getByText(/url must start with/i)).toBeInTheDocument();

    await user.clear(urlInput);
    expect(screen.queryByText(/url must start with/i)).not.toBeInTheDocument();
  });

  it("disables submit when URL is invalid", async () => {
    const user = userEvent.setup();
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    await user.type(screen.getByPlaceholderText(/health check/i), "My CR");
    await user.type(screen.getByPlaceholderText(/describe the change/i), "Details");
    await user.type(screen.getByPlaceholderText(/github\.com/i), "bad-url");

    expect(screen.getByRole("button", { name: /trigger pipeline/i })).toBeDisabled();
  });

  // Accessibility: label associations
  it("has properly associated labels", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);

    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
    expect(screen.getByLabelText("Repository URL")).toBeInTheDocument();
    expect(screen.getByLabelText("Default Branch")).toBeInTheDocument();
  });
});
