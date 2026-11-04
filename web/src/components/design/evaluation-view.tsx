import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/cn";
import type { DesignEvaluation } from "@/lib/types";

import { CRITERION_LABEL } from "./components";

const pct = (x: number | null) => (x === null ? "—" : `${Math.round(x * 100)}%`);

function Items({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section>
      <h4 className="mb-1 text-xs font-medium text-fg-subtle">{title}</h4>
      <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] leading-relaxed text-fg marker:text-fg-subtle">
        {items.map((x, i) => <li key={i}>{x}</li>)}
      </ul>
    </section>
  );
}

/** Renders a design evaluation. Ungraded results never show a score. */
export function EvaluationView({
  ev,
  nodeNames = {},
  onEvidence,
}: {
  ev: DesignEvaluation;
  nodeNames?: Record<string, string>;
  onEvidence?: (ids: string[]) => void;
}) {
  if (ev.status !== "evaluated" || !ev.result) {
    return (
      <div className="rounded-lg border border-line p-3 text-[13px] text-fg-muted">
        <p className="flex items-center gap-2 text-fg">
          <AlertTriangle className="size-4" aria-hidden="true" />
          {ev.status === "pending" ? "Evaluation in progress" : "Ungraded"}
        </p>
        {ev.status === "ungraded" ? (
          <p className="mt-1">
            The evaluation could not be completed ({ev.error_code}). No score was recorded and nothing counts toward mastery.
          </p>
        ) : null}
      </div>
    );
  }
  const r = ev.result;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Evidence-backed score" value={pct(ev.total_score)} />
        <Stat label="Model's own total" value={pct(ev.model_total_score)} />
        <Stat label="Confidence" value={pct(ev.confidence)} />
      </div>
      <p className="text-xs leading-relaxed text-fg-subtle">
        AI judgment of version {ev.architecture_version}, not proof of mastery. Only criteria backed by components,
        connections or your own words count toward the score.
        {ev.mastery_eligible ? " Recorded as unverified reasoning evidence." : " Not recorded as mastery evidence."}
        {ev.injection_suspected ? " Instruction-like text was found in your design, so confidence was capped." : ""}
      </p>
      <p className="text-[13px] leading-relaxed text-fg">{r.summary}</p>

      <section>
        <h4 className="mb-2 text-xs font-medium text-fg-subtle">Criteria</h4>
        <ul className="flex flex-col divide-y divide-line-subtle rounded-lg border border-line">
          {r.criteria.map((c) => {
            const nodes = c.evidence.filter((e) => e.kind === "node").map((e) => e.ref);
            return (
              <li key={c.criterion} className="px-3 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] text-fg">{CRITERION_LABEL[c.criterion] ?? c.criterion}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-[11px] text-fg-subtle">
                      {c.evidence_status === "observed" ? "evidence" : c.evidence_status === "inferred" ? "unsupported" : ""}
                    </span>
                    <Score value={c.evidence_status === "observed" ? c.score : 0} max={c.max_score} muted={c.evidence_status !== "observed"} />
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-fg-muted">{c.rationale}</p>
                {c.evidence.length ? (
                  <ul className="mt-1.5 flex flex-wrap gap-1">
                    {c.evidence.map((e, i) => (
                      <li key={i}>
                        {e.kind === "quote" ? (
                          <q className="block text-[11px] text-fg-subtle italic">{e.ref}</q>
                        ) : (
                          <button
                            type="button"
                            disabled={!onEvidence}
                            onClick={() => onEvidence?.(e.kind === "node" ? [e.ref] : nodes)}
                            className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] text-fg-muted hover:text-fg disabled:hover:text-fg-muted"
                          >
                            {e.kind === "edge" ? "connection" : "component"}: {nodeNames[e.ref] ?? e.ref}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>
      <Items title="Risks" items={r.risks} />
      <Items title="Missing requirements" items={r.missing_requirements} />
      <Items title="Incorrect assumptions" items={r.incorrect_assumptions} />
      <Items title="Suggested improvements" items={r.improvements} />
      <Items title="Follow-up questions" items={r.follow_up_questions} />
      <p className="font-mono text-[11px] text-fg-subtle">
        {ev.versions.provider}/{ev.versions.model} · {ev.versions.evaluation} · {ev.versions.rubric}
        {ev.usage.prompt_tokens !== null ? ` · ${ev.usage.prompt_tokens}+${ev.usage.completion_tokens ?? 0} tokens` : ""}
        {" · cost not tracked"}
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-canvas px-2.5 py-2">
      <p className="text-lg font-semibold text-fg tabular-nums">{value}</p>
      <p className="text-[11px] text-fg-subtle">{label}</p>
    </div>
  );
}

function Score({ value, max, muted }: { value: number; max: number; muted: boolean }) {
  return (
    <span className="flex gap-0.5" aria-label={`${value} of ${max}`} role="img">
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className={cn("h-1.5 w-4 rounded-full", i < value ? "bg-fg" : muted ? "bg-line-subtle" : "bg-line")} />
      ))}
    </span>
  );
}
