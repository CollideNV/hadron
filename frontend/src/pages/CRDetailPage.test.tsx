import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CRDetailPage from "./CRDetailPage";
import type { CRDetailState } from "../hooks/useCRDetail";
import type { EventStreamState } from "../hooks/useEventStream";

// Mock react-router
const mockCrId = "cr-123";
const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ crId: mockCrId }),
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...props }: { to: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={to} {...props}>{children}</a>
  ),
}));

// Mock useCRDetail
const mockUseCRDetail = vi.fn<() => CRDetailState>();
vi.mock("../hooks/useCRDetail", () => ({
  useCRDetail: () => mockUseCRDetail(),
}));

// Mock child components that are complex
vi.mock("../components/pipeline/StageTimeline", () => ({
  default: () => <div data-testid="stage-timeline" />,
}));
vi.mock("../components/logs/LogsPanel", () => ({
  default: () => <div data-testid="logs-panel" />,
}));

function makeStreamState(overrides: Partial<EventStreamState> = {}): EventStreamState {
  return {
    events: [],
    currentStage: "",
    completedStages: new Set(),
    stageData: new Map(),
    toolCalls: [],
    agentOutputs: [],
    agentNudges: [],
    testRuns: [],
    reviewFindings: [],
    costUsd: 0,
    status: "running",
    error: null,
    ...overrides,
  };
}

function makeCRDetailState(overrides: Partial<CRDetailState> = {}): CRDetailState {
  return {
    crRun: null,
    displayStatus: "running",
    title: "Test CR",
    stream: makeStreamState(),
    filterByStage: () => ({
      events: [],
      toolCalls: [],
      agentOutputs: [],
      agentNudges: [],
      testRuns: [],
      findings: [],
    }),
    ...overrides,
  };
}

beforeEach(() => {
  mockUseCRDetail.mockReturnValue(makeCRDetailState());
});

describe("CRDetailPage", () => {
  it("renders title and status", () => {
    render(<CRDetailPage />);
    expect(screen.getByText("Test CR")).toBeInTheDocument();
    expect(screen.getByText("cr-123")).toBeInTheDocument();
  });

  it("renders the EventLog in overview mode", () => {
    render(<CRDetailPage />);
    expect(screen.getByText(/pipeline stages/i)).toBeInTheDocument();
  });

  it("toggles logs panel", async () => {
    const user = userEvent.setup();
    render(<CRDetailPage />);

    expect(screen.queryByTestId("logs-panel")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /logs/i }));
    expect(screen.getByTestId("logs-panel")).toBeInTheDocument();
  });

  it("shows error banner when stream has error", () => {
    mockUseCRDetail.mockReturnValue(
      makeCRDetailState({
        stream: makeStreamState({ error: "Connection lost" }),
      }),
    );
    render(<CRDetailPage />);
    expect(screen.getByText("Connection lost")).toBeInTheDocument();
  });

  it("shows cost tracker", () => {
    mockUseCRDetail.mockReturnValue(
      makeCRDetailState({
        stream: makeStreamState({ costUsd: 1.234 }),
      }),
    );
    render(<CRDetailPage />);
    expect(screen.getByText("$1.2340")).toBeInTheDocument();
  });

  it("renders EventLog with waiting message for empty events", () => {
    render(<CRDetailPage />);
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument();
  });
});
