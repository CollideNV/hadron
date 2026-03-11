import { describe, it, expect, vi, beforeEach } from "vitest";
import { connectEventStream } from "./sse";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: ((e: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (e: MessageEvent) => void) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(listener);
  }

  close() {
    this.closed = true;
  }

  // Test helper: simulate an event
  emit(type: string, data: string) {
    for (const listener of this.listeners[type] || []) {
      listener({ data } as MessageEvent);
    }
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  // @ts-expect-error - mocking EventSource
  globalThis.EventSource = MockEventSource;
});

describe("connectEventStream", () => {
  it("creates EventSource with correct URL", () => {
    connectEventStream("cr-1", vi.fn());
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe(
      "/api/events/stream?cr_id=cr-1",
    );
  });

  it("registers listeners for all event types", () => {
    connectEventStream("cr-1", vi.fn());
    const source = MockEventSource.instances[0];
    expect(Object.keys(source.listeners)).toContain("pipeline_started");
    expect(Object.keys(source.listeners)).toContain("stage_entered");
    expect(Object.keys(source.listeners)).toContain("agent_tool_call");
    expect(Object.keys(source.listeners)).toContain("cost_update");
  });

  it("calls onEvent with parsed data", () => {
    const onEvent = vi.fn();
    connectEventStream("cr-1", onEvent);
    const source = MockEventSource.instances[0];

    const event = { cr_id: "cr-1", event_type: "stage_entered", stage: "intake", data: {}, timestamp: 0 };
    source.emit("stage_entered", JSON.stringify(event));

    expect(onEvent).toHaveBeenCalledWith(event);
  });

  it("ignores parse errors", () => {
    const onEvent = vi.fn();
    connectEventStream("cr-1", onEvent);
    const source = MockEventSource.instances[0];

    source.emit("stage_entered", "not json{{{");
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("calls onError when source errors", () => {
    const onError = vi.fn();
    connectEventStream("cr-1", vi.fn(), onError);
    const source = MockEventSource.instances[0];

    const errorEvent = new Event("error");
    source.onerror!(errorEvent);
    expect(onError).toHaveBeenCalledWith(errorEvent);
  });

  it("returns close function", () => {
    const close = connectEventStream("cr-1", vi.fn());
    const source = MockEventSource.instances[0];

    expect(source.closed).toBe(false);
    close();
    expect(source.closed).toBe(true);
  });
});
