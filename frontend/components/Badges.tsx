import type { HealthStatus } from "@/lib/types";

const INTENT_STYLES: Record<string, string> = {
  billing: "bg-emerald-100 text-emerald-700",
  technical: "bg-sky-100 text-sky-700",
  account: "bg-violet-100 text-violet-700",
  sales: "bg-amber-100 text-amber-700",
};

export function IntentBadge({ intent }: { intent?: string | null }) {
  if (!intent) return null;
  const style = INTENT_STYLES[intent] ?? "bg-slate-100 text-slate-600";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      routed to {intent}
    </span>
  );
}

export function GuardrailBadges({
  blocked,
  escalated,
}: {
  blocked?: boolean;
  escalated?: boolean;
}) {
  return (
    <>
      {blocked && (
        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">
          refused by guardrail
        </span>
      )}
      {escalated && (
        <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
          human handoff
        </span>
      )}
    </>
  );
}

export function HealthDot({ health }: { health: HealthStatus | null }) {
  const ok = health?.status === "ok";
  const color = ok ? (health?.ollama ? "bg-emerald-400" : "bg-amber-400") : "bg-rose-400";
  const label = !ok
    ? "API offline"
    : health?.ollama
      ? "API online"
      : "API up · model offline";
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-500">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
      {health?.tracing && <span className="text-slate-400">· tracing on</span>}
    </span>
  );
}
