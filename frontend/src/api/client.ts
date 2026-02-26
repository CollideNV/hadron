import type {
  CRRun,
  RawChangeRequest,
  ModelConfig,
  ProviderConfig,
} from "./types";

const BASE = "/api";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export async function listPipelines(): Promise<CRRun[]> {
  return fetchJSON<CRRun[]>("/pipeline/list");
}

export async function listModels(): Promise<ModelConfig[]> {
  const data = await fetchJSON<{ models: ModelConfig[] }>("/config/models");
  return data.models;
}

export async function listProviders(): Promise<ProviderConfig[]> {
  const data = await fetchJSON<{ providers: ProviderConfig[] }>(
    "/config/providers",
  );
  return data.providers;
}

export async function getPipelineStatus(crId: string): Promise<CRRun> {
  return fetchJSON<CRRun>(`/pipeline/${crId}`);
}

export async function triggerPipeline(
  cr: RawChangeRequest,
): Promise<{ cr_id: string; status: string }> {
  return fetchJSON("/pipeline/trigger", {
    method: "POST",
    body: JSON.stringify(cr),
  });
}

export async function sendIntervention(
  crId: string,
  instructions: string,
): Promise<{ status: string }> {
  return fetchJSON(`/pipeline/${crId}/intervene`, {
    method: "POST",
    body: JSON.stringify({ instructions }),
  });
}

export async function resumePipeline(
  crId: string,
  stateOverrides: Record<string, unknown> = {},
): Promise<{
  status: string;
  cr_id: string;
  overrides: Record<string, unknown>;
}> {
  return fetchJSON(`/pipeline/${crId}/resume`, {
    method: "POST",
    body: JSON.stringify({ state_overrides: stateOverrides }),
  });
}

export async function sendNudge(
  crId: string,
  role: string,
  message: string,
): Promise<{ status: string }> {
  return fetchJSON(`/pipeline/${crId}/nudge`, {
    method: "POST",
    body: JSON.stringify({ role, message }),
  });
}

export async function getConversation(
  crId: string,
  key: string,
): Promise<Record<string, unknown>[]> {
  return fetchJSON(
    `/pipeline/${crId}/conversation?key=${encodeURIComponent(key)}`,
  );
}

export async function getWorkerLogs(crId: string): Promise<string> {
  const res = await fetch(`${BASE}/pipeline/${crId}/logs`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.text();
}
