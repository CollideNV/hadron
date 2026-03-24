import { useState } from "react";
import { useAnalyticsSummary, useAnalyticsCost } from "../hooks/useAnalytics";
import KPICards from "../components/analytics/KPICards";
import StatusChart from "../components/analytics/StatusChart";
import DailyTrendChart from "../components/analytics/DailyTrendChart";
import StageDurationChart from "../components/analytics/StageDurationChart";
import CostBreakdownChart from "../components/analytics/CostBreakdownChart";
import type { CostTab } from "../components/analytics/CostBreakdownChart";

export default function AnalyticsPage() {
  const { data: summary, loading: summaryLoading, error } = useAnalyticsSummary();
  const [costTab, setCostTab] = useState<CostTab>("stage");
  const { data: costData, loading: costLoading } = useAnalyticsCost(costTab);

  if (summaryLoading && !summary) {
    return <div className="max-w-6xl mx-auto py-8 px-4 text-text-dim">Loading analytics...</div>;
  }

  if (!summary) {
    return <div className="max-w-6xl mx-auto py-8 px-4 text-text-dim">Failed to load analytics.</div>;
  }

  return (
    <div className="max-w-6xl mx-auto py-8 px-4 space-y-6">
      <h1 className="text-lg font-semibold text-text">Analytics</h1>

      {error && (
        <div className="bg-status-failed/10 text-status-failed px-4 py-3 rounded-lg text-sm mb-4 border border-status-failed/20">
          {error}
        </div>
      )}

      <KPICards summary={summary} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatusChart statusCounts={summary.status_counts} />
        <DailyTrendChart dailyStats={summary.daily_stats} />
      </div>

      <StageDurationChart stageDurations={summary.stage_durations} />

      <CostBreakdownChart
        tab={costTab}
        onTabChange={setCostTab}
        data={costData}
        loading={costLoading}
      />
    </div>
  );
}
