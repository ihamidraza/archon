# Archon Frontend

A polished **Next.js 14** (App Router + TypeScript + Tailwind) chat UI for the Archon
support agent. It consumes the backend's Server-Sent Events protocol — streaming answers,
routing/guardrail badges, thumbs feedback, and the human-in-the-loop resume flow.

## Run it

```bash
# 1. backend first (from the repo root)
make run                      # FastAPI on http://localhost:8000

# 2. frontend
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm install                        # or: make ui-install   (from repo root)
npm run dev                        # or: make ui            → http://localhost:3000
```

## What it shows

- **Streaming answers** token-by-token (model `<think>` reasoning is filtered out).
- **Routing & guardrails** — each answer is tagged with the specialist it was routed to,
  and flags when a message was refused or escalated.
- **Human-in-the-loop** — when the agent escalates, an amber panel lets you reply *as the
  human agent*; the reply streams back to the customer (drives the `/resume` endpoint).
- **Feedback** — 👍/👎 on an answer posts to `/feedback` (recorded in LangSmith when tracing
  is on).
- **Health** — a status dot reflects `/health` (API + model + tracing).

## Layout

```
app/            layout · page · global styles
components/      Chat (state machine) · MessageBubble · Badges
lib/            api.ts (SSE client) · types.ts (wire protocol)
```

The SSE wire types in `lib/types.ts` mirror `backend/app/api/schemas.py`.
