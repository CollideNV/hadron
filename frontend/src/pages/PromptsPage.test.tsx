import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PromptsPage from "./PromptsPage";

const mockListPrompts = vi.fn();
const mockGetPrompt = vi.fn();
const mockUpdatePrompt = vi.fn();

vi.mock("../api/client", () => ({
  listPrompts: (...args: unknown[]) => mockListPrompts(...args),
  getPrompt: (...args: unknown[]) => mockGetPrompt(...args),
  updatePrompt: (...args: unknown[]) => mockUpdatePrompt(...args),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <PromptsPage />
    </MemoryRouter>,
  );
}

const TEMPLATES = [
  { role: "spec_writer", description: "Behaviour Specification Writer", version: 1, updated_at: "2026-03-16T00:00:00+00:00" },
  { role: "explorer", description: "Codebase Explorer", version: 2, updated_at: "2026-03-15T00:00:00+00:00" },
];

const DETAIL = {
  role: "spec_writer",
  content: "# Spec Writer prompt",
  description: "Behaviour Specification Writer",
  version: 1,
  updated_at: "2026-03-16T00:00:00+00:00",
};

describe("PromptsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListPrompts.mockResolvedValue(TEMPLATES);
    mockGetPrompt.mockResolvedValue(DETAIL);
    mockUpdatePrompt.mockResolvedValue({ ...DETAIL, version: 2, content: "# Updated" });
  });

  it("renders list of prompt templates", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Spec Writer")).toBeInTheDocument());
    expect(screen.getByText("Explorer")).toBeInTheDocument();
  });

  it("shows placeholder when no prompt selected", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/select a prompt/i)).toBeInTheDocument());
  });

  it("loads prompt detail on click", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText("Spec Writer")).toBeInTheDocument());

    await user.click(screen.getByText("Spec Writer"));
    await waitFor(() => expect(mockGetPrompt).toHaveBeenCalledWith("spec_writer"));
  });

  it("save button disabled when not dirty", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText("Spec Writer")).toBeInTheDocument());

    await user.click(screen.getByText("Spec Writer"));
    await waitFor(() => expect(screen.getByRole("button", { name: /save/i })).toBeDisabled());
  });

  it("save triggers update and refreshes", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText("Spec Writer")).toBeInTheDocument());

    await user.click(screen.getByText("Spec Writer"));
    await waitFor(() => expect(screen.getByRole("button", { name: /save/i })).toBeInTheDocument());

    // Type in textarea to make dirty
    const textarea = document.querySelector("textarea")!;
    await user.click(textarea);
    await user.type(textarea, " extra");

    await waitFor(() => expect(screen.getByRole("button", { name: /save/i })).toBeEnabled());

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(mockUpdatePrompt).toHaveBeenCalledWith("spec_writer", expect.any(String)));
  });
});
