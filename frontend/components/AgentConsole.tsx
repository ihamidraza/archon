"use client";

// The dedicated human-agent console for one department. Lists escalated conversations
// (the queue), shows a selected conversation's full context + history, and lets the agent
// reply — which streams back to the waiting customer via the backend's pub/sub.
//
// No auth: the agent name is a cosmetic localStorage value set on the hub page.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchQueue, getThread, resume } from "@/lib/api";
import type { ChatMessage, Department, QueueItem, SSEEvent } from "@/lib/types";
import { IntentBadge } from "./Badges";
import { ArrowUpIcon, HeadsetIcon, SparkIcon } from "./Icons";
import MessageBubble from "./MessageBubble";

const DEPT_LABEL: Record<Department, string> = {
  billing: "Billing",
  technical: "Technical",
  account: "Account",
  sales: "Sales",
};

let counter = 0;
const nextId = () => `a${Date.now()}-${counter++}`;

type Context = { reason: string; intent: string | null; pending: boolean } | null;

const noop = () => {};

export default function AgentConsole({ dept }: { dept: Department }) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [context, setContext] = useState<Context>(null);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [agentName, setAgentName] = useState("");

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setAgentName(localStorage.getItem("archon.agentName") || "");
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadQueue = useCallback(async () => {
    try {
      const res = await fetchQueue(dept);
      setItems(res.items);
    } catch {
      // transient API/network error — keep the last good queue
    }
  }, [dept]);

  useEffect(() => {
    loadQueue();
    const timer = setInterval(loadQueue, 5000);
    return () => clearInterval(timer);
  }, [loadQueue]);

  async function openThread(threadId: string) {
    setSelectedId(threadId);
    setMessages([]);
    setContext(null);
    try {
      const detail = await getThread(threadId);
      setMessages(detail.messages.map((m) => ({ id: nextId(), role: m.role, content: m.content })));
      setContext({
        reason: detail.reason || detail.escalation_reason || "",
        intent: detail.intent,
        pending: detail.pending,
      });
    } catch {
      setContext({ reason: "Could not load this conversation.", intent: null, pending: false });
    }
  }

  async function sendReply() {
    const text = reply.trim();
    if (!text || !selectedId || sending) return;

    const replyId = nextId();
    const threadId = selectedId;
    setMessages((prev) => [...prev, { id: replyId, role: "human-agent", content: "", pending: true }]);
    setReply("");
    setSending(true);

    const handler = (event: SSEEvent) => {
      if (event.type === "token") {
        setMessages((prev) =>
          prev.map((m) => (m.id === replyId ? { ...m, content: m.content + event.content } : m)),
        );
      } else if (event.type === "done") {
        setMessages((prev) => prev.map((m) => (m.id === replyId ? { ...m, pending: false } : m)));
      } else if (event.type === "error") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === replyId ? { ...m, pending: false, errored: true, content: event.detail } : m,
          ),
        );
      }
    };

    try {
      await resume(threadId, text, handler);
    } finally {
      setSending(false);
      setMessages((prev) => prev.map((m) => (m.id === replyId && m.pending ? { ...m, pending: false } : m)));
      setContext((c) => (c ? { ...c, pending: false } : c));
      loadQueue();
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-slate-200/70 px-5 py-4 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 text-white shadow-sm">
            <HeadsetIcon className="h-[18px] w-[18px]" />
          </div>
          <div className="leading-tight">
            <h1 className="text-[15px] font-semibold text-slate-900 dark:text-slate-100">
              {DEPT_LABEL[dept]} agent console
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {agentName ? `Signed in as ${agentName}` : "Escalated conversations"}
            </p>
          </div>
        </div>
        <Link
          href="/agent"
          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          All departments
        </Link>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 sm:grid-cols-[300px_1fr]">
        {/* Queue */}
        <aside className="scroll-area min-h-0 overflow-y-auto border-b border-slate-200/70 p-3 sm:border-b-0 sm:border-r dark:border-slate-800">
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Queue</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {items.length}
            </span>
          </div>
          {items.length === 0 ? (
            <p className="px-1 py-8 text-center text-xs text-slate-400">No escalations waiting.</p>
          ) : (
            <ul className="space-y-1.5">
              {items.map((item) => (
                <li key={item.thread_id}>
                  <button
                    type="button"
                    onClick={() => openThread(item.thread_id)}
                    className={`w-full rounded-xl border p-2.5 text-left transition ${
                      selectedId === item.thread_id
                        ? "border-orange-300 bg-orange-50/80 dark:border-orange-500/40 dark:bg-orange-500/10"
                        : "border-slate-200/80 bg-white hover:border-slate-300 dark:border-slate-700/80 dark:bg-slate-800/60 dark:hover:border-slate-600"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <IntentBadge intent={item.department} />
                      <span className="truncate text-[11px] text-slate-400">{item.reason}</span>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-[13px] text-slate-700 dark:text-slate-300">
                      {item.customer_message || "(no message)"}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Conversation */}
        <section className="flex min-h-0 flex-col">
          {selectedId === null ? (
            <div className="flex flex-1 flex-col items-center justify-center px-6 text-center text-slate-400">
              <SparkIcon className="h-7 w-7 opacity-40" />
              <p className="mt-3 text-sm">Select a conversation to view its history and reply.</p>
            </div>
          ) : (
            <>
              {context && (
                <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200/70 px-4 py-2.5 dark:border-slate-800">
                  <IntentBadge intent={context.intent} />
                  {context.reason && (
                    <span className="text-[11px] text-slate-500 dark:text-slate-400">{context.reason}</span>
                  )}
                  {!context.pending && (
                    <span className="ml-auto rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20">
                      resolved
                    </span>
                  )}
                </div>
              )}

              <div className="scroll-area flex-1 space-y-5 overflow-y-auto px-4 py-6">
                {messages.map((m) => (
                  <MessageBubble key={m.id} message={m} onFeedback={noop} />
                ))}
                <div ref={endRef} />
              </div>

              {context?.pending ? (
                <div className="px-4 pb-4 pt-2">
                  <div className="flex items-end gap-2 rounded-2xl border border-orange-200 bg-white p-2 shadow-soft focus-within:ring-4 focus-within:ring-orange-100 dark:border-orange-500/30 dark:bg-slate-800 dark:focus-within:ring-orange-500/20">
                    <textarea
                      rows={1}
                      value={reply}
                      onChange={(e) => setReply(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          sendReply();
                        }
                      }}
                      placeholder="Reply to the customer…"
                      className="max-h-40 flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500"
                    />
                    <button
                      type="button"
                      onClick={sendReply}
                      disabled={sending || !reply.trim()}
                      aria-label="Send reply"
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      {sending ? (
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                      ) : (
                        <ArrowUpIcon className="h-[18px] w-[18px]" />
                      )}
                    </button>
                  </div>
                </div>
              ) : (
                <p className="px-4 pb-4 pt-2 text-center text-[11px] text-slate-400">
                  This conversation has been answered.
                </p>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
