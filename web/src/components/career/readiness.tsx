import { CircleAlert, CircleCheck, CircleDashed, CircleX } from "lucide-react";

import { cn } from "@/lib/cn";
import type { BenchmarkRow, DimensionEval, Readiness } from "@/lib/types";

import { LEVEL_LABEL, STATUS_LABEL, TRACK_LABEL, levelLabel, pct } from "./format";

const ROW_ICON = { met: CircleCheck, unmet: CircleAlert, missing: CircleDashed, critical: CircleX } as const;
const ROW_TEXT = { met: "Met", unmet: "Below level", missing: "No evidence", critical: "Critical gap" } as const;

export function ReadinessHeadline({ r }: { r: Readiness }) {
  const t = r.target;
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs text-fg-subtle">{TRACK_LABEL[r.track]} · target {LEVEL_LABEL[r.target_level]} · framework {r.framework_version}</p>
          <p className="mt-1 text-xl font-semibold text-fg">
            {t.status === "insufficient_evidence" ? t.message : STATUS_LABEL[t.status]}
          </p>
          <p className="mt-1 text-sm text-fg-muted">
            Demonstrated level: <span className="text-fg">{levelLabel(r.demonstrated_level)}</span>
          </p>
        </div>
        <dl className="grid grid-cols-3 gap-4 text-right">
          <div><dt className="text-[11px] text-fg-subtle">Coverage</dt><dd className="font-mono text-lg text-fg tabular-nums">{pct(t.coverage)}</dd></div>
          <div><dt className="text-[11px] text-fg-subtle">Evidence items</dt><dd className="font-mono text-lg text-fg tabular-nums">{r.evidence_summary.items}</dd></div>
          <div><dt className="text-[11px] text-fg-subtle">Confidence</dt><dd className="font-mono text-lg text-fg">{r.confidence}</dd></div>
        </dl>
      </div>
      <ol className="flex flex-wrap gap-1.5 text-[11px]" aria-label="Readiness by level">
        {(["foundation", "junior", "mid", "senior"] as const).map((l) => (
          <li key={l} className={cn("rounded-full border px-2 py-0.5",
            ["ready", "ready_with_gaps"].includes(r.levels[l].status) ? "border-fg bg-fg text-canvas" : "border-line text-fg-muted")}>
            {LEVEL_LABEL[l]}: {STATUS_LABEL[r.levels[l].status]}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function BenchmarkList({ rows, title, empty }: { rows: BenchmarkRow[]; title: string; empty?: string }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-medium text-fg-subtle">{title}</h3>
      {rows.length ? (
        <ul className="divide-y divide-line-subtle rounded-lg border border-line">
          {rows.map((g) => {
            const Icon = ROW_ICON[g.status];
            return (
              <li key={g.dimension} className="flex items-start gap-3 px-3 py-2 text-[13px]">
                <Icon className={cn("mt-0.5 size-4 shrink-0", g.status === "met" ? "text-fg" : g.status === "critical" ? "text-fg" : "text-fg-subtle")} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="text-fg">{g.title}</span>
                  {g.gate ? <span className="ml-2 rounded border border-line px-1 text-[10px] text-fg-muted">gate</span> : null}
                  <span className="block text-xs text-fg-muted">
                    needs {LEVEL_LABEL[g.needed]} · shown {levelLabel(g.demonstrated)}
                    {g.status !== "met" && g.reasons.length ? ` · ${g.reasons.join("; ")}` : ""}
                    {g.dangerous_actions.length ? ` · dangerous actions: ${g.dangerous_actions.join(", ")}` : ""}
                  </span>
                </span>
                <span className="shrink-0 text-xs text-fg-muted">{ROW_TEXT[g.status]}</span>
              </li>
            );
          })}
        </ul>
      ) : <p className="text-xs text-fg-subtle">{empty ?? "None."}</p>}
    </section>
  );
}

export function CompetencyMatrix({ dims, highlight }: { dims: Record<string, DimensionEval>; highlight?: Set<string> }) {
  const levels = ["junior", "mid", "senior"] as const;
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="sr-only">Competency matrix: demonstrated level and evidence per dimension</caption>
        <thead>
          <tr className="border-b border-line-subtle text-left text-xs text-fg-subtle">
            <th scope="col" className="px-4 py-2.5 font-medium">Competency</th>
            {levels.map((l) => <th key={l} scope="col" className="px-2 py-2.5 text-center font-medium">{LEVEL_LABEL[l]}</th>)}
            <th scope="col" className="px-3 py-2.5 text-right font-medium">Evidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line-subtle">
          {Object.values(dims).map((d) => (
            <tr key={d.key} className={highlight && !highlight.has(d.key) ? "text-fg-subtle" : "text-fg"}>
              <th scope="row" className="px-4 py-2 text-left font-normal">
                {d.title}
                {d.ai_only ? <span className="ml-2 text-[10px] text-fg-subtle">AI-judged only</span> : null}
                {d.dangerous_actions.length ? <span className="ml-2 text-[10px] text-fg">dangerous action</span> : null}
              </th>
              {levels.map((l) => {
                const p = d.per_level[l];
                return (
                  <td key={l} className="px-2 py-2 text-center" title={p.met ? `Met (${pct(p.mean)}, weight ${p.weight})` : p.reasons.join("; ")}>
                    {p.met ? <span aria-label="met" className="inline-block size-2.5 rounded-full bg-fg" />
                      : p.weight > 0 ? <span aria-label="some evidence" className="inline-block size-2.5 rounded-full border border-fg-muted" />
                        : <span aria-label="no evidence" className="inline-block size-2.5 rounded-full border border-dashed border-line" />}
                  </td>
                );
              })}
              <td className="px-3 py-2 text-right font-mono text-xs text-fg-muted tabular-nums">
                {d.fresh_evidence}{d.verified_evidence ? ` (${d.verified_evidence} verified)` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line-subtle px-4 py-2 text-[11px] text-fg-subtle">
        Filled: level demonstrated. Outline: some evidence, not enough. Dashed: no evidence. Hover a cell for the reasons.
      </p>
    </div>
  );
}
