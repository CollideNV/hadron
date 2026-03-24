import "@testing-library/jest-dom/vitest";

// Mock EventSource for tests that use SSE (e.g. useGlobalActivity, useEventStream)
if (typeof globalThis.EventSource === "undefined") {
  class MockEventSource {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 2;
    readyState = 0;
    onopen: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: (() => void) | null = null;
    close() { this.readyState = 2; }
    addEventListener() {}
    removeEventListener() {}
    dispatchEvent() { return false; }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).EventSource = MockEventSource;
}
