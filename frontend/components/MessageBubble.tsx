import type { ChatMessage } from "@/lib/types";
import { GuardrailBadges, IntentBadge } from "./Badges";

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-blink rounded-full bg-slate-400"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

export default function MessageBubble({
  message,
  onFeedback,
}: {
  message: ChatMessage;
  onFeedback: (message: ChatMessage, score: 1 | 0) => void;
}) {
  const isUser = message.role === "user";
  const isHuman = message.role === "human-agent";
  const showMeta = !isUser && !message.pending;
  const canRate = showMeta && !!message.runId && !message.blocked;

  const bubbleClass = isUser
    ? "bg-brand-600 text-white"
    : isHuman
      ? "bg-orange-50 text-slate-800 ring-1 ring-orange-200"
      : "bg-white text-slate-800 ring-1 ring-slate-200";

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      {isHuman && (
        <span className="mb-1 ml-1 text-xs font-medium text-orange-600">Human agent</span>
      )}

      <div
        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed shadow-sm ${bubbleClass}`}
      >
        {message.pending && !message.content ? (
          message.escalated ? (
            <span className="text-slate-500">Connecting you to a human agent…</span>
          ) : (
            <TypingDots />
          )
        ) : (
          <span className={message.errored ? "text-rose-600" : undefined}>
            {message.content}
            {message.pending && <span className="ml-0.5 animate-blink">▋</span>}
          </span>
        )}
      </div>

      {showMeta && (message.intent || message.blocked || message.escalated || canRate) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-1">
          <IntentBadge intent={message.intent} />
          <GuardrailBadges blocked={message.blocked} escalated={message.escalated} />
          {canRate && (
            <span className="flex items-center gap-1">
              <button
                type="button"
                aria-label="Helpful"
                onClick={() => onFeedback(message, 1)}
                disabled={!!message.feedback}
                className={`rounded px-1.5 text-sm transition ${
                  message.feedback === "up"
                    ? "text-emerald-600"
                    : "text-slate-400 hover:text-emerald-600 disabled:hover:text-slate-400"
                }`}
              >
                ▲
              </button>
              <button
                type="button"
                aria-label="Not helpful"
                onClick={() => onFeedback(message, 0)}
                disabled={!!message.feedback}
                className={`rounded px-1.5 text-sm transition ${
                  message.feedback === "down"
                    ? "text-rose-600"
                    : "text-slate-400 hover:text-rose-600 disabled:hover:text-slate-400"
                }`}
              >
                ▼
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
