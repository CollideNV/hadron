import { useMemo } from "react";
import type { PipelineEvent, AgentCompletedData, ModelBreakdownEntry } from "../api/types";
import { STAGE_META } from "../components/pipeline/stageTimelineConstants";

export interface StageCost {
  stage: string;
  label: string;
  costUsd: number;
  inputTokens: number;
  outputTokens: number;
  agentCount: number;
}

export interface ModelCost {
  model: string;
  costUsd: number;
  inputTokens: number;
  outputTokens: number;
  apiCalls: number;
}

export interface CostTimelinePoint {
  timestamp: number;
  cumulativeCostUsd: number;
}

export interface CostBreakdown {
  totalCostUsd: number;
  byStage: StageCost[];
  byModel: ModelCost[];
  timeline: CostTimelinePoint[];
}

/** Extracts the base stage name (e.g. "review" from "review:security_reviewer") */
function baseStage(stage: string): string {
  const colon = stage.indexOf(":");
  return colon === -1 ? stage : stage.substring(0, colon);
}

export function useCostBreakdown(events: PipelineEvent[]): CostBreakdown {
  return useMemo(() => {
    const stageMap = new Map<string, { costUsd: number; inputTokens: number; outputTokens: number; agentCount: number }>();
    const modelMap = new Map<string, { costUsd: number; inputTokens: number; outputTokens: number; apiCalls: number }>();
    const timeline: CostTimelinePoint[] = [];
    let cumulative = 0;

    for (const event of events) {
      if (event.event_type !== "agent_completed") continue;

      const d = event.data as AgentCompletedData;
      const stage = baseStage(event.stage);

      // Per-stage accumulation
      const existing = stageMap.get(stage);
      if (existing) {
        existing.costUsd += d.cost_usd;
        existing.inputTokens += d.input_tokens;
        existing.outputTokens += d.output_tokens;
        existing.agentCount += 1;
      } else {
        stageMap.set(stage, {
          costUsd: d.cost_usd,
          inputTokens: d.input_tokens,
          outputTokens: d.output_tokens,
          agentCount: 1,
        });
      }

      // Per-model accumulation
      if (d.model_breakdown) {
        for (const [model, stats] of Object.entries(d.model_breakdown) as [string, ModelBreakdownEntry][]) {
          const m = modelMap.get(model);
          if (m) {
            m.costUsd += stats.cost_usd;
            m.inputTokens += stats.input_tokens;
            m.outputTokens += stats.output_tokens;
            m.apiCalls += stats.api_calls;
          } else {
            modelMap.set(model, {
              costUsd: stats.cost_usd,
              inputTokens: stats.input_tokens,
              outputTokens: stats.output_tokens,
              apiCalls: stats.api_calls,
            });
          }
        }
      } else if (d.model) {
        // Fallback: single model, no breakdown
        const m = modelMap.get(d.model);
        if (m) {
          m.costUsd += d.cost_usd;
          m.inputTokens += d.input_tokens;
          m.outputTokens += d.output_tokens;
          m.apiCalls += 1;
        } else {
          modelMap.set(d.model, {
            costUsd: d.cost_usd,
            inputTokens: d.input_tokens,
            outputTokens: d.output_tokens,
            apiCalls: 1,
          });
        }
      }

      // Timeline
      cumulative += d.cost_usd;
      timeline.push({ timestamp: event.timestamp, cumulativeCostUsd: cumulative });
    }

    const byStage = Array.from(stageMap.entries())
      .map(([stage, data]) => ({
        stage,
        label: (STAGE_META as Record<string, { label: string }>)[stage]?.label || stage,
        ...data,
      }))
      .sort((a, b) => b.costUsd - a.costUsd);

    const byModel = Array.from(modelMap.entries())
      .map(([model, data]) => ({ model, ...data }))
      .sort((a, b) => b.costUsd - a.costUsd);

    return {
      totalCostUsd: cumulative,
      byStage,
      byModel,
      timeline,
    };
  }, [events]);
}
