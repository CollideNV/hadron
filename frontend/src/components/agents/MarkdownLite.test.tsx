import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MarkdownLite, { renderInline } from "./MarkdownLite";

describe("MarkdownLite", () => {
  it("renders plain text", () => {
    render(<MarkdownLite text="Hello world" />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders inline code", () => {
    render(<MarkdownLite text="Use `foo()` here" />);
    expect(screen.getByText("foo()")).toBeInTheDocument();
    expect(screen.getByText("foo()").tagName).toBe("CODE");
  });

  it("renders bold text", () => {
    render(<MarkdownLite text="This is **bold** text" />);
    const bold = screen.getByText("bold");
    expect(bold.tagName).toBe("STRONG");
  });

  it("renders code blocks", () => {
    const text = "before\n```\nconst x = 1;\n```\nafter";
    render(<MarkdownLite text={text} />);
    expect(screen.getByText("const x = 1;")).toBeInTheDocument();
    expect(screen.getByText("const x = 1;").tagName).toBe("PRE");
  });

  it("handles unclosed code blocks", () => {
    const text = "```\nconst x = 1;";
    render(<MarkdownLite text={text} />);
    expect(screen.getByText("const x = 1;")).toBeInTheDocument();
    expect(screen.getByText("const x = 1;").tagName).toBe("PRE");
  });
});

describe("renderInline", () => {
  it("returns plain text as-is", () => {
    const result = renderInline("hello");
    expect(result).toBe("hello");
  });

  it("handles mixed inline code and bold", () => {
    const result = renderInline("use `foo` and **bold**");
    expect(Array.isArray(result)).toBe(true);
  });
});
