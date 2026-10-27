import { KeyboardEvent, useEffect, useRef } from "react";

type Props = {
  value: string;
  disabled?: boolean;
  loading?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export function Composer({
  value,
  disabled,
  loading,
  placeholder = "Ask an urban-planning question...",
  onChange,
  onSubmit,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!disabled && !loading && value.trim()) {
        onSubmit();
      }
    }
  }

  const canSend = Boolean(value.trim()) && !disabled && !loading;

  return (
    <div className="composer-dock">
      <form
        className="composer-shell"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) onSubmit();
        }}
      >
        <textarea
          ref={ref}
          value={value}
          rows={1}
          placeholder={placeholder}
          disabled={disabled || loading}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          aria-label="Investigation question"
        />
        <button
          type="submit"
          className="send-button"
          disabled={!canSend}
          aria-label={loading ? "Sending" : "Send"}
        >
          {loading ? "…" : "↑"}
        </button>
      </form>
      <p className="composer-hint">
        Enter to send · Shift+Enter for a new line
      </p>
    </div>
  );
}
