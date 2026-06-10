# Phase 9 — Next.js Frontend

> **Goal:** a polished browser chat UI that makes the whole system tangible — streaming
> answers, visible routing/guardrail state, thumbs feedback, and a working
> human-in-the-loop handoff. The UI is intentionally a **thin shell** over the Phase 8 SSE
> API; all intelligence stays in the backend.

---

## 1. Stack & shape

Next.js 14 (App Router) + TypeScript + Tailwind, no component library — small and
reviewable. Three layers:

```
app/page.tsx          → renders <Chat/>
components/Chat.tsx    → the client state machine (the only stateful piece)
components/…           → MessageBubble, Badges (presentational)
lib/api.ts             → SSE client (fetch + stream reader)
lib/types.ts           → wire types mirroring backend/app/api/schemas.py
```

The wire types are a literal mirror of the backend's SSE schema, so the contract is typed
end to end.

---

## 2. Streaming over `fetch` (not `EventSource`)

The browser's `EventSource` only does **GET**, but `/chat` is a **POST** (it has a body).
So `lib/api.ts` streams the response manually:

```ts
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  while ((sep = buffer.indexOf("\n\n")) !== -1) {       // one SSE frame
    const frame = buffer.slice(0, sep);
    buffer = buffer.slice(sep + 2);
    const data = frame.split("\n").filter(l => l.startsWith("data:")) …;
    onEvent(JSON.parse(data));                            // typed SSEEvent
  }
}
```

Non-OK responses (422 validation, 429 rate limit, 409 resume conflict, network errors) are
funneled into a synthetic `error` event, so the UI has exactly one code path to render.

---

## 3. The chat state machine (`Chat.tsx`)

One small machine drives everything:

```
idle ──send()──▶ streaming ──"done"──────────▶ idle
                     │
                     └──"interrupt"──▶ awaiting_human ──sendHumanReply()──▶ streaming ─▶ idle
```

Each turn appends a `user` bubble and a `pending` `assistant` bubble, then a per-reply
event handler mutates *that* message by id as events arrive:

| Event | UI effect |
| ----- | --------- |
| `session` | remember `thread_id` (used for every later turn + resume) |
| `token` | append text to the streaming bubble (with a blinking cursor) |
| `interrupt` | flip to `awaiting_human`; show the amber agent-reply panel |
| `done` | stamp the bubble with intent / guardrail badges + a `run_id` for feedback |
| `error` | render the bubble in red |

Because the **same `thread_id`** is sent on every request, the backend checkpointer keeps
the conversation coherent across turns — the UI itself stores no history server-side.

---

## 4. Human-in-the-loop in the browser

When a turn ends in `interrupt` instead of `done`, the composer is replaced by an **amber
"reply as the human agent" panel**. Submitting it calls `/resume` with the saved
`thread_id`; the agent's reply streams back as a distinct *Human agent* bubble. This is the
same pause/resume the CLI demoed — now driven from two browser interactions, proving the
backend's stateless-HTTP handoff works for real clients.

---

## 5. Making the AI state visible

The point of the UI is to *show the machinery*, so each answer carries:

- a **routing badge** (`routed to billing`, color-coded per specialist),
- **guardrail badges** (`refused by guardrail`, `human handoff`) when relevant,
- **👍/👎 feedback** that posts to `/feedback` with the run's `run_id` (no-op if tracing is
  off), and
- a header **health dot** reflecting `/health` (API up · model up · tracing on).

Model reasoning never reaches the screen — the stream is filtered server-side (Phase 7) and
the client only ever receives clean answer tokens.

---

## 6. Run it

```bash
make run            # backend  → :8000
make ui-install     # one-time
make ui             # frontend → :3000
```

Open <http://localhost:3000>, try a suggestion chip, then send something vague like
"hello" to trigger an escalation and reply as the human agent.

### Files added this phase
```
frontend/
  package.json · tsconfig.json · next.config.mjs · tailwind.config.ts · postcss.config.mjs
  app/{layout,page}.tsx · app/globals.css
  components/{Chat,MessageBubble,Badges}.tsx
  lib/{api,types}.ts
```

---

## 7. Concepts to take away

- **Stream POST with `fetch` + a reader.** `EventSource` is GET-only; reading the body
  stream yourself is a few lines and works for POST.
- **Normalize transport errors into one event type.** The UI renders `error` the same way
  whether it was a 429, a 409, or a dropped connection.
- **A typed event protocol keeps the UI thin.** `session/token/interrupt/done/error` maps
  almost directly onto a tiny state machine; the frontend holds no business logic.
- **Make the invisible visible.** Routing, guardrail, and escalation state are exactly what
  a reviewer wants to see — surface them as first-class UI.

**Next:** [`docs/10-deployment.md`](./10-deployment.md) — hardening: full test pass, error
handling, dependency audit, and deployment notes.
