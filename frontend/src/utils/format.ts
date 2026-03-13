export function formatDuration(start: number, end: number): string {
  const secs = Math.round(end - start);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return `${mins}m ${rem}s`;
}

export function formatModelName(model: string): string {
  return model.replace("claude-", "").replace(/-\d{8}$/, "");
}

export function formatModelNameShort(model: string): string {
  return formatModelName(model).split("-")[0];
}

export function formatTokens(tokens: number): string {
  return `${(tokens / 1000).toFixed(1)}k`;
}

export function formatTokenPair(input: number, output: number): string {
  return `${formatTokens(input)}/${formatTokens(output)}`;
}

export function formatCost(usd: number, precision = 4): string {
  return `$${usd.toFixed(precision)}`;
}
