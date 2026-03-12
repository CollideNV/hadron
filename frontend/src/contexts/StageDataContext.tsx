import { createContext, useContext } from "react";
import type { PipelineEvent } from "../api/types";

interface StageData {
  crId: string;
  pipelineStatus: string;
  events: PipelineEvent[];
  toolCalls: PipelineEvent[];
  agentOutputs: PipelineEvent[];
  agentNudges: PipelineEvent[];
  testRuns: PipelineEvent[];
  findings: PipelineEvent[];
}

const StageDataContext = createContext<StageData | null>(null);

export function StageDataProvider({
  children,
  ...value
}: StageData & { children: React.ReactNode }) {
  return (
    <StageDataContext.Provider value={value}>
      {children}
    </StageDataContext.Provider>
  );
}

export function useStageData(): StageData {
  const ctx = useContext(StageDataContext);
  if (!ctx) throw new Error("useStageData must be used within StageDataProvider");
  return ctx;
}
