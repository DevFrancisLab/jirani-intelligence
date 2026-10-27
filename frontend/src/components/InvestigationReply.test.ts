import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { InvestigationBrief } from "../api/client";
import { InvestigationReply } from "./InvestigationReply";

function brief(
  overrides: Partial<InvestigationBrief> = {},
): InvestigationBrief {
  return {
    question: "Any housing permits?",
    findings: [],
    supporting_records: [],
    uncertainty: [],
    evidence_gaps: [],
    next_steps: [],
    layer_status: [],
    contract: null,
    clarification: null,
    prior_memories: [],
    nightshift_handoff: null,
    nightshift_meta: null,
    ...overrides,
  };
}

function render(next: InvestigationBrief): string {
  return renderToStaticMarkup(
    createElement(InvestigationReply, { brief: next }),
  );
}

describe("InvestigationReply", () => {
  it("asks clarification conversationally without internal labels", () => {
    const html = render(
      brief({
        clarification: { question: "Which neighbourhood should I focus on?" },
        layer_status: [
          { name: "Scout Intent", state: "clarification", detail: "needed" },
        ],
      }),
    );
    expect(html).toContain("Which neighbourhood should I focus on?");
    expect(html).not.toContain("Scout Intent");
    expect(html).not.toContain("not_called");
  });

  it("shows the honest empty-records message", () => {
    const html = render(
      brief({
        evidence_gaps: ["No rows"],
        next_steps: ["Connect a planning registry source."],
      }),
    );
    expect(html).toMatch(/couldn(?:'|&#x27;)t find supporting records/);
    expect(html).toContain("Connect a planning registry source.");
  });

  it("renders retrieved evidence with source identifiers", () => {
    const html = render(
      brief({
        findings: [
          {
            statement: "A permit mentions housing.",
            record_ids: ["permit-9"],
            source: "housing_permits",
          },
        ],
        supporting_records: [
          {
            record_id: "permit-9",
            source: "housing_permits",
            kind: "row",
            fields: { status: "approved" },
            statement: "approved",
          },
        ],
      }),
    );
    expect(html).toContain("Evidence");
    expect(html).toContain("housing_permits");
    expect(html).toContain("permit-9");
    expect(html).toContain("Retrieved evidence");
    expect(html).toContain("approved");
  });

  it("hides hackathon and nvidia routing warnings from chat", () => {
    const html = render(
      brief({
        findings: [
          {
            statement: "One record matched.",
            record_ids: ["r1"],
            source: "permits",
          },
        ],
        supporting_records: [
          {
            record_id: "r1",
            source: "permits",
            kind: "row",
            fields: { id: "1" },
            statement: "row",
          },
        ],
        uncertainty: [
          "A label that contains NVIDIA is not proof of NVIDIA routing.",
          "Stage-2 organizers note omitted.",
        ],
        next_steps: ["Review the retrieved permit record."],
      }),
    );
    expect(html).not.toContain("NVIDIA");
    expect(html).not.toContain("organizers");
    expect(html).not.toContain("Stage-2");
    expect(html).toContain("Review the retrieved permit record.");
  });
});
