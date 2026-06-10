import type { HealthStatus } from "@/lib/types";

const INTENT_STYLES: Record<string, { dot: string; text: string; bg: string }> = {
  billing: { dot: "bg-emerald-500", text: "text-emerald-700", bg: "bg-emerald-50 ring-emerald-100" },
  technical: { dot: "bg-sky-500", text: "text-sky-700", bg: "bg-sky-50 ring-sky-100" },
  account: { dot: "bg-violet-500", text: "text-violet-700", bg: "bg-violet-50 ring-violet-100" },
  sales: { dot: "bg-amber-500", text: "text-amber-700", bg: "bg-amber-50 ring-amber-100" },
};

function Chip({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${className}`}
    >
      {children}
    </span>
  );
}

export function IntentBadge({ intent }: { intent?: string | null }) {
  if (!intent) return null;
  const s = INTENT_STYLES[intent] ?? {
    dot: "bg-slate-400",
    text: "text-slate-600",
    bg: "bg-slate-50 ring-slate-200",
  };
  return (
    <Chip className={`${s.bg} ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {intent}
    </Chip>
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
        <Chip className="bg-rose-50 text-rose-700 ring-rose-100">refused by guardrail</Chip>
      )}
      {escalated && (
        <Chip className="bg-orange-50 text-orange-700 ring-orange-100">human handoff</Chip>
      )}
    </>
  );
}

export function HealthDot({ health }: { health: HealthStatus | null }) {
  const ok = health?.status === "ok";
  const color = ok ? (health?.ollama ? "bg-emerald-500" : "bg-amber-500") : "bg-rose-500";
  const label = !ok ? "offline" : health?.ollama ? "online" : "model offline";
  return (
    <span className="flex items-center gap-1.5 rounded-full bg-slate-100/80 px-2.5 py-1 text-[11px] font-medium text-slate-500 ring-1 ring-slate-200/70">
      <span className="relative flex h-2 w-2">
        {ok && health?.ollama && (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-60`} />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
      </span>
      {label}
      {health?.tracing && <span className="text-slate-400">· traced</span>}
    </span>
  );
}
