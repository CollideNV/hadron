import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KeyRow, keyForBackend } from "./ApiKeyEditor";
import type { ApiKeyStatus } from "../../api/types";

vi.mock("../../api/client", () => ({
  getApiKeys: vi.fn(),
  setApiKey: vi.fn(),
  clearApiKey: vi.fn(),
}));

import { setApiKey, clearApiKey } from "../../api/client";

const dbKey: ApiKeyStatus = {
  key_name: "anthropic_api_key",
  display_name: "Anthropic",
  is_configured: true,
  masked_value: "••••abcd",
  source: "database",
};

const envKey: ApiKeyStatus = {
  key_name: "openai_api_key",
  display_name: "OpenAI",
  is_configured: true,
  masked_value: "••••efgh",
  source: "environment",
};

const unsetKey: ApiKeyStatus = {
  key_name: "gemini_api_key",
  display_name: "Gemini",
  is_configured: false,
  masked_value: "",
  source: "none",
};

beforeEach(() => {
  vi.mocked(setApiKey).mockResolvedValue(dbKey);
  vi.mocked(clearApiKey).mockResolvedValue({ ...dbKey, is_configured: false, masked_value: "", source: "none" });
});

describe("KeyRow", () => {
  it("shows masked value for configured key", () => {
    render(<KeyRow status={dbKey} onUpdated={vi.fn()} />);
    expect(screen.getByTestId("masked-anthropic_api_key")).toHaveTextContent("••••abcd");
  });

  it("shows 'Not configured' for unset key", () => {
    render(<KeyRow status={unsetKey} onUpdated={vi.fn()} />);
    expect(screen.getByText("Not configured")).toBeInTheDocument();
  });

  it("shows source badges", () => {
    const { rerender } = render(<KeyRow status={dbKey} onUpdated={vi.fn()} />);
    expect(screen.getByText("Database")).toBeInTheDocument();

    rerender(<KeyRow status={envKey} onUpdated={vi.fn()} />);
    expect(screen.getByText("Environment")).toBeInTheDocument();

    rerender(<KeyRow status={unsetKey} onUpdated={vi.fn()} />);
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });

  it("shows Clear button only for database-sourced keys", () => {
    const { rerender } = render(<KeyRow status={dbKey} onUpdated={vi.fn()} />);
    expect(screen.getByTestId("clear-anthropic_api_key")).toBeInTheDocument();

    rerender(<KeyRow status={envKey} onUpdated={vi.fn()} />);
    expect(screen.queryByTestId("clear-openai_api_key")).not.toBeInTheDocument();
  });

  it("opens input when Set Key is clicked", async () => {
    const user = userEvent.setup();
    render(<KeyRow status={unsetKey} onUpdated={vi.fn()} />);

    await user.click(screen.getByTestId("set-gemini_api_key"));
    expect(screen.getByTestId("input-gemini_api_key")).toBeInTheDocument();
  });

  it("calls setApiKey on save", async () => {
    const user = userEvent.setup();
    render(<KeyRow status={unsetKey} onUpdated={vi.fn()} />);

    await user.click(screen.getByTestId("set-gemini_api_key"));
    await user.type(screen.getByTestId("input-gemini_api_key"), "sk-new-key");
    await user.click(screen.getByTestId("save-gemini_api_key"));

    await waitFor(() => {
      expect(setApiKey).toHaveBeenCalledWith("gemini_api_key", "sk-new-key");
    });
  });

  it("calls clearApiKey on clear", async () => {
    const user = userEvent.setup();
    render(<KeyRow status={dbKey} onUpdated={vi.fn()} />);

    await user.click(screen.getByTestId("clear-anthropic_api_key"));

    await waitFor(() => {
      expect(clearApiKey).toHaveBeenCalledWith("anthropic_api_key");
    });
  });
});

describe("keyForBackend", () => {
  const keys = [dbKey, envKey, unsetKey];

  it("maps claude to anthropic_api_key", () => {
    expect(keyForBackend(keys, "claude")?.key_name).toBe("anthropic_api_key");
  });

  it("maps openai to openai_api_key", () => {
    expect(keyForBackend(keys, "openai")?.key_name).toBe("openai_api_key");
  });

  it("maps gemini to gemini_api_key", () => {
    expect(keyForBackend(keys, "gemini")?.key_name).toBe("gemini_api_key");
  });

  it("returns undefined for opencode", () => {
    expect(keyForBackend(keys, "opencode")).toBeUndefined();
  });
});
