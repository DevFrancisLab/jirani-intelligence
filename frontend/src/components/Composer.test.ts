import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("renders the urban-planning placeholder and disabled send when empty", () => {
    const html = renderToStaticMarkup(
      createElement(Composer, {
        value: "",
        onChange: () => undefined,
        onSubmit: () => undefined,
      }),
    );
    expect(html).toContain("Ask an urban-planning question...");
    expect(html).toContain("disabled");
    expect(html).not.toContain("hackathon");
  });

  it("enables send when there is text and not loading", () => {
    const html = renderToStaticMarkup(
      createElement(Composer, {
        value: "What records mention zoning?",
        onChange: () => undefined,
        onSubmit: () => undefined,
      }),
    );
    expect(html).toContain("What records mention zoning?");
    expect(html).not.toMatch(/send-button" disabled/);
  });

  it("shows a loading send state", () => {
    const html = renderToStaticMarkup(
      createElement(Composer, {
        value: "Hello",
        loading: true,
        onChange: () => undefined,
        onSubmit: () => undefined,
      }),
    );
    expect(html).toContain('aria-label="Sending"');
    expect(html).toContain("disabled");
  });
});
