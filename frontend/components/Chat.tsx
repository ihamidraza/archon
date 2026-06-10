"use client";

import { useEffect, useRef, useState } from "react";
import { chat, fetchHealth, resume, sendFeedback } from "@/lib/api";
import type { ChatMessage, HealthStatus, SSEEvent } from "@/lib/types";
import { HealthDot } from "./Badges";
import MessageBubble from "./MessageBubble";

type Status = "idle" | "streaming" | "awaiting_human";

const SUGGESTIONS = [
  "What is your refund policy for monthly plans?",
  "I get a 500 error when exporting a large dataset.",
  "How do I enable SAML SSO for my workspace?",
  "How much does the Pro plan cost per month?",
];

let counter = 0;
const nextId = () => `m${Date.now()}-${counter++}`;

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [input, setInput] = useState("");
  const [humanInput, setHumanInput] = useState("");
  const [escalationReason, setEscalationReason] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchHealth().then(setHealth);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const patch = (id: string, fields: Partial<ChatMessage>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...fields } : m)));

  const appendToken = (id: string, text: string) =>
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + text } : m)),
    );

  const handler = (replyId: string) => (event: SSEEvent) => {
    switch (event.type) {
      case "session":
        setThreadId(event.thread_id);
        break;
      case "token":
        appendToken(replyId, event.content);
        break;
      case "interrupt":
        setEscalationReason(event.reason);
        setStatus("awaiting_human");
        patch(replyId, {
          pending: false,
          escalated: true,
          content: "This needs a person — a support agent will reply below.",
        });
        break;
      case "done":
        patch(replyId, {
          pending: false,
          intent: event.intent,
          blocked: event.blocked,
          escalated: event.escalated,
          runId: event.run_id,
        });
        setStatus("idle");
        break;
      case "error":
        patch(replyId, {
          pending: false,
          errored: true,
          content: event.detail || "Something went wrong.",
        });
        setStatus("idle");
        break;
    }
  };

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || status !== "idle") return;

    const replyId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", content: trimmed },
      { id: replyId, role: "assistant", content: "", pending: true },
    ]);
    setInput("");
    setStatus("streaming");

    try {
      await chat(trimmed, threadId, handler(replyId));
    } finally {
      setStatus((s) => (s === "streaming" ? "idle" : s));
      // Safety net: if the stream ended without a terminal event, stop the cursor.
      setMessages((prev) =>
        prev.map((m) =>
          m.id === replyId && m.pending && !m.escalated ? { ...m, pending: false } : m,
        ),
      );
    }
  }

  async function sendHumanReply() {
    const trimmed = humanInput.trim();
    if (!trimmed || !threadId) return;

    const replyId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: replyId, role: "human-agent", content: "", pending: true },
    ]);
    setHumanInput("");
    setEscalationReason(null);
    setStatus("streaming");

    try {
      await resume(threadId, trimmed, handler(replyId));
    } finally {
      setStatus((s) => (s === "streaming" ? "idle" : s));
    }
  }

  async function onFeedback(message: ChatMessage, score: 1 | 0) {
    if (!message.runId || message.feedback) return;
    patch(message.id, { feedback: score === 1 ? "up" : "down" });
    await sendFeedback(message.runId, score);
  }

  function newChat() {
    setMessages([]);
    setThreadId(null);
    setStatus("idle");
    setEscalationReason(null);
    setHumanInput("");
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white/80 px-5 py-3 backdrop-blur">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Archon</h1>
          <p className="text-xs text-slate-500">Nimbus customer support</p>
        </div>
        <div className="flex items-center gap-4">
          <HealthDot health={health} />
          <button
            type="button"
            onClick={newChat}
            className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
          >
            New chat
          </button>
        </div>
      </header>

      <div className="scroll-area flex-1 space-y-4 overflow-y-auto px-5 py-6">
        {messages.length === 0 ? (
          <EmptyState onPick={send} />
        ) : (
          messages.map((m) => (
            <MessageBubble key={m.id} message={m} onFeedback={onFeedback} />
          ))
        )}
        <div ref={endRef} />
      </div>

      {status === "awaiting_human" ? (
        <HumanPanel
          reason={escalationReason}
          value={humanInput}
          onChange={setHumanInput}
          onSend={sendHumanReply}
        />
      ) : (
        <Composer
          value={input}
          onChange={setInput}
          onSend={() => send(input)}
          disabled={status === "streaming"}
        />
      )}
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto mt-10 max-w-md text-center">
      <h2 className="text-base font-semibold text-slate-700">How can I help?</h2>
      <p className="mt-1 text-sm text-slate-500">
        Ask about billing, technical issues, your account, or our plans.
      </p>
      <div className="mt-5 grid gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-600 shadow-sm transition hover:border-brand-500 hover:text-slate-900"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
}) {
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-3">
      <div className="flex items-end gap-2">
        <textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Message Archon…"
          className="max-h-40 flex-1 resize-none rounded-xl border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {disabled ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}

function HumanPanel({
  reason,
  value,
  onChange,
  onSend,
}: {
  reason: string | null;
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
}) {
  return (
    <div className="border-t border-orange-200 bg-orange-50 px-4 py-3">
      <p className="mb-2 text-xs font-medium text-orange-700">
        Escalated to a human agent{reason ? ` (${reason})` : ""}. Reply as the agent:
      </p>
      <div className="flex items-end gap-2">
        <textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder="Human agent reply…"
          className="max-h-40 flex-1 resize-none rounded-xl border border-orange-300 bg-white px-3.5 py-2.5 text-[15px] text-slate-800 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={!value.trim()}
          className="rounded-xl bg-orange-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-orange-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
