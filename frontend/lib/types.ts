// Wire types mirroring the backend SSE protocol (see backend/app/api/schemas.py).

export type SSEEvent =
  | { type: "session"; thread_id: string }
  | { type: "token"; content: string }
  | { type: "interrupt"; thread_id: string; reason: string; customer_message: string }
  | {
      type: "done";
      thread_id: string;
      intent: string | null;
      blocked: boolean;
      escalated: boolean;
      run_id: string | null;
    }
  | { type: "human_reply_start"; thread_id: string }
  | { type: "error"; detail: string };

export type Role = "user" | "assistant" | "human-agent";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  // streaming / lifecycle
  pending?: boolean;
  // metadata from the `done` event
  intent?: string | null;
  blocked?: boolean;
  escalated?: boolean;
  runId?: string | null;
  // local UI state
  feedback?: "up" | "down" | null;
  errored?: boolean;
}

export interface HealthStatus {
  status: string;
  ollama: boolean;
  tracing: boolean;
}

// Agent console wire types (see backend/app/api/schemas.py).
export const DEPARTMENTS = ["billing", "technical", "account", "sales"] as const;
export type Department = (typeof DEPARTMENTS)[number];

export interface QueueItem {
  thread_id: string;
  department: string;
  customer_message: string;
  reason: string;
  created_at: string;
  status: "waiting" | "resolved";
}

export interface QueueResponse {
  department: string | null;
  items: QueueItem[];
}

export interface TranscriptMessage {
  role: Role;
  content: string;
}

export interface ThreadDetail {
  thread_id: string;
  department: string;
  intent: string | null;
  escalation_reason: string | null;
  reason: string;
  customer_message: string;
  pending: boolean;
  messages: TranscriptMessage[];
}
