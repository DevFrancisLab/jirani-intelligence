import { useEffect, useRef, useState } from "react";
import { PublicStatus, api } from "./api/client";
import { Composer } from "./components/Composer";
import { InvestigationReply } from "./components/InvestigationReply";
import { SettingsPage } from "./components/SettingsPage";
import { Sidebar } from "./components/Sidebar";
import {
  ConversationTurn,
  recentInvestigationTitles,
} from "./lib/brief";

const EXAMPLE_PROMPTS = [
  "What records are available about housing permits?",
  "Which registered sources contain zoning information?",
  "What evidence is available about development applications?",
];

type View = "chat" | "settings";

export default function App() {
  const [view, setView] = useState<View>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [status, setStatus] = useState<PublicStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [sending, setSending] = useState(false);
  const threadEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refreshBootstrap();
  }, []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, sending]);

  async function refreshBootstrap() {
    try {
      const [nextStatus, memory] = await Promise.all([
        api.status(),
        api.memory(),
      ]);
      setStatus(nextStatus);
      setRecent(recentInvestigationTitles(memory.memories));
      setStatusError("");
    } catch (err) {
      setStatusError(
        err instanceof Error ? err.message : "Backend unavailable",
      );
    }
  }

  function startNewInvestigation() {
    setTurns([]);
    setDraft("");
    setView("chat");
    setSidebarOpen(false);
  }

  function useRecent(question: string) {
    setDraft(question);
    setView("chat");
    setSidebarOpen(false);
  }

  async function submitQuestion(raw: string) {
    const question = raw.trim();
    if (!question || sending) return;

    const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setDraft("");
    setSending(true);
    setTurns((prev) => [
      ...prev,
      { id: turnId, question, brief: null, pending: true },
    ]);

    try {
      const brief = await api.investigate(question);
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === turnId
            ? { ...turn, brief, pending: false }
            : turn,
        ),
      );
      try {
        const memory = await api.memory();
        setRecent(recentInvestigationTitles(memory.memories));
        const nextStatus = await api.status();
        setStatus(nextStatus);
      } catch {
        // Conversation reply already succeeded; sidebar refresh can wait.
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Investigation request failed";
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === turnId
            ? { ...turn, pending: false, error: message, brief: null }
            : turn,
        ),
      );
    } finally {
      setSending(false);
    }
  }

  const showWelcome = turns.length === 0 && view === "chat";

  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        recent={recent}
        activeView={view}
        onNewInvestigation={startNewInvestigation}
        onSelectRecent={useRecent}
        onOpenSettings={() => {
          setView("settings");
          setSidebarOpen(false);
        }}
        onOpenChat={() => {
          setView("chat");
          setSidebarOpen(false);
        }}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-button"
            aria-label="Open navigation"
            onClick={() => setSidebarOpen(true)}
          >
            Menu
          </button>
          <strong>Jirani Intelligence</strong>
        </header>

        <div className="content">
          {view === "settings" ? (
            <SettingsPage
              status={status}
              statusError={statusError}
              onRefreshStatus={refreshBootstrap}
            />
          ) : showWelcome ? (
            <>
              <div className="welcome">
                <h1>What would you like to understand about your city?</h1>
                <p>
                  Investigate urban development using available records and
                  evidence.
                </p>
                <div className="suggestions">
                  {EXAMPLE_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="suggestion"
                      onClick={() => setDraft(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
                {statusError && (
                  <div className="error-banner" style={{ marginTop: "1.25rem" }}>
                    The investigation service is unavailable right now.{" "}
                    {statusError}
                  </div>
                )}
              </div>
              <Composer
                value={draft}
                loading={sending}
                disabled={!!statusError && !status}
                onChange={setDraft}
                onSubmit={() => void submitQuestion(draft)}
              />
            </>
          ) : (
            <>
              <div className="thread" aria-live="polite">
                <div className="thread-inner">
                  {turns.map((turn) => (
                    <TurnView key={turn.id} turn={turn} />
                  ))}
                  <div ref={threadEndRef} />
                </div>
              </div>
              <Composer
                value={draft}
                loading={sending}
                onChange={setDraft}
                onSubmit={() => void submitQuestion(draft)}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: ConversationTurn }) {
  return (
    <div className="message-group">
      <div className="message user">
        <div className="message-label">You</div>
        <div className="bubble">{turn.question}</div>
      </div>
      <div className="message assistant">
        <div className="message-label">Jirani Intelligence</div>
        <div className="bubble">
          {turn.pending && (
            <p className="status-note loading-dots">Investigating</p>
          )}
          {turn.error && (
            <div className="error-banner" role="alert">
              {friendlyError(turn.error)}
            </div>
          )}
          {turn.brief && <InvestigationReply brief={turn.brief} />}
        </div>
      </div>
    </div>
  );
}

function friendlyError(message: string): string {
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return "Could not reach the investigation service. Check that it is running and try again.";
  }
  if (/HTTP 5\d\d/.test(message)) {
    return "The investigation service had a problem. Please try again shortly.";
  }
  return message
    .replace(/ZETARIS_[A-Z_]+/g, "data connection settings")
    .replace(/METERLESS_[A-Z_]+/g, "AI provider settings");
}
