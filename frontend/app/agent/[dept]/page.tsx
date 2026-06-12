import { notFound } from "next/navigation";
import AgentConsole from "@/components/AgentConsole";
import { DEPARTMENTS, type Department } from "@/lib/types";

export default async function DepartmentConsolePage({
  params,
}: {
  params: Promise<{ dept: string }>;
}) {
  const { dept } = await params;
  if (!DEPARTMENTS.includes(dept as Department)) notFound();

  return (
    <main className="mx-auto flex h-[100dvh] max-w-5xl flex-col sm:py-5">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white/75 shadow-soft ring-1 ring-slate-200/70 backdrop-blur-xl dark:bg-slate-900/70 dark:ring-slate-800/80 sm:rounded-[28px]">
        <AgentConsole dept={dept as Department} />
      </div>
    </main>
  );
}
