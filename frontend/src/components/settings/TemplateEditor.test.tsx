import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TemplateEditor from "./TemplateEditor";
import type { BackendTemplate } from "../../api/types";

const makeTemplate = (overrides: Partial<BackendTemplate> = {}): BackendTemplate => ({
  slug: "anthropic",
  display_name: "Anthropic",
  backend: "claude",
  stages: {
    intake: { act: { backend: "claude", model: "claude-sonnet-4-6" }, explore: null, plan: null },
    implementation: {
      act: { backend: "claude", model: "claude-sonnet-4-6" },
      explore: { backend: "claude", model: "claude-haiku-4-5-20251001" },
      plan: { backend: "claude", model: "claude-opus-4-6" },
    },
  },
  available_models: ["claude-haiku-4-5-20251001", "claude-opus-4-6", "claude-sonnet-4-6"],
  is_default: true,
  ...overrides,
});

const fakeTemplates: BackendTemplate[] = [
  makeTemplate(),
  makeTemplate({ slug: "openai", display_name: "OpenAI", backend: "openai", available_models: ["gpt-4.1", "gpt-4.1-mini", "o3"], is_default: false }),
  makeTemplate({ slug: "gemini", display_name: "Gemini", backend: "gemini", available_models: ["gemini-2.5-pro", "gemini-2.5-flash"], is_default: false }),
];

describe("TemplateEditor", () => {
  it("renders template tabs for each template", () => {
    render(
      <TemplateEditor templates={fakeTemplates} onChange={vi.fn()} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );
    expect(screen.getByTestId("template-tab-anthropic")).toBeInTheDocument();
    expect(screen.getByTestId("template-tab-openai")).toBeInTheDocument();
    expect(screen.getByTestId("template-tab-gemini")).toBeInTheDocument();
  });

  it("shows default badge on the default template", () => {
    render(
      <TemplateEditor templates={fakeTemplates} onChange={vi.fn()} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );
    expect(screen.getByTestId("default-badge")).toBeInTheDocument();
  });

  it("shows Set as Default button for non-default templates", async () => {
    const user = userEvent.setup();
    const onDefaultChange = vi.fn();
    render(
      <TemplateEditor templates={fakeTemplates} onChange={vi.fn()} defaultSlug="anthropic" onDefaultChange={onDefaultChange} />,
    );

    await user.click(screen.getByTestId("template-tab-openai"));
    await user.click(screen.getByTestId("set-default-btn"));
    expect(onDefaultChange).toHaveBeenCalledWith("openai");
  });

  it("renders stage grid with model dropdowns", () => {
    render(
      <TemplateEditor templates={fakeTemplates} onChange={vi.fn()} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );
    expect(screen.getByTestId("template-stage-grid")).toBeInTheDocument();
  });

  it("adds an OpenCode template when clicking + OpenCode", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <TemplateEditor templates={fakeTemplates} onChange={onChange} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    await user.click(screen.getByTestId("add-opencode-template"));
    expect(onChange).toHaveBeenCalledTimes(1);
    const newTemplates = onChange.mock.calls[0][0];
    expect(newTemplates.length).toBe(4);
    expect(newTemplates[3].backend).toBe("opencode");
  });

  it("shows delete button only for non-builtin templates", async () => {
    const user = userEvent.setup();
    const openCodeTemplate = makeTemplate({
      slug: "opencode-test",
      display_name: "Test Server",
      backend: "opencode",
      base_url: "http://localhost:11434/v1",
      available_models: ["qwen3:7b"],
      is_default: false,
    });
    const templates = [...fakeTemplates, openCodeTemplate];

    render(
      <TemplateEditor templates={templates} onChange={vi.fn()} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    // Select the OpenCode template
    await user.click(screen.getByTestId("template-tab-opencode-test"));
    expect(screen.getByTestId("delete-template-btn")).toBeInTheDocument();

    // Select a builtin — no delete button
    await user.click(screen.getByTestId("template-tab-anthropic"));
    expect(screen.queryByTestId("delete-template-btn")).not.toBeInTheDocument();
  });

  it("shows OpenCode-specific fields for custom templates", async () => {
    const user = userEvent.setup();
    const openCodeTemplate = makeTemplate({
      slug: "opencode-test",
      display_name: "Test Server",
      backend: "opencode",
      base_url: "http://localhost:11434/v1",
      available_models: ["qwen3:7b"],
      is_default: false,
    });

    render(
      <TemplateEditor templates={[...fakeTemplates, openCodeTemplate]} onChange={vi.fn()} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    await user.click(screen.getByTestId("template-tab-opencode-test"));
    expect(screen.getByTestId("opencode-display-name")).toBeInTheDocument();
    expect(screen.getByTestId("opencode-base-url")).toBeInTheDocument();
    expect(screen.getByTestId("opencode-models")).toBeInTheDocument();
  });

  it("calls onChange when deleting a template", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const openCodeTemplate = makeTemplate({
      slug: "opencode-test",
      display_name: "Test Server",
      backend: "opencode",
      is_default: false,
    });

    render(
      <TemplateEditor templates={[...fakeTemplates, openCodeTemplate]} onChange={onChange} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    await user.click(screen.getByTestId("template-tab-opencode-test"));
    await user.click(screen.getByTestId("delete-template-btn"));
    expect(onChange).toHaveBeenCalledTimes(1);
    const updated = onChange.mock.calls[0][0];
    expect(updated.length).toBe(3);
    expect(updated.find((t: BackendTemplate) => t.slug === "opencode-test")).toBeUndefined();
  });
});
