import { describe, expect, it } from "vitest";
import type { InvestigationBrief } from "../api/client";
import {
  buildSummary,
  hasNoSupportingRecords,
  isRetrievedEvidence,
  recentInvestigationTitles,
} from "./brief";

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

describe("brief helpers", () => {
  it("treats nightshift sources as interpretation, not retrieved evidence", () => {
    expect(isRetrievedEvidence("permits_registry")).toBe(true);
    expect(isRetrievedEvidence("nightshift")).toBe(false);
    expect(isRetrievedEvidence("nightshift_ai_interpretation")).toBe(false);
  });

  it("builds a summary from findings when present", () => {
    const result = buildSummary(
      brief({
        findings: [
          {
            statement: "One permit record mentions Kilimani.",
            record_ids: ["r1"],
            source: "permits",
          },
        ],
      }),
    );
    expect(result).toContain("Kilimani");
  });

  it("returns no summary for clarification-only briefs", () => {
    expect(
      buildSummary(
        brief({
          clarification: { question: "Which neighbourhood should I check?" },
        }),
      ),
    ).toBeNull();
  });

  it("detects empty evidence honestly", () => {
    expect(
      hasNoSupportingRecords(
        brief({
          evidence_gaps: ["No registered sources returned rows."],
          next_steps: ["Register planning sources."],
        }),
      ),
    ).toBe(true);
    expect(
      hasNoSupportingRecords(
        brief({
          supporting_records: [
            {
              record_id: "r1",
              source: "permits",
              kind: "row",
              fields: { id: "1" },
              statement: "row",
            },
          ],
        }),
      ),
    ).toBe(false);
  });

  it("lists recent titles only from persisted user questions", () => {
    const titles = recentInvestigationTitles([
      {
        content: "What records mention housing permits?",
        standing: "unverified_note",
        source: "user",
        provenance: { origin: "chat_message", label: "Investigation question" },
      },
      {
        content: "AI interpretation of taxi sample",
        standing: "ai_interpretation",
        source: "nightshift",
        provenance: { origin: "cockpit", label: "AI interpretation" },
      },
      {
        content: "What records mention housing permits?",
        standing: "unverified_note",
        source: "user",
        provenance: { origin: "chat_message", label: "Investigation question" },
      },
    ]);
    expect(titles).toEqual(["What records mention housing permits?"]);
  });
});
