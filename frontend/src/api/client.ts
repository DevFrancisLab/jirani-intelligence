const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: text.slice(0, 400) };
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "error" in body
        ? String((body as { error: unknown }).error)
        : body && typeof body === "object" && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export type PublicStatus = {
  zetaris_configured: boolean;
  registered_sources: string[];
  registered_source_count: number;
  meterless_enabled: boolean;
  nightshift_configured: boolean;
  nightshift_model: string | null;
  intended_model_label: string;
  nvidia_label_is_not_proof: boolean;
  hmem_memory_count: number;
  warnings: string[];
  ui_origin: string | null;
  zetaris_api_key_set: boolean;
  nightshift_api_key_set: boolean;
};

export type QueryResult = {
  status: string;
  detail: string;
  rows: Record<string, string>[];
  duration_ms: number | null;
  statement: string;
  http_status: number | null;
  ok: boolean;
};

export type InvestigationBrief = {
  question: string;
  findings: { statement: string; record_ids: string[]; source: string }[];
  supporting_records: {
    record_id: string;
    source: string;
    kind: string;
    fields: Record<string, string>;
    statement: string;
  }[];
  uncertainty: string[];
  evidence_gaps: string[];
  next_steps: string[];
  layer_status: { name: string; state: string; detail: string }[];
  contract: Record<string, unknown> | null;
  clarification: { question?: string } | null;
  prior_memories: {
    content: string;
    standing: string;
    source: string;
    score?: number;
    provenance: { origin?: string; label?: string; refs?: string[] };
  }[];
  nightshift_handoff: {
    url: string;
    steps: string[];
    prompt: string;
    edition_note: string;
    api_call: boolean;
  } | null;
  nightshift_meta: Record<string, unknown> | null;
};

export const api = {
  health: () => request<{ status: string }>("/api/health/"),
  status: () => request<PublicStatus>("/api/status/"),
  connections: () =>
    request<Record<string, { state: string; detail: string }>>("/api/connections/", {
      method: "POST",
      body: "{}",
    }),
  zetarisProbe: () =>
    request<QueryResult>("/api/zetaris/probe/", { method: "POST", body: "{}" }),
  zetarisTaxiSample: () =>
    request<QueryResult>("/api/zetaris/sample/taxi-trips/", {
      method: "POST",
      body: "{}",
    }),
  investigate: (question: string) =>
    request<InvestigationBrief>("/api/investigations/", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  memory: () =>
    request<{ memories: InvestigationBrief["prior_memories"]; count: number }>(
      "/api/memory/",
    ),
  recordCockpitAnswer: (payload: {
    question: string;
    answer: string;
    record_ids: string[];
  }) =>
    request<{ recorded: { content: string; standing: string; source: string } }>(
      "/api/nightshift/cockpit-answer/",
      { method: "POST", body: JSON.stringify(payload) },
    ),
};
