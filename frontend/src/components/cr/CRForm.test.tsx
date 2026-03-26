import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CRForm from "./CRForm";
import type { BackendTemplate } from "../../api/types";

const fakeTemplates: BackendTemplate[] = [
  { slug: "anthropic", display_name: "Anthropic", backend: "claude", stages: {}, available_models: [], is_default: true },
  { slug: "openai", display_name: "OpenAI", backend: "openai", stages: {}, available_models: [], is_default: false },
  { slug: "gemini", display_name: "Gemini", backend: "gemini", stages: {}, available_models: [], is_default: false },
];

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

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "My CR",
        description: "Details",
        repo_urls: ["https://github.com/org/repo"],
        repo_default_branch: "main",
      }),
    );
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

  // Cancel button tests
  it("does not render Cancel button when onCancel not provided", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });

  it("renders Cancel button when onCancel is provided", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={false} onCancel={vi.fn()} />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("calls onCancel when Cancel button is clicked", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<CRForm onSubmit={vi.fn()} submitting={false} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("Cancel button does not submit the form", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<CRForm onSubmit={onSubmit} submitting={false} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  // Template selector tests
  it("renders template dropdown when templates provided", () => {
    render(
      <CRForm onSubmit={vi.fn()} submitting={false} templates={fakeTemplates} defaultTemplateSlug="anthropic" />,
    );
    expect(screen.getByTestId("cr-template-select")).toBeInTheDocument();
    expect(screen.getByLabelText("Backend Template")).toBeInTheDocument();
  });

  it("does not render template dropdown when no templates", () => {
    render(<CRForm onSubmit={vi.fn()} submitting={false} />);
    expect(screen.queryByTestId("cr-template-select")).not.toBeInTheDocument();
  });

  it("pre-selects the default template", () => {
    render(
      <CRForm onSubmit={vi.fn()} submitting={false} templates={fakeTemplates} defaultTemplateSlug="anthropic" />,
    );
    const select = screen.getByTestId("cr-template-select") as HTMLSelectElement;
    expect(select.value).toBe("anthropic");
  });

  it("includes template_slug in submit payload", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <CRForm onSubmit={onSubmit} submitting={false} templates={fakeTemplates} defaultTemplateSlug="anthropic" />,
    );

    await user.type(screen.getByPlaceholderText(/health check/i), "My CR");
    await user.type(screen.getByPlaceholderText(/describe the change/i), "Details");

    // Change template to openai
    await user.selectOptions(screen.getByTestId("cr-template-select"), "openai");
    await user.click(screen.getByRole("button", { name: /trigger pipeline/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ template_slug: "openai" }),
    );
  });
});
