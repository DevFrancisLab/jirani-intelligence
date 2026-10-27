import type { InvestigationBrief } from "../api/client";

export type ConversationTurn = {
  id: string;
  question: string;
  brief: InvestigationBrief | null;
  error?: string;
  pending?: boolean;
};

export function isRetrievedEvidence(source: string): boolean {
  return source !== "nightshift_ai_interpretation" && source !== "nightshift";
}

export function buildSummary(brief: InvestigationBrief): string | null {
  if (brief.clarification?.question) {
    return null;
  }
  if (brief.findings.length > 0) {
    return brief.findings.map((item) => item.statement).join(" ");
  }
  if (
    brief.supporting_records.length === 0 &&
    (brief.evidence_gaps.length > 0 || brief.uncertainty.length > 0)
  ) {
    return null;
  }
  return null;
}

export function hasNoSupportingRecords(brief: InvestigationBrief): boolean {
  return (
    !brief.clarification &&
    brief.findings.length === 0 &&
    brief.supporting_records.length === 0
  );
}

export function recentInvestigationTitles(
  memories: InvestigationBrief["prior_memories"],
): string[] {
  const seen = new Set<string>();
  const titles: string[] = [];
  for (const memory of memories) {
    const isQuestion =
      memory.source === "user" ||
      memory.provenance?.origin === "chat_message" ||
      memory.provenance?.label === "Investigation question";
    if (!isQuestion) continue;
    const title = memory.content.trim();
    if (!title || seen.has(title)) continue;
    seen.add(title);
    titles.push(title);
    if (titles.length >= 8) break;
  }
  return titles;
}

export function humanConnectionLabel(state: string): string {
  switch (state) {
    case "ok":
    case "online":
    case "local_ready":
    case "local_store":
      return "Ready";
    case "disabled":
    case "not_configured":
      return "Not configured";
    case "hotspot_offline":
      return "Offline";
    case "unauthorized":
      return "Unauthorized";
    case "rate_limited":
      return "Rate limited";
    case "browser_handoff":
      return "Browser handoff available";
    default:
      return state.replace(/_/g, " ");
  }
}
