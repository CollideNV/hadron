import type { BackendModels, CRRun, CRRunDetail, ModelSettings, PromptTemplate, PromptTemplateDetail, RawChangeRequest } from "./types";

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

export async function getPipelineStatus(crId: string): Promise<CRRunDetail> {
  return fetchJSON<CRRunDetail>(`/pipeline/${crId}`);
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
): Promise<{ status: string; cr_id: string; overrides: Record<string, unknown> }> {
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
  return fetchJSON(`/pipeline/${crId}/conversation?key=${encodeURIComponent(key)}`);
}

export async function listPrompts(): Promise<PromptTemplate[]> {
  return fetchJSON<PromptTemplate[]>("/prompts");
}

export async function getPrompt(role: string): Promise<PromptTemplateDetail> {
  return fetchJSON<PromptTemplateDetail>(`/prompts/${encodeURIComponent(role)}`);
}

export async function updatePrompt(
  role: string,
  content: string,
): Promise<PromptTemplateDetail> {
  return fetchJSON(`/prompts/${encodeURIComponent(role)}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  });
}

export async function getModelSettings(): Promise<ModelSettings> {
  return fetchJSON<ModelSettings>("/settings/models");
}

export async function updateModelSettings(settings: ModelSettings): Promise<ModelSettings> {
  return fetchJSON<ModelSettings>("/settings/models", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export async function getAvailableBackends(): Promise<BackendModels[]> {
  return fetchJSON<BackendModels[]>("/settings/backends");
}

export async function getWorkerLogs(crId: string): Promise<string> {
  const res = await fetch(`${BASE}/pipeline/${crId}/logs`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.text();
}
