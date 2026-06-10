import type { ChatMessage } from "@/lib/types";
import { GuardrailBadges, IntentBadge } from "./Badges";
import { HeadsetIcon, SparkIcon, ThumbDownIcon, ThumbUpIcon } from "./Icons";

function Avatar({ role }: { role: "assistant" | "human-agent" }) {
  const isHuman = role === "human-agent";
  return (
    <div
      className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-white shadow-sm ${
        isHuman
          ? "bg-gradient-to-br from-orange-400 to-amber-500"
          : "bg-gradient-to-br from-brand-500 to-violet-500"
      }`}
    >
      {isHuman ? <HeadsetIcon className="h-4 w-4" /> : <SparkIcon className="h-4 w-4" />}
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce-dot"
          style={{ animationDelay: `${i * 150}ms` }}
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
    ? "bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-glow rounded-br-md"
    : isHuman
      ? "bg-amber-50 text-slate-800 ring-1 ring-amber-200/80 rounded-bl-md"
      : "bg-white text-slate-800 ring-1 ring-slate-200/80 shadow-soft rounded-bl-md";

  return (
    <div className={`flex animate-fade-in-up gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && <Avatar role={isHuman ? "human-agent" : "assistant"} />}

      <div className={`flex min-w-0 max-w-[82%] flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        {isHuman && (
          <span className="ml-1 text-[11px] font-semibold text-orange-600">Human agent</span>
        )}

        <div
          className={`whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${bubbleClass}`}
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
          <div className="flex flex-wrap items-center gap-1.5 pl-1">
            <IntentBadge intent={message.intent} />
            <GuardrailBadges blocked={message.blocked} escalated={message.escalated} />
            {canRate && (
              <span className="ml-0.5 flex items-center gap-0.5">
                <FeedbackButton
                  active={message.feedback === "up"}
                  disabled={!!message.feedback}
                  tone="up"
                  onClick={() => onFeedback(message, 1)}
                />
                <FeedbackButton
                  active={message.feedback === "down"}
                  disabled={!!message.feedback}
                  tone="down"
                  onClick={() => onFeedback(message, 0)}
                />
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FeedbackButton({
  active,
  disabled,
  tone,
  onClick,
}: {
  active: boolean;
  disabled: boolean;
  tone: "up" | "down";
  onClick: () => void;
}) {
  const activeColor = tone === "up" ? "text-emerald-600" : "text-rose-600";
  const hoverColor = tone === "up" ? "hover:text-emerald-600" : "hover:text-rose-600";
  return (
    <button
      type="button"
      aria-label={tone === "up" ? "Helpful" : "Not helpful"}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md p-1 transition ${
        active ? activeColor : `text-slate-400 ${hoverColor} disabled:hover:text-slate-300`
      }`}
    >
      {tone === "up" ? <ThumbUpIcon className="h-3.5 w-3.5" /> : <ThumbDownIcon className="h-3.5 w-3.5" />}
    </button>
  );
}
