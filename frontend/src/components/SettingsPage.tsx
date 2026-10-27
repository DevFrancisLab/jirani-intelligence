import { useState } from "react";
import type { PublicStatus, QueryResult } from "../api/client";
import { api } from "../api/client";
import { humanConnectionLabel } from "../lib/brief";

type Props = {
  status: PublicStatus | null;
  statusError: string;
  onRefreshStatus: () => Promise<void>;
};

export function SettingsPage({ status, statusError, onRefreshStatus }: Props) {
  const [connections, setConnections] = useState<Record<
    string,
    { state: string; detail: string }
  > | null>(null);
  const [probe, setProbe] = useState<QueryResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="settings">
      <h1>Settings</h1>
      <p className="settings-lead">
        System status for administrators and developers. This page can show
        connection diagnostics. It never displays secrets, and it does not treat
        sample data as planning evidence.
      </p>

      {statusError && <div className="error-banner">{statusError}</div>}
      {error && <div className="error-banner">{error}</div>}

      <section className="settings-card">
        <h2>System status</h2>
        {!status ? (
          <p className="status-note">Status is unavailable until the API responds.</p>
        ) : (
          <div className="status-grid">
            <div className="status-row">
              <span>Data connection configured</span>
              <span>{status.zetaris_configured ? "Yes" : "No"}</span>
            </div>
            <div className="status-row">
              <span>Registered planning sources</span>
              <span>{status.registered_source_count}</span>
            </div>
            <div className="status-row">
              <span>AI provider enabled</span>
              <span>{status.meterless_enabled ? "Yes" : "No"}</span>
            </div>
            <div className="status-row">
              <span>AI provider ready</span>
              <span>{status.nightshift_configured ? "Configured" : "Not ready"}</span>
            </div>
            <div className="status-row">
              <span>Saved investigation notes</span>
              <span>{status.hmem_memory_count}</span>
            </div>
          </div>
        )}
        {status?.registered_sources?.length ? (
          <p className="status-note" style={{ marginTop: "0.75rem" }}>
            Sources: {status.registered_sources.join(", ")}
          </p>
        ) : (
          <p className="status-note" style={{ marginTop: "0.75rem" }}>
            No planning sources are registered yet. Sample databases are not used
            as city planning evidence.
          </p>
        )}
        <div className="settings-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={!!busy}
            onClick={() => void run("refresh", onRefreshStatus)}
          >
            {busy === "refresh" ? "Refreshing…" : "Refresh status"}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!!busy}
            onClick={() =>
              void run("connections", async () =>
                setConnections(await api.connections()),
              )
            }
          >
            {busy === "connections" ? "Checking…" : "Check connections"}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!!busy}
            onClick={() =>
              void run("probe", async () => setProbe(await api.zetarisProbe()))
            }
          >
            {busy === "probe" ? "Running…" : "Test data connection"}
          </button>
        </div>
      </section>

      {connections && (
        <section className="settings-card">
          <h2>Connection details</h2>
          <div className="status-grid">
            {Object.entries(connections).map(([name, item]) => (
              <div className="status-row" key={name}>
                <span>{friendlyServiceName(name)}</span>
                <span>
                  {humanConnectionLabel(item.state)}
                  {item.detail ? ` — ${sanitizeDetail(item.detail)}` : ""}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {probe && (
        <section className="settings-card">
          <h2>Data connection test</h2>
          <p className="status-note">
            Result: {probe.ok ? "Succeeded" : "Did not succeed"} · {probe.status}
            {probe.duration_ms != null ? ` · ${probe.duration_ms} ms` : ""}
          </p>
          <p className="status-note">{sanitizeDetail(probe.detail)}</p>
        </section>
      )}
    </div>
  );
}

function friendlyServiceName(name: string): string {
  if (name === "Zetaris") return "Data connection";
  if (name === "Meterless Nightshift") return "AI provider";
  if (name === "H-MEM") return "Investigation memory";
  if (name === "Scout Intent") return "Routing";
  return name;
}

function sanitizeDetail(detail: string): string {
  return detail
    .replace(/https?:\/\/\S+/g, "[endpoint]")
    .replace(/Bearer\s+\S+/gi, "[redacted]")
    .replace(/nsk_[A-Za-z0-9_-]+/g, "[redacted]");
}
