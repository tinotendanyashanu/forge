import { CircleCheck, CircleDashed, CircleX, EyeOff, Timer, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/cn";
import type { CodeTestResult, TestOutcome } from "@/lib/types";

const ICON: Record<TestOutcome, typeof CircleCheck> = {
  passed: CircleCheck,
  failed: CircleX,
  error: TriangleAlert,
  timeout: Timer,
  not_executed: CircleDashed,
};

const LABEL: Record<TestOutcome, string> = {
  passed: "Passed",
  failed: "Failed",
  error: "Error",
  timeout: "Timed out",
  not_executed: "Not executed",
};

const fmt = (v: unknown) => JSON.stringify(v);

export function TestResults({ results }: { results: CodeTestResult[] }) {
  return (
    <ol className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {results.map((r) => {
        const Icon = ICON[r.outcome];
        return (
          <li key={r.name} className="px-4 py-3">
            <div className="flex items-start gap-3">
              <Icon
                className={cn("mt-0.5 size-4 shrink-0", r.outcome === "passed" ? "text-fg" : "text-fg-muted")}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-x-2 text-sm text-fg">
                  {r.name}
                  {r.visibility === "hidden" ? (
                    <span className="inline-flex items-center gap-1 text-xs text-fg-subtle">
                      <EyeOff className="size-3" aria-hidden="true" />
                      hidden
                    </span>
                  ) : null}
                </p>
                {r.message ? <p className="mt-0.5 text-[13px] text-fg-muted">{r.message}</p> : null}
                {r.visibility === "public" && r.outcome !== "passed" && r.args ? (
                  <dl className="mt-2 grid gap-1 font-mono text-xs text-fg-muted">
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-fg-subtle">input</dt>
                      <dd className="break-all">{fmt(r.args)}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-fg-subtle">expected</dt>
                      <dd className="break-all">
                        {r.expected?.raises ? `raises ${r.expected.raises}` : fmt(r.expected?.value)}
                      </dd>
                    </div>
                    {r.actual ? (
                      <div className="flex gap-2">
                        <dt className="w-16 shrink-0 text-fg-subtle">actual</dt>
                        <dd className="break-all">{r.actual}</dd>
                      </div>
                    ) : null}
                  </dl>
                ) : null}
              </div>
              <span className="shrink-0 text-right text-xs text-fg-subtle tabular-nums">
                {LABEL[r.outcome]}
                {r.duration_ms !== null ? <span className="block">{r.duration_ms} ms</span> : null}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
