"use client";

import { useEffect, useRef, useState } from "react";
import { chat, fetchHealth, resume, sendFeedback } from "@/lib/api";
import type { ChatMessage, HealthStatus, SSEEvent } from "@/lib/types";
import { HealthDot } from "./Badges";
import { ArrowUpIcon, HeadsetIcon, PlusIcon, SparkIcon } from "./Icons";
import MessageBubble from "./MessageBubble";

type Status = "idle" | "streaming" | "awaiting_human";

const SUGGESTIONS = [
  { title: "Refund policy", text: "What is your refund policy for monthly plans?" },
  { title: "Export error", text: "I get a 500 error when exporting a large dataset." },
  { title: "Enable SSO", text: "How do I enable SAML SSO for my workspace?" },
  { title: "Pricing", text: "How much does the Pro plan cost per month?" },
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
      <header className="flex items-center justify-between gap-3 border-b border-slate-200/70 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-glow">
            <SparkIcon className="h-[18px] w-[18px]" />
          </div>
          <div className="leading-tight">
            <h1 className="text-[15px] font-semibold text-slate-900">Archon</h1>
            <p className="text-xs text-slate-500">Nimbus customer support</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <HealthDot health={health} />
          <button
            type="button"
            onClick={newChat}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
          >
            <PlusIcon className="h-3.5 w-3.5" />
            New
          </button>
        </div>
      </header>

      <div className="scroll-area flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-6">
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
          busy={status === "streaming"}
        />
      )}
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center pt-8 text-center sm:pt-14">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-glow">
        <SparkIcon className="h-7 w-7" />
      </div>
      <h2 className="mt-5 text-xl font-semibold text-slate-900">How can I help?</h2>
      <p className="mt-1.5 text-sm text-slate-500">
        Ask about billing, technical issues, your account, or our plans.
      </p>
      <div className="mt-7 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.title}
            type="button"
            onClick={() => onPick(s.text)}
            className="group rounded-2xl border border-slate-200/80 bg-white/80 p-3.5 text-left transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-soft"
          >
            <div className="text-[13px] font-semibold text-slate-800 group-hover:text-brand-700">
              {s.title}
            </div>
            <div className="mt-0.5 text-xs text-slate-500">{s.text}</div>
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
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
}) {
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="px-4 pb-4 pt-2 sm:px-6">
      <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-soft transition focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-100">
        <textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Message Archon…"
          className="max-h-44 flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] text-slate-800 outline-none placeholder:text-slate-400"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={busy || !value.trim()}
          aria-label="Send"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-glow transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30 disabled:shadow-none"
        >
          {busy ? (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          ) : (
            <ArrowUpIcon className="h-[18px] w-[18px]" />
          )}
        </button>
      </div>
      <p className="mt-2 text-center text-[11px] text-slate-400">
        Archon can make mistakes. Answers are grounded in Nimbus docs.
      </p>
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
    <div className="px-4 pb-4 pt-2 sm:px-6">
      <div className="rounded-2xl border border-orange-200 bg-orange-50/80 p-3">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-orange-700">
          <HeadsetIcon className="h-3.5 w-3.5" />
          Escalated to a human agent{reason ? ` · ${reason}` : ""}
        </p>
        <div className="flex items-end gap-2 rounded-xl border border-orange-200 bg-white p-2 focus-within:ring-4 focus-within:ring-orange-100">
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
            placeholder="Reply as the human agent…"
            className="max-h-40 flex-1 resize-none bg-transparent px-2.5 py-1.5 text-[15px] text-slate-800 outline-none placeholder:text-slate-400"
          />
          <button
            type="button"
            onClick={onSend}
            disabled={!value.trim()}
            aria-label="Send as human agent"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ArrowUpIcon className="h-[18px] w-[18px]" />
          </button>
        </div>
      </div>
    </div>
  );
}
