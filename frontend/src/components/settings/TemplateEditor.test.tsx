import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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

  it("backfills empty stage models when Available Models is typed for an opencode template", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    // Freshly-added opencode template: every stage.model is "" and available_models is empty.
    const openCodeTemplate: BackendTemplate = {
      slug: "opencode-new",
      display_name: "New OpenCode",
      backend: "opencode",
      base_url: "",
      available_models: [],
      is_default: false,
      stages: {
        intake: { act: { backend: "opencode", model: "" }, explore: null, plan: null },
        implementation: {
          act: { backend: "opencode", model: "" },
          explore: { backend: "opencode", model: "" },
          plan: { backend: "opencode", model: "" },
        },
      },
    };

    render(
      <TemplateEditor templates={[...fakeTemplates, openCodeTemplate]} onChange={onChange} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    await user.click(screen.getByTestId("template-tab-opencode-new"));
    const modelsInput = screen.getByTestId("opencode-models");
    // fireEvent.change fires one synthetic event with the full value, so we
    // don't need a stateful wrapper around `onChange` for this assertion.
    fireEvent.change(modelsInput, { target: { value: "qwen3:7b" } });

    // The last onChange call should have the template with available_models populated
    // AND every previously-empty stage.model backfilled to "qwen3:7b".
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    const patched = lastCall.find((t: BackendTemplate) => t.slug === "opencode-new");
    expect(patched.available_models).toEqual(["qwen3:7b"]);
    expect(patched.stages.intake.act.model).toBe("qwen3:7b");
    expect(patched.stages.implementation.act.model).toBe("qwen3:7b");
    expect(patched.stages.implementation.explore.model).toBe("qwen3:7b");
    expect(patched.stages.implementation.plan.model).toBe("qwen3:7b");
  });

  it("reconciles stage models to the new first model when the previous value is no longer in Available Models", async () => {
    // Simulates mid-typing: template already has stage.model === "h" (from an
    // earlier backfill when Available Models was "h"), then the user finishes
    // typing so Available Models becomes "hf". The stale "h" should now be
    // replaced by "hf" since "h" is no longer a valid option.
    const onChange = vi.fn();
    const openCodeTemplate: BackendTemplate = {
      slug: "opencode-mid",
      display_name: "Mid Type",
      backend: "opencode",
      base_url: "",
      available_models: ["h"],
      is_default: false,
      stages: {
        intake: { act: { backend: "opencode", model: "h" }, explore: null, plan: null },
        implementation: {
          act: { backend: "opencode", model: "h" },
          explore: { backend: "opencode", model: "h" },
          plan: { backend: "opencode", model: "h" },
        },
      },
    };

    const user = userEvent.setup();
    render(
      <TemplateEditor templates={[...fakeTemplates, openCodeTemplate]} onChange={onChange} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    await user.click(screen.getByTestId("template-tab-opencode-mid"));
    const modelsInput = screen.getByTestId("opencode-models");
    fireEvent.change(modelsInput, { target: { value: "hf" } });

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    const patched = lastCall.find((t: BackendTemplate) => t.slug === "opencode-mid");
    expect(patched.available_models).toEqual(["hf"]);
    expect(patched.stages.intake.act.model).toBe("hf");
    expect(patched.stages.implementation.act.model).toBe("hf");
    expect(patched.stages.implementation.explore.model).toBe("hf");
    expect(patched.stages.implementation.plan.model).toBe("hf");
  });

  it("preserves a valid stage model when Available Models gains extra entries", async () => {
    // User has already saved a template with stage.model="qwen3:7b" and
    // available_models=["qwen3:7b"]. They now add "llama3.2" to the list.
    // "qwen3:7b" is still a member of the new list, so stage selections must
    // be preserved (no clobber).
    const onChange = vi.fn();
    const openCodeTemplate: BackendTemplate = {
      slug: "opencode-existing",
      display_name: "Existing",
      backend: "opencode",
      base_url: "",
      available_models: ["qwen3:7b"],
      is_default: false,
      stages: {
        intake: { act: { backend: "opencode", model: "qwen3:7b" }, explore: null, plan: null },
      },
    };

    const user = userEvent.setup();
    render(
      <TemplateEditor templates={[...fakeTemplates, openCodeTemplate]} onChange={onChange} defaultSlug="anthropic" onDefaultChange={vi.fn()} />,
    );

    await user.click(screen.getByTestId("template-tab-opencode-existing"));
    const modelsInput = screen.getByTestId("opencode-models");
    fireEvent.change(modelsInput, { target: { value: "qwen3:7b, llama3.2" } });

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    const patched = lastCall.find((t: BackendTemplate) => t.slug === "opencode-existing");
    expect(patched.available_models).toEqual(["qwen3:7b", "llama3.2"]);
    expect(patched.stages.intake.act.model).toBe("qwen3:7b");
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
