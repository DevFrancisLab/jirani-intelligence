import { FormEvent, useEffect, useState } from "react";
import {
  InvestigationBrief,
  PublicStatus,
  QueryResult,
  api,
} from "./api/client";

type LoadState = "idle" | "loading" | "error" | "ready";

export default function App() {
  const [status, setStatus] = useState<PublicStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [question, setQuestion] = useState("");
  const [brief, setBrief] = useState<InvestigationBrief | null>(null);
  const [probe, setProbe] = useState<QueryResult | null>(null);
  const [sample, setSample] = useState<QueryResult | null>(null);
  const [connections, setConnections] = useState<Record<
    string,
    { state: string; detail: string }
  > | null>(null);
  const [memories, setMemories] = useState<InvestigationBrief["prior_memories"]>(
    [],
  );
  const [cockpitAnswer, setCockpitAnswer] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [boot, setBoot] = useState<LoadState>("loading");

  useEffect(() => {
    void refreshStatus();
  }, []);

  async function refreshStatus() {
    setBoot("loading");
    try {
      const [nextStatus, memory] = await Promise.all([
        api.status(),
        api.memory(),
      ]);
      setStatus(nextStatus);
      setMemories(memory.memories);
      setStatusError("");
      setBoot("ready");
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Backend unavailable");
      setBoot("error");
    }
  }

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  function onInvestigate(event: FormEvent) {
    event.preventDefault();
    void run("investigate", async () => {
      const result = await api.investigate(question);
      setBrief(result);
      const memory = await api.memory();
      setMemories(memory.memories);
      const nextStatus = await api.status();
      setStatus(nextStatus);
    });
  }

  return (
    <main>
      <p className="eyebrow">
        Open Agent Hackathon 2026 · Track 01 · Solving Fragmented Intelligence
      </p>
      <h1>Jirani Intelligence</h1>
      <p className="lede">
        Ask one urban-planning question. Scout Intent signs a contract, Zetaris
        retrieves registered records, H-MEM recalls prior notes, and Meterless
        Nightshift reasons only over retrieved evidence when configured. The
        React UI talks to Django over HTTP. Secrets never leave the backend.
      </p>

      {boot === "error" && (
        <div className="error">
          Backend unavailable: {statusError}. Start Django on port 8000.
        </div>
      )}

      {status && (
        <section className="panel" style={{ marginTop: "1.25rem" }}>
          <div className="section-label">Configuration</div>
          <div className="row">
            <span className="pill">
              Zetaris · {status.zetaris_configured ? "configured" : "not ready"}
            </span>
            <span className="pill">
              Sources · {status.registered_source_count}
            </span>
            <span className="pill">
              Nightshift ·{" "}
              {status.nightshift_configured
                ? "HTTP ready"
                : status.meterless_enabled
                  ? "incomplete"
                  : "cockpit handoff"}
            </span>
            <span className="pill">
              Model · {status.nightshift_model || "not set"}
            </span>
            <span className="pill">H-MEM · {status.hmem_memory_count}</span>
          </div>
          <p className="caption">
            Intended label: {status.intended_model_label}. A label that contains
            NVIDIA is not proof of NVIDIA routing.
          </p>
          {status.registered_source_count === 0 && (
            <div className="info">
              Zetaris can run, and no planning sources are registered. Set
              ZETARIS_SOURCES on the backend. Do not register NY_TAXI, TPCDS, or
              TPCH as planning evidence.
            </div>
          )}
        </section>
      )}

      <div className="section-label">Zetaris</div>
      <section className="panel">
        <p className="caption">
          Queries use the verified UI-proxy route. NY_TAXI.taxi_trips is New York
          sample data, not evidence about Nairobi or Kilimani.
        </p>
        <div className="row">
          <button
            disabled={!!busy}
            onClick={() =>
              void run("probe", async () => setProbe(await api.zetarisProbe()))
            }
          >
            {busy === "probe" ? "Running…" : "Run SELECT 1"}
          </button>
          <button
            disabled={!!busy}
            onClick={() =>
              void run("sample", async () =>
                setSample(await api.zetarisTaxiSample()),
              )
            }
          >
            {busy === "sample" ? "Reading…" : "Read NY_TAXI.taxi_trips sample"}
          </button>
          <button
            disabled={!!busy}
            onClick={() =>
              void run("connections", async () =>
                setConnections(await api.connections()),
              )
            }
          >
            {busy === "connections" ? "Checking…" : "Check connections"}
          </button>
        </div>
        {probe && <QueryBlock title="SELECT 1" result={probe} />}
        {sample && (
          <>
            <p className="caption">
              These rows are New York sample data from NY_TAXI.taxi_trips. They
              are not evidence about Nairobi or Kilimani.
            </p>
            <QueryBlock title="NY_TAXI.taxi_trips" result={sample} />
          </>
        )}
        {connections && (
          <div>
            <div className="section-label">Connection check</div>
            {Object.entries(connections).map(([name, item]) => (
              <div key={name}>
                <span className="pill">
                  <strong>{name}</strong> · {item.state}
                </span>
                <p className="caption">{item.detail}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="section-label">H-MEM</div>
      <section className="panel">
        <p className="caption">
          Local investigation memory with provenance. Standing labels separate
          retrieved evidence from AI interpretations.
        </p>
        {memories.length === 0 ? (
          <p>No memories yet.</p>
        ) : (
          memories.map((item, index) => (
            <div key={`${item.source}-${index}`}>
              <p>{item.content.slice(0, 280)}</p>
              <p className="caption">
                {item.standing} · {item.provenance?.origin} · source{" "}
                {item.source}
              </p>
            </div>
          ))
        )}
      </section>

      <div className="section-label">Investigation</div>
      <section className="panel">
        <form onSubmit={onInvestigate}>
          <label htmlFor="question">Investigation question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Which registered records mention housing permits?"
          />
          <div className="row">
            <button className="primary" disabled={!!busy || !question.trim()}>
              {busy === "investigate" ? "Running…" : "Run investigation"}
            </button>
          </div>
        </form>
        {error && <div className="error">{error}</div>}
        {notice && <div className="success">{notice}</div>}
        {brief && (
          <BriefView
            brief={brief}
            cockpitAnswer={cockpitAnswer}
            setCockpitAnswer={setCockpitAnswer}
            busy={busy}
            onRecord={() =>
              void run("cockpit", async () => {
                await api.recordCockpitAnswer({
                  question: brief.question,
                  answer: cockpitAnswer,
                  record_ids: brief.supporting_records.map(
                    (record) => record.record_id,
                  ),
                });
                setNotice(
                  "Recorded as an AI interpretation. It is not a retrieved fact and it is not a finding.",
                );
                setCockpitAnswer("");
                const memory = await api.memory();
                setMemories(memory.memories);
              })
            }
          />
        )}
      </section>

      <p className="sidebar-note">
        Nothing on this page is planning evidence until a query returns rows. A
        connection check that fails stays failed.
      </p>
    </main>
  );
}

function QueryBlock({ title, result }: { title: string; result: QueryResult }) {
  const duration =
    result.duration_ms == null ? "n/a" : `${result.duration_ms} ms`;
  return (
    <div>
      <span className="pill">
        <strong>{title}</strong> · {result.status} · {duration}
      </span>
      <p className="caption">{result.detail}</p>
      {result.rows.length > 0 && <RowsTable rows={result.rows} />}
    </div>
  );
}

function RowsTable({ rows }: { rows: Record<string, string>[] }) {
  const columns = Object.keys(rows[0] || {});
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{row[column]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BriefView({
  brief,
  cockpitAnswer,
  setCockpitAnswer,
  onRecord,
  busy,
}: {
  brief: InvestigationBrief;
  cockpitAnswer: string;
  setCockpitAnswer: (value: string) => void;
  onRecord: () => void;
  busy: string | null;
}) {
  return (
    <div>
      <div className="section-label">Layer status</div>
      {brief.layer_status.map((layer) => (
        <div key={layer.name}>
          <span className="pill">
            <strong>{layer.name}</strong> · {layer.state}
          </span>
          <p className="caption">{layer.detail}</p>
        </div>
      ))}

      {brief.clarification?.question && (
        <div className="info">{brief.clarification.question}</div>
      )}

      <div className="section-label">Findings</div>
      {brief.findings.length === 0 ? (
        <p>
          No findings. The desk does not fill this section when no cited
          reasoning was accepted.
        </p>
      ) : (
        brief.findings.map((finding, index) => (
          <div key={index}>
            <p>{finding.statement}</p>
            <p className="caption">
              Cites {finding.record_ids.join(", ")} · {finding.source}
            </p>
          </div>
        ))
      )}

      <div className="section-label">Supporting records</div>
      {brief.supporting_records.length === 0 ? (
        <p>No records were retrieved.</p>
      ) : (
        <RowsTable
          rows={brief.supporting_records.map((record) => ({
            record_id: record.record_id,
            source: record.source,
            kind: record.kind,
            ...record.fields,
          }))}
        />
      )}

      <BulletList title="Uncertainty" items={brief.uncertainty} />
      <BulletList title="Evidence gaps" items={brief.evidence_gaps} />
      <BulletList title="Recommended next steps" items={brief.next_steps} />

      <div className="section-label">Prior H-MEM context</div>
      {brief.prior_memories.length === 0 ? (
        <p>No prior memory scored at or above 0.35 for this question.</p>
      ) : (
        brief.prior_memories.map((memory, index) => (
          <div key={index}>
            <p>{memory.content}</p>
            <p className="caption">
              {memory.standing} · {memory.provenance?.origin} · source{" "}
              {memory.source}
              {memory.score != null ? ` · score ${memory.score}` : ""}
            </p>
          </div>
        ))
      )}

      {brief.nightshift_meta && (
        <>
          <div className="section-label">Nightshift provider metadata</div>
          <p className="caption">
            Configured model id and any response model field. A NVIDIA label is
            not proof of NVIDIA routing.
          </p>
          <pre className="prompt">{JSON.stringify(brief.nightshift_meta, null, 2)}</pre>
        </>
      )}

      {brief.nightshift_handoff && (
        <>
          <div className="section-label">Meterless Web cockpit</div>
          <div className="warning">{brief.nightshift_handoff.edition_note}</div>
          <p className="caption">{brief.nightshift_handoff.url}</p>
          <ul>
            {brief.nightshift_handoff.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
          <pre className="prompt">{brief.nightshift_handoff.prompt}</pre>
          <label htmlFor="cockpit">Paste the Morning answer</label>
          <textarea
            id="cockpit"
            value={cockpitAnswer}
            onChange={(event) => setCockpitAnswer(event.target.value)}
          />
          <div className="row">
            <button disabled={!!busy || !cockpitAnswer.trim()} onClick={onRecord}>
              {busy === "cockpit" ? "Recording…" : "Record cockpit answer"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function BulletList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="section-label">{title}</div>
      {items.length === 0 ? (
        <p>None.</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
