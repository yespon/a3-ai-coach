interface TypingIndicatorProps {
  label: string; // "正在解析附件…" | "正在思考…"
}

export default function TypingIndicator({ label }: TypingIndicatorProps) {
  return (
    <div className="typing-indicator" aria-live="polite">
      <span className="typing-dot" />
      <span className="typing-label">{label}</span>
    </div>
  );
}
