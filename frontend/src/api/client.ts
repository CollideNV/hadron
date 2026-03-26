import type { AnalyticsCost, AnalyticsSummary, ApiKeyStatus, AuditLogPage, BackendTemplate, CRRun, CRRunDetail, PipelineDefaults, PromptTemplate, PromptTemplateDetail, RawChangeRequest } from "./types";

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

export interface ListPipelinesParams {
  search?: string;
  status?: string;
  sort?: string;
}

export async function listPipelines(params: ListPipelinesParams = {}): Promise<CRRun[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set("search", params.search);
  if (params.status) qs.set("status", params.status);
  if (params.sort) qs.set("sort", params.sort);
  const query = qs.toString();
  return fetchJSON<CRRun[]>(`/pipeline/list${query ? `?${query}` : ""}`);
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

export async function getTemplates(): Promise<BackendTemplate[]> {
  return fetchJSON<BackendTemplate[]>("/settings/templates");
}

export async function updateTemplates(templates: BackendTemplate[]): Promise<BackendTemplate[]> {
  return fetchJSON<BackendTemplate[]>("/settings/templates", {
    method: "PUT",
    body: JSON.stringify(templates),
  });
}

export async function getDefaultTemplate(): Promise<{ slug: string }> {
  return fetchJSON<{ slug: string }>("/settings/templates/default");
}

export async function setDefaultTemplate(slug: string): Promise<{ slug: string }> {
  return fetchJSON<{ slug: string }>("/settings/templates/default", {
    method: "PUT",
    body: JSON.stringify({ slug }),
  });
}

export async function getPipelineDefaults(): Promise<PipelineDefaults> {
  return fetchJSON<PipelineDefaults>("/settings/pipeline-defaults");
}

export async function updatePipelineDefaults(defaults: PipelineDefaults): Promise<PipelineDefaults> {
  return fetchJSON<PipelineDefaults>("/settings/pipeline-defaults", {
    method: "PUT",
    body: JSON.stringify(defaults),
  });
}

export async function getAuditLog(params: { page?: number; page_size?: number; action?: string } = {}): Promise<AuditLogPage> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.action) qs.set("action", params.action);
  const query = qs.toString();
  return fetchJSON<AuditLogPage>(`/audit-log${query ? `?${query}` : ""}`);
}

export async function getWorkerLogs(crId: string): Promise<string> {
  const res = await fetch(`${BASE}/pipeline/${crId}/logs`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.text();
}

export async function getApiKeys(): Promise<ApiKeyStatus[]> {
  return fetchJSON<ApiKeyStatus[]>("/settings/api-keys");
}

export async function setApiKey(keyName: string, value: string): Promise<ApiKeyStatus> {
  return fetchJSON<ApiKeyStatus>("/settings/api-keys", {
    method: "PUT",
    body: JSON.stringify({ key_name: keyName, value }),
  });
}

export async function clearApiKey(keyName: string): Promise<ApiKeyStatus> {
  return fetchJSON<ApiKeyStatus>(`/settings/api-keys/${encodeURIComponent(keyName)}`, {
    method: "DELETE",
  });
}

export async function getAnalyticsSummary(days = 30): Promise<AnalyticsSummary> {
  return fetchJSON<AnalyticsSummary>(`/analytics/summary?days=${days}`);
}

export async function getAnalyticsCost(groupBy = "stage"): Promise<AnalyticsCost> {
  return fetchJSON<AnalyticsCost>(`/analytics/cost?group_by=${encodeURIComponent(groupBy)}`);
}
