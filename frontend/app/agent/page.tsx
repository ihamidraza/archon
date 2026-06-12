"use client";

// Agent hub: pick a department console. No authentication — the optional display name is a
// cosmetic, locally-stored label shown in the console header (see plan: auth out of scope).

import Link from "next/link";
import { useEffect, useState } from "react";
import { DEPARTMENTS, type Department } from "@/lib/types";
import { HeadsetIcon, SparkIcon } from "@/components/Icons";

const DEPT_META: Record<Department, { label: string; blurb: string }> = {
  billing: { label: "Billing", blurb: "Invoices, charges, refunds, subscriptions" },
  technical: { label: "Technical", blurb: "Bugs, errors, outages, integrations" },
  account: { label: "Account", blurb: "Profile, workspace, SSO, security" },
  sales: { label: "Sales", blurb: "Pricing, plans, features, trials" },
};

export default function AgentHub() {
  const [name, setName] = useState("");

  useEffect(() => {
    setName(localStorage.getItem("archon.agentName") || "");
  }, []);

  function onNameChange(value: string) {
    setName(value);
    localStorage.setItem("archon.agentName", value);
  }

  return (
    <main className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col px-4 py-10 sm:py-16">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-amber-500 text-white shadow-glow">
          <HeadsetIcon className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Agent consoles</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Pick your department to handle escalated conversations.
          </p>
        </div>
      </div>

      <label className="mt-8 block">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          Display name (optional)
        </span>
        <input
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="e.g. Sam from Billing"
          className="mt-1.5 w-full max-w-sm rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-brand-400 focus:ring-4 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-brand-500/20"
        />
      </label>

      <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {DEPARTMENTS.map((dept) => (
          <Link
            key={dept}
            href={`/agent/${dept}`}
            className="group rounded-2xl border border-slate-200/80 bg-white/80 p-4 transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-soft dark:border-slate-700/80 dark:bg-slate-800/60 dark:hover:border-brand-500"
          >
            <div className="flex items-center gap-2">
              <SparkIcon className="h-4 w-4 text-brand-500" />
              <span className="text-[15px] font-semibold text-slate-800 group-hover:text-brand-700 dark:text-slate-200 dark:group-hover:text-brand-300">
                {DEPT_META[dept].label}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{DEPT_META[dept].blurb}</p>
          </Link>
        ))}
      </div>

      <p className="mt-10 text-center text-[11px] text-slate-400">
        Demo console — no authentication. Anyone with the link can view and reply.
      </p>
    </main>
  );
}
