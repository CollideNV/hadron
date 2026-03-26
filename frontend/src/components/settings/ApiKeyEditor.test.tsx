import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ApiKeyEditor from "./ApiKeyEditor";
import type { ApiKeyStatus } from "../../api/types";

const mockKeys: ApiKeyStatus[] = [
  { key_name: "anthropic_api_key", display_name: "Anthropic", is_configured: true, masked_value: "••••abcd", source: "database" },
  { key_name: "openai_api_key", display_name: "OpenAI", is_configured: true, masked_value: "••••efgh", source: "environment" },
  { key_name: "gemini_api_key", display_name: "Gemini", is_configured: false, masked_value: "", source: "none" },
];

vi.mock("../../api/client", () => ({
  getApiKeys: vi.fn(),
  setApiKey: vi.fn(),
  clearApiKey: vi.fn(),
}));

import { getApiKeys, setApiKey, clearApiKey } from "../../api/client";

beforeEach(() => {
  vi.mocked(getApiKeys).mockResolvedValue(mockKeys);
  vi.mocked(setApiKey).mockResolvedValue(mockKeys[0]);
  vi.mocked(clearApiKey).mockResolvedValue({ ...mockKeys[0], is_configured: false, masked_value: "", source: "none" });
});

describe("ApiKeyEditor", () => {
  it("renders all key rows after loading", async () => {
    render(<ApiKeyEditor />);
    await waitFor(() => {
      expect(screen.getByText("Anthropic")).toBeInTheDocument();
      expect(screen.getByText("OpenAI")).toBeInTheDocument();
      expect(screen.getByText("Gemini")).toBeInTheDocument();
    });
  });

  it("shows masked value for configured keys", async () => {
    render(<ApiKeyEditor />);
    await waitFor(() => {
      expect(screen.getByTestId("masked-anthropic_api_key")).toHaveTextContent("••••abcd");
    });
  });

  it("shows 'Not configured' for unconfigured keys", async () => {
    render(<ApiKeyEditor />);
    await waitFor(() => {
      expect(screen.getByText("Not configured")).toBeInTheDocument();
    });
  });

  it("shows source badges", async () => {
    render(<ApiKeyEditor />);
    await waitFor(() => {
      expect(screen.getByText("Database")).toBeInTheDocument();
      expect(screen.getByText("Environment")).toBeInTheDocument();
      expect(screen.getByText("Not set")).toBeInTheDocument();
    });
  });

  it("shows Clear button only for database-sourced keys", async () => {
    render(<ApiKeyEditor />);
    await waitFor(() => {
      expect(screen.getByTestId("clear-anthropic_api_key")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("clear-openai_api_key")).not.toBeInTheDocument();
    expect(screen.queryByTestId("clear-gemini_api_key")).not.toBeInTheDocument();
  });

  it("opens input when Set Key is clicked", async () => {
    const user = userEvent.setup();
    render(<ApiKeyEditor />);
    await waitFor(() => screen.getByTestId("set-gemini_api_key"));

    await user.click(screen.getByTestId("set-gemini_api_key"));
    expect(screen.getByTestId("input-gemini_api_key")).toBeInTheDocument();
  });

  it("calls setApiKey on save", async () => {
    const user = userEvent.setup();
    render(<ApiKeyEditor />);
    await waitFor(() => screen.getByTestId("set-gemini_api_key"));

    await user.click(screen.getByTestId("set-gemini_api_key"));
    await user.type(screen.getByTestId("input-gemini_api_key"), "sk-new-key");
    await user.click(screen.getByTestId("save-gemini_api_key"));

    await waitFor(() => {
      expect(setApiKey).toHaveBeenCalledWith("gemini_api_key", "sk-new-key");
    });
  });

  it("calls clearApiKey on clear", async () => {
    const user = userEvent.setup();
    render(<ApiKeyEditor />);
    await waitFor(() => screen.getByTestId("clear-anthropic_api_key"));

    await user.click(screen.getByTestId("clear-anthropic_api_key"));

    await waitFor(() => {
      expect(clearApiKey).toHaveBeenCalledWith("anthropic_api_key");
    });
  });
});
