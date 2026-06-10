// Thin client for the Archon SSE API. The browser's EventSource only does GET, and our
// endpoints are POST, so we stream the response body manually with fetch + a reader.

import type { HealthStatus, SSEEvent } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

/** POST `path` and invoke `onEvent` for each parsed SSE event until the stream ends. */
export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    onEvent({ type: "error", detail: `Cannot reach the API at ${API_BASE}.` });
    return;
  }

  if (!res.ok || !res.body) {
    let detail = `Request failed (${res.status}).`;
    if (res.status === 429) detail = "Rate limit reached — please slow down.";
    try {
      const data = await res.json();
      if (data?.detail) detail = String(data.detail);
    } catch {
      // non-JSON error body; keep the default detail
    }
    onEvent({ type: "error", detail });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""))
        .join("\n");
      if (!data) continue;
      try {
        onEvent(JSON.parse(data) as SSEEvent);
      } catch {
        // ignore keep-alive / malformed frames
      }
    }
  }
}

export function chat(
  message: string,
  threadId: string | null,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE("/chat", { message, thread_id: threadId ?? undefined }, onEvent, signal);
}

export function resume(
  threadId: string,
  message: string,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE("/resume", { thread_id: threadId, message }, onEvent, signal);
}

export async function sendFeedback(
  runId: string,
  score: number,
  comment?: string,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, score, comment }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return Boolean(data?.recorded);
  } catch {
    return false;
  }
}

export async function fetchHealth(): Promise<HealthStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) return null;
    return (await res.json()) as HealthStatus;
  } catch {
    return null;
  }
}
