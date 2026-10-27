import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));

function read(relativePath: string): string {
  return readFileSync(join(root, relativePath), "utf8");
}

describe("visible UI copy", () => {
  it("removes hackathon branding and developer SQL samples from the main app", () => {
    const app = read("App.tsx");
    const sidebar = read("components/Sidebar.tsx");
    const settings = read("components/SettingsPage.tsx");
    const reply = read("components/InvestigationReply.tsx");
    const combined = `${app}\n${sidebar}\n${settings}\n${reply}`;

    expect(combined).not.toMatch(/Open Agent Hackathon/i);
    expect(combined).not.toMatch(/Track 01/i);
    expect(combined).not.toMatch(/Run SELECT 1/);
    expect(combined).not.toMatch(/NY_TAXI\.taxi_trips sample/);
    expect(app).not.toContain("Scout Intent");
    expect(app).toContain("What would you like to understand about your city?");
    expect(sidebar).toContain("New investigation");
    expect(settings).toContain("System status");
  });
});
