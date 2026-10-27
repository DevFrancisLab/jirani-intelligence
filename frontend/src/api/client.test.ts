import { describe, expect, it } from "vitest";

describe("frontend public config", () => {
  it("does not embed provider secret env names in the client module source contract", async () => {
    const source = await import("./client");
    const exported = JSON.stringify(Object.keys(source));
    expect(exported).not.toContain("ZETARIS_API_KEY");
    expect(exported).not.toContain("METERLESS_API_KEY");
  });
});
