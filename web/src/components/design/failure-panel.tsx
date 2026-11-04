"use client";

import { ChevronLeft, Flame, Loader2 } from "lucide-react";
import { useId, useState } from "react";

import { answerFailureScenario, startFailureScenario } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { FailureAttempt, FailureScenario } from "@/lib/types";

const field =
  "w-full rounded-md border border-line bg-canvas px-2.5 py-2 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none";

const DIMENSION_LABEL: Record<string, string> = {
  impact_analysis: "Impact analysis",
  mitigation: "Mitigation",
  residual_risk: "Residual risk",
};

export function FailurePanel({
  projectId,
  suggested,
  all,
  initial,
  flush,
  hasNodes,
}: {
  projectId: string;
  suggested: FailureScenario[];
  all: FailureScenario[];
  initial: FailureAttempt[];
  flush: () => Promise<boolean>;
  hasNodes: boolean;
}) {
  const [attempts, setAttempts] = useState(initial);
  const [active, setActive] = useState<FailureAttempt | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const others = all.filter((s) => !suggested.some((x) => x.slug === s.slug));

  async function start(slug: string) {
    setBusy(slug);
    setError(null);
    if (!(await flush())) {
      setBusy(null);
      return setError("Save your design first: resolve the save problem shown above.");
    }
    const res = await startFailureScenario({ projectId, scenario: slug });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    setAttempts((a) => [res.data, ...a]);
    setActive(res.data);
  }

  if (active) {
    return (
      <Attempt
        attempt={active}
        onBack={() => setActive(null)}
        onUpdated={(a) => {
          setActive(a);
          setAttempts((list) => list.map((x) => (x.id === a.id ? a : x)));
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs leading-relaxed text-fg-muted">
        Educational drills: FORGE describes a failure, you explain the impact on <em>your</em> design and how you would
        mitigate it, and the AI evaluates your reasoning. Nothing is simulated or measured.
      </p>
      {!hasNodes ? <p className="text-xs text-fg">Add components to your design first.</p> : null}
      {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
      <section>
        <h3 className="mb-2 text-xs font-medium text-fg-subtle">Suggested for this challenge</h3>
        <ul className="flex flex-col gap-1.5">{suggested.map((s) => <Row key={s.slug} s={s} busy={busy} hasNodes={hasNodes} onStart={start} />)}</ul>
      </section>
      <details>
        <summary className="cursor-pointer text-xs text-fg-subtle">Other scenarios ({others.length})</summary>
        <ul className="mt-2 flex flex-col gap-1.5">{others.map((s) => <Row key={s.slug} s={s} busy={busy} hasNodes={hasNodes} onStart={start} />)}</ul>
      </details>
      {attempts.length ? (
        <section>
          <h3 className="mb-2 text-xs font-medium text-fg-subtle">Your attempts</h3>
          <ul className="flex flex-col gap-1">
            {attempts.map((a) => (
              <li key={a.id}>
                <button type="button" onClick={() => setActive(a)} className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left text-xs hover:bg-surface-hover">
                  <span className="truncate text-fg">{a.scenario.title}</span>
                  <span className="shrink-0 text-fg-muted">
                    v{a.architecture_version} · {a.status === "evaluated" && a.score !== null ? `${Math.round(a.score * 100)}%` : a.status}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function Attempt({ attempt: a, onBack, onUpdated }: { attempt: FailureAttempt; onBack: () => void; onUpdated: (a: FailureAttempt) => void }) {
  const id = useId();
  const [impact, setImpact] = useState(a.impact ?? "");
  const [mitigation, setMitigation] = useState(a.mitigation ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editable = a.status === "open" || a.status === "ungraded";

  async function submit() {
    setBusy(true);
    setError(null);
    const res = await answerFailureScenario({ attemptId: a.id, impact, mitigation });
    setBusy(false);
    if (!res.ok) return setError(res.error);
    onUpdated(res.data);
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <button type="button" onClick={onBack} className="inline-flex w-fit items-center gap-1 text-xs text-fg-muted hover:text-fg">
        <ChevronLeft className="size-3.5" aria-hidden="true" />All scenarios
      </button>
      <div className="rounded-lg border border-line bg-surface-elevated p-3">
        <p className="flex items-center gap-2 text-[13px] font-medium text-fg">
          <Flame className="size-4" aria-hidden="true" />{a.scenario.title}
        </p>
        <p className="mt-1 text-[13px] text-fg-muted">{a.scenario.prompt}</p>
        <p className="mt-2 text-[11px] text-fg-subtle">Applies to version {a.architecture_version} of your design.</p>
      </div>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div>
          <label htmlFor={`${id}-impact`} className="mb-1 block text-xs font-medium text-fg">1. What is the impact?</label>
          <textarea id={`${id}-impact`} className={`${field} min-h-24`} value={impact} disabled={!editable} minLength={20} maxLength={6000}
            onChange={(e) => setImpact(e.target.value)} placeholder="Which requests fail, which degrade, what do users see, what data is at risk?" />
        </div>
        <div>
          <label htmlFor={`${id}-mitigation`} className="mb-1 block text-xs font-medium text-fg">2. How do you mitigate and recover?</label>
          <textarea id={`${id}-mitigation`} className={`${field} min-h-24`} value={mitigation} disabled={!editable} minLength={20} maxLength={6000}
            onChange={(e) => setMitigation(e.target.value)} placeholder="Detection, immediate mitigation, recovery, and what you'd change in the design." />
        </div>
        {a.status === "ungraded" ? (
          <p className="text-xs text-fg-muted">The last evaluation could not be completed ({a.error_code}). No score was recorded. You can submit again.</p>
        ) : null}
        {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
        {editable ? (
          <Button type="submit" size="sm" disabled={busy || impact.trim().length < 20 || mitigation.trim().length < 20}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
            {busy ? "Evaluating…" : "Submit for evaluation"}
          </Button>
        ) : null}
      </form>

      {a.status === "evaluated" && a.result ? (
        <section className="flex flex-col gap-3 border-t border-line-subtle pt-4">
          <p className="text-sm text-fg">
            Score {a.score !== null ? `${Math.round(a.score * 100)}%` : "—"}
            <span className="ml-2 text-xs text-fg-subtle">AI judgment · confidence {Math.round(a.result.confidence * 100)}%</span>
          </p>
          <ul className="flex flex-col divide-y divide-line-subtle rounded-lg border border-line">
            {a.result.dimensions.map((d) => (
              <li key={d.dimension} className="px-3 py-2">
                <p className="flex justify-between text-[13px] text-fg">
                  {DIMENSION_LABEL[d.dimension] ?? d.dimension}
                  <span className="text-xs text-fg-muted tabular-nums">{d.evidence_status === "observed" ? d.score : 0}/{d.max_score}</span>
                </p>
                <p className="mt-0.5 text-xs text-fg-muted">{d.rationale}</p>
                {d.evidence_quote ? <q className="mt-1 block text-[11px] text-fg-subtle italic">{d.evidence_quote}</q> : null}
                {d.rejected_quote ? (
                  <p className="mt-1 text-[11px] text-fg-subtle">
                    No credit: the cited text isn&apos;t in your answer (<q className="italic">{d.rejected_quote}</q>).
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="text-[13px] leading-relaxed text-fg">{a.result.feedback}</p>
          {a.result.remaining_risks.length ? (
            <div>
              <h4 className="mb-1 text-xs font-medium text-fg-subtle">Remaining risks</h4>
              <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{a.result.remaining_risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
            </div>
          ) : null}
          <div className="rounded-lg border border-line p-3">
            <h4 className="mb-1 text-xs font-medium text-fg-subtle">Follow-up</h4>
            <p className="text-[13px] text-fg">{a.result.follow_up_question}</p>
            <p className="mt-1.5 text-[11px] text-fg-subtle">Answer it in the AI review conversation, improve the design, then run the drill again.</p>
          </div>
          <p className="text-[11px] text-fg-subtle">
            {a.result.note} {a.mastery_eligible ? "Recorded as unverified reasoning evidence." : "Not recorded as mastery evidence."}
          </p>
        </section>
      ) : null}
    </div>
  );
}

function Row({ s, busy, hasNodes, onStart }: { s: FailureScenario; busy: string | null; hasNodes: boolean; onStart: (slug: string) => Promise<void> }) {
  return (
    <li className="flex items-start gap-3 rounded-lg border border-line px-3 py-2.5">
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] text-fg">{s.title}</span>
        <span className="block text-xs text-fg-muted">{s.prompt}</span>
      </span>
      <Button size="sm" variant="secondary" disabled={busy !== null || !hasNodes} onClick={() => void onStart(s.slug)} aria-label={`Run drill: ${s.title}`}>
        {busy === s.slug ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}Run
      </Button>
    </li>
  );
}
