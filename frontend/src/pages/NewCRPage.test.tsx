import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import NewCRPage from "./NewCRPage";

const mockTriggerPipeline = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../api/client", () => ({
  triggerPipeline: (...args: unknown[]) => mockTriggerPipeline(...args),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

beforeEach(() => {
  mockTriggerPipeline.mockReset();
  mockNavigate.mockReset();
});

describe("NewCRPage", () => {
  it("renders heading and form", () => {
    render(
      <MemoryRouter>
        <NewCRPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("New Change Request")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /trigger pipeline/i }),
    ).toBeInTheDocument();
  });

  it("submits and navigates to CR detail page", async () => {
    mockTriggerPipeline.mockResolvedValue({
      cr_id: "cr-new-123",
      status: "pending",
    });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <NewCRPage />
      </MemoryRouter>,
    );

    await user.type(
      screen.getByPlaceholderText(/health check/i),
      "My Feature",
    );
    await user.type(
      screen.getByPlaceholderText(/describe the change/i),
      "Add a health endpoint",
    );
    await user.click(
      screen.getByRole("button", { name: /trigger pipeline/i }),
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/cr/cr-new-123");
    });
  });

  it("shows error on submission failure", async () => {
    mockTriggerPipeline.mockRejectedValue(new Error("500: server error"));
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <NewCRPage />
      </MemoryRouter>,
    );

    await user.type(
      screen.getByPlaceholderText(/health check/i),
      "My Feature",
    );
    await user.type(
      screen.getByPlaceholderText(/describe the change/i),
      "Details",
    );
    await user.click(
      screen.getByRole("button", { name: /trigger pipeline/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("500: server error")).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
