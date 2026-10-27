type Props = {
  open: boolean;
  recent: string[];
  activeView: "chat" | "settings";
  onNewInvestigation: () => void;
  onSelectRecent: (question: string) => void;
  onOpenSettings: () => void;
  onOpenChat: () => void;
  onClose: () => void;
};

export function Sidebar({
  open,
  recent,
  activeView,
  onNewInvestigation,
  onSelectRecent,
  onOpenSettings,
  onOpenChat,
  onClose,
}: Props) {
  return (
    <>
      {open && <div className="backdrop" onClick={onClose} aria-hidden="true" />}
      <aside
        className={`sidebar ${open ? "open" : ""}`}
        aria-label="Jirani Intelligence navigation"
      >
        <div className="brand">Jirani Intelligence</div>
        <button type="button" className="new-investigation" onClick={onNewInvestigation}>
          New investigation
        </button>

        <div className="sidebar-section-label">Recent</div>
        <div className="history-list">
          {recent.length === 0 ? (
            <div className="history-empty">
              No saved investigations yet. Ask a question to begin.
            </div>
          ) : (
            recent.map((item) => (
              <button
                key={item}
                type="button"
                className="history-item"
                onClick={() => onSelectRecent(item)}
              >
                {item.length > 72 ? `${item.slice(0, 72)}…` : item}
              </button>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <button
            type="button"
            className={`sidebar-link ${activeView === "chat" ? "active" : ""}`}
            onClick={onOpenChat}
          >
            Conversation
          </button>
          <button
            type="button"
            className={`sidebar-link ${activeView === "settings" ? "active" : ""}`}
            onClick={onOpenSettings}
          >
            Settings
          </button>
        </div>
      </aside>
    </>
  );
}
