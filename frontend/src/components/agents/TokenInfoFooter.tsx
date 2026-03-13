import type { AgentSession } from "./types";
import { formatModelName, formatTokenPair, formatCost } from "../../utils/format";

interface TokenInfoFooterProps {
  session: AgentSession;
  tokenInfo: string;
}

export default function TokenInfoFooter({ session, tokenInfo }: TokenInfoFooterProps) {
  return (
    <div className="border-t border-border-subtle flex-shrink-0">
      {Object.keys(session.modelBreakdown).length > 0 && (
        <div className="px-3 pt-1.5 pb-0.5 space-y-0.5">
          {Object.entries(session.modelBreakdown).map(([model, stats]) => {
            const shortName = formatModelName(model);
            return (
              <div key={model} className="flex items-center gap-2 text-[10px]">
                <span className="font-mono text-text-muted w-20 truncate" title={model}>
                  {shortName}
                </span>
                <span className="text-text-dim">
                  {formatTokenPair(stats.input_tokens, stats.output_tokens)} tok
                </span>
                <span className="text-accent">
                  {formatCost(stats.cost_usd)}
                </span>
                {stats.throttle_count > 0 && (
                  <span className="text-status-error">
                    {stats.throttle_seconds.toFixed(0)}s throttled
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="px-3 py-1 text-[10px] text-text-dim text-right flex items-center justify-end gap-3">
        {session.throttleCount > 0 && (
          <span className="text-status-error">
            total: {session.throttleSeconds.toFixed(0)}s throttled
          </span>
        )}
        <span>{tokenInfo}</span>
      </div>
    </div>
  );
}
