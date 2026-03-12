import { describe, it, expect } from "vitest";
import { formatDuration, formatModelName, formatModelNameShort } from "./format";

describe("formatDuration", () => {
  it("formats seconds only when under 60", () => {
    expect(formatDuration(100, 145)).toBe("45s");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(100, 225)).toBe("2m 5s");
  });

  it("handles exact minute boundary", () => {
    expect(formatDuration(0, 120)).toBe("2m 0s");
  });

  it("handles zero duration", () => {
    expect(formatDuration(100, 100)).toBe("0s");
  });

  it("rounds fractional seconds", () => {
    expect(formatDuration(0, 1.7)).toBe("2s");
  });
});

describe("formatModelName", () => {
  it("strips claude- prefix and date suffix", () => {
    expect(formatModelName("claude-3-5-sonnet-20241022")).toBe("3-5-sonnet");
  });

  it("strips claude- prefix without date suffix", () => {
    expect(formatModelName("claude-3-opus")).toBe("3-opus");
  });

  it("handles model with only date suffix", () => {
    expect(formatModelName("claude-haiku-20240307")).toBe("haiku");
  });

  it("returns as-is for non-claude model names", () => {
    expect(formatModelName("gpt-4")).toBe("gpt-4");
  });

  it("handles empty string", () => {
    expect(formatModelName("")).toBe("");
  });
});

describe("formatModelNameShort", () => {
  it("returns first segment after stripping", () => {
    expect(formatModelNameShort("claude-3-5-sonnet-20241022")).toBe("3");
  });

  it("handles single-segment result", () => {
    expect(formatModelNameShort("claude-haiku-20240307")).toBe("haiku");
  });

  it("handles empty string", () => {
    expect(formatModelNameShort("")).toBe("");
  });
});
