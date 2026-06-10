import type { HealthStatus } from "@/lib/types";

const INTENT_STYLES: Record<string, { dot: string; cls: string }> = {
  billing: {
    dot: "bg-emerald-500",
    cls: "bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20",
  },
  technical: {
    dot: "bg-sky-500",
    cls: "bg-sky-50 text-sky-700 ring-sky-100 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/20",
  },
  account: {
    dot: "bg-violet-500",
    cls: "bg-violet-50 text-violet-700 ring-violet-100 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-500/20",
  },
  sales: {
    dot: "bg-amber-500",
    cls: "bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20",
  },
};

const FALLBACK = {
  dot: "bg-slate-400",
  cls: "bg-slate-50 text-slate-600 ring-slate-200 dark:bg-slate-700/40 dark:text-slate-300 dark:ring-slate-600/40",
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
  const s = INTENT_STYLES[intent] ?? FALLBACK;
  return (
    <Chip className={s.cls}>
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
        <Chip className="bg-rose-50 text-rose-700 ring-rose-100 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/20">
          refused by guardrail
        </Chip>
      )}
      {escalated && (
        <Chip className="bg-orange-50 text-orange-700 ring-orange-100 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/20">
          human handoff
        </Chip>
      )}
    </>
  );
}

export function HealthDot({ health }: { health: HealthStatus | null }) {
  const ok = health?.status === "ok";
  const color = ok ? (health?.ollama ? "bg-emerald-500" : "bg-amber-500") : "bg-rose-500";
  const label = !ok ? "offline" : health?.ollama ? "online" : "model offline";
  return (
    <span className="flex items-center gap-1.5 rounded-full bg-slate-100/80 px-2.5 py-1 text-[11px] font-medium text-slate-500 ring-1 ring-slate-200/70 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700">
      <span className="relative flex h-2 w-2">
        {ok && health?.ollama && (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-60`} />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
      </span>
      {label}
      {health?.tracing && <span className="text-slate-400 dark:text-slate-500">· traced</span>}
    </span>
  );
}
