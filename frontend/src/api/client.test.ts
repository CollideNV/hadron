import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  listPipelines,
  getPipelineStatus,
  triggerPipeline,
  sendIntervention,
  resumePipeline,
  sendNudge,
  getConversation,
  getWorkerLogs,
} from "./client";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  };
}

function textResponse(text: string, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe("listPipelines", () => {
  it("fetches /api/pipeline/list", async () => {
    const runs = [{ cr_id: "cr-1", status: "running" }];
    mockFetch.mockResolvedValue(jsonResponse(runs));

    const result = await listPipelines();

    expect(result).toEqual(runs);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/pipeline/list",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
  });
});

describe("getPipelineStatus", () => {
  it("fetches pipeline by cr_id", async () => {
    const detail = { cr_id: "cr-1", repos: [] };
    mockFetch.mockResolvedValue(jsonResponse(detail));

    const result = await getPipelineStatus("cr-1");
    expect(result).toEqual(detail);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/pipeline/cr-1",
      expect.anything(),
    );
  });
});

describe("triggerPipeline", () => {
  it("POSTs CR payload", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ cr_id: "cr-new", status: "pending" }),
    );

    const result = await triggerPipeline({
      title: "Test",
      description: "Desc",
      repo_urls: ["https://github.com/org/repo"],
    });

    expect(result.cr_id).toBe("cr-new");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/pipeline/trigger",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("sendIntervention", () => {
  it("POSTs intervention instructions", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "intervention_set" }));

    const result = await sendIntervention("cr-1", "fix tests");
    expect(result.status).toBe("intervention_set");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.instructions).toBe("fix tests");
  });
});

describe("resumePipeline", () => {
  it("POSTs resume with overrides", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: "resumed", cr_id: "cr-1", overrides: {} }),
    );

    const result = await resumePipeline("cr-1", { max_retries: 3 });
    expect(result.status).toBe("resumed");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.state_overrides).toEqual({ max_retries: 3 });
  });
});

describe("sendNudge", () => {
  it("POSTs nudge with role and message", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "nudge_set" }));

    await sendNudge("cr-1", "tdd_developer", "focus on edge cases");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.role).toBe("tdd_developer");
    expect(body.message).toBe("focus on edge cases");
  });
});

describe("getConversation", () => {
  it("fetches conversation by key", async () => {
    const conv = [{ role: "user", content: "hello" }];
    mockFetch.mockResolvedValue(jsonResponse(conv));

    const result = await getConversation("cr-1", "hadron:cr:cr-1:conv:tdd:repo:123");
    expect(result).toEqual(conv);
    expect(mockFetch.mock.calls[0][0]).toContain("conversation");
    expect(mockFetch.mock.calls[0][0]).toContain(encodeURIComponent("hadron:cr:cr-1:conv:tdd:repo:123"));
  });
});

describe("getWorkerLogs", () => {
  it("fetches logs as text", async () => {
    mockFetch.mockResolvedValue(textResponse("line 1\nline 2\n"));

    const result = await getWorkerLogs("cr-1");
    expect(result).toBe("line 1\nline 2\n");
  });

  it("throws on error response", async () => {
    mockFetch.mockResolvedValue(textResponse("not found", 404));

    await expect(getWorkerLogs("cr-missing")).rejects.toThrow("404");
  });
});

describe("fetchJSON error handling", () => {
  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve("Internal Server Error"),
    });

    await expect(listPipelines()).rejects.toThrow("500: Internal Server Error");
  });
});
