"use client";

import { CheckCircle2, Download, History, Loader2, RotateCcw, XCircle } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { fetchOpsEvaluations, fetchOpsReplay, fetchPostmortem, opsResolve, opsRetryReview, reviewPostmortem, savePostmortem } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { OpsEvaluation, OpsPostmortem, OpsSession } from "@/lib/types";

import { TimeChart } from "./chart";
import { QUALITY_LABEL, RCA_LABEL, STATUS_LABEL, pct } from "./format";
import { useLoad } from "./use-load";

const field =
  "w-full rounded-md border border-line bg-canvas px-2.5 py-1.5 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none";

const RCA_FIELDS: [string, string, string, number][] = [
  ["summary", "Incident summary", "What happened, when, and how it was resolved.", 10],
  ["customer_impact", "Customer impact", "Who was affected, how, and for how long.", 5],
  ["evidence", "Evidence collected", "The specific logs, metrics, traces and records that support your conclusion.", 5],
  ["root_cause", "Root cause", "The causal mechanism, not just the symptom.", 10],
  ["contributing_factors", "Contributing factors", "What made it possible, worse, or slower to detect.", 0],
  ["mitigation", "Mitigation performed", "What you changed and why it was safe.", 5],
  ["recovery_validation", "Validation of recovery", "How you know the service recovered and stays recovered.", 5],
  ["prevention", "Preventive actions", "Concrete follow-ups that address the cause.", 5],
];

// ---------------------------------------------------------------- resolve (RCA)

export function ResolvePanel({ session, onResolved }: { session: OpsSession; onResolved: (s: OpsSession) => void }) {
  const id = useId();
  const storeKey = `forge:ops:rca:${session.id}`;
  const [values, setValues] = useState<Record<string, string>>(() => {
    try {
      return JSON.parse(window.localStorage.getItem(storeKey) ?? "{}");
    } catch {
      return {};
    }
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clientId = useRef<string | null>(null);
  const ready = session.state.status === "monitoring" && session.state.recovery.verified;

  function set(k: string, v: string) {
    const next = { ...values, [k]: v };
    setValues(next);
    try {
      window.localStorage.setItem(storeKey, JSON.stringify(next));
    } catch {}
  }

  async function submit() {
    setBusy(true);
    setError(null);
    clientId.current ??= crypto.randomUUID();
    const res = await opsResolve({ sessionId: session.id, rca: values, clientActionId: clientId.current });
    setBusy(false);
    if (!res.ok) {
      clientId.current = null;
      return setError(res.error);
    }
    try {
      window.localStorage.removeItem(storeKey);
    } catch {}
    onResolved(res.data.session);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex max-w-3xl flex-col gap-4"
    >
      <div className={cn("rounded-lg border p-3 text-[13px]", ready ? "border-fg text-fg" : "border-dashed border-line text-fg-muted")}>
        {ready
          ? `Recovery verified: ${session.state.recovery.message} You can resolve the incident.`
          : `Resolution requires a verified recovery. ${session.state.recovery.message}`}
      </div>
      <fieldset>
        <legend className="mb-2 text-xs font-medium text-fg">Root cause (pick the one your evidence supports)</legend>
        {session.root_cause_options ? (
          <div className="flex flex-col gap-1.5">
            {session.root_cause_options.map((o) => (
              <label key={o.id} className={cn("flex cursor-pointer gap-2.5 rounded-lg border px-3 py-2.5 text-[13px]", values.root_cause_choice === o.id ? "border-fg bg-surface-elevated" : "border-line hover:bg-surface-hover")}>
                <input type="radio" name={`${id}-rc`} value={o.id} checked={values.root_cause_choice === o.id} onChange={() => set("root_cause_choice", o.id)} className="mt-1 accent-white" />
                <span className="text-fg">{o.text}</span>
              </label>
            ))}
          </div>
        ) : (
          <p className="text-xs text-fg-subtle">The options appear once the incident is in monitoring.</p>
        )}
      </fieldset>
      {RCA_FIELDS.map(([k, label, hint, min]) => (
        <div key={k}>
          <label htmlFor={`${id}-${k}`} className="mb-1 block text-xs font-medium text-fg">{label}</label>
          <textarea id={`${id}-${k}`} className={`${field} min-h-16 resize-y`} maxLength={4000} minLength={min || undefined}
            required={min > 0} value={values[k] ?? ""} onChange={(e) => set(k, e.target.value)} placeholder={hint} />
        </div>
      ))}
      {error ? <p role="alert" className="text-sm text-fg">{error}</p> : null}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy || !ready || !values.root_cause_choice}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
          {busy ? "Resolving and reviewing…" : "Resolve incident"}
        </Button>
        <span className="text-xs text-fg-subtle">Draft saved in this browser. Resolving records the verified outcome, then the AI reviews your analysis.</span>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- summary & debrief

export function SummaryPanel({ session, evidenceLabel }: { session: OpsSession; evidenceLabel: (id: string) => string }) {
  const evals = useLoad(`evals:${session.revision}`, () => fetchOpsEvaluations(session.id));
  const [retrying, setRetrying] = useState(false);
  const [list, setList] = useState<OpsEvaluation[] | null>(null);
  const evaluations = list ?? evals.data ?? [];
  const rca = evaluations.find((e) => e.kind === "rca");
  const o = session.outcome;
  const d = session.debrief;
  const actionLabel = new Map(d?.actions.map((a) => [a.id, a.label]) ?? []);

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      {o ? (
        <section aria-labelledby="verified-h" className="rounded-xl border border-line bg-surface p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h3 id="verified-h" className="text-sm font-medium text-fg">Verified simulation outcome</h3>
            <p className="text-2xl font-semibold text-fg tabular-nums">{pct(o.score)}</p>
          </div>
          <p className="mt-1 text-xs text-fg-subtle">
            Graded deterministically by the scenario rules. Recorded as verified practical evidence. One incident never establishes mastery.
          </p>
          <dl className="mt-4 grid gap-3 text-[13px] sm:grid-cols-2">
            <Item ok={o.root_cause_correct} label="Root cause" text={o.root_cause_correct ? "Correctly identified" : "Not identified"} />
            <Item ok={o.recovered} label="Service recovered" text={o.recovered ? "Yes, verified" : "No"} />
            <Item ok={o.key_evidence_missed.length === 0} label="Key evidence pinned" text={`${o.key_evidence_found.length} of ${o.key_evidence_found.length + o.key_evidence_missed.length}`} />
            <Item ok={!o.harmful_actions.length} label="Mitigation safety" text={o.harmful_actions.length ? `${o.harmful_actions.length} harmful, ${o.risky_actions.length} risky` : o.risky_actions.length ? `${o.risky_actions.length} risky action(s)` : "No risky actions"} />
            <Item ok={o.minutes_to_recovery !== null && o.minutes_to_recovery <= o.target_minutes} label="Time to recovery" text={o.minutes_to_recovery === null ? "—" : `${o.minutes_to_recovery} min (target ${o.target_minutes})`} />
            {o.decisions ? (
              <Item ok={o.decisions.score >= 0.75} label="Decision quality" text={`${pct(o.decisions.score)} (diagnosed first ${pct(o.decisions.informed)}, mitigation precision ${pct(o.decisions.precision)}, investigation focus ${pct(o.decisions.focus)})`} />
            ) : (
              <Item ok label="Actions" text={`${o.investigation_actions} investigations, ${o.mitigation_actions} mitigations`} />
            )}
          </dl>
          {o.decision_flags?.length ? (
            <ul className="mt-3 flex flex-col gap-1 text-xs text-fg">
              {o.decision_flags.map((f) => <li key={f}>• {f}</li>)}
            </ul>
          ) : null}
          {o.key_evidence_missed.length ? (
            <p className="mt-3 text-xs text-fg-muted">Missed key evidence: {o.key_evidence_missed.map((e) => `${e} (${evidenceLabel(e)})`).join(", ")}</p>
          ) : null}
        </section>
      ) : (
        <p className="rounded-lg border border-dashed border-line p-4 text-sm text-fg-muted">
          This attempt was ended without resolution, so there is no outcome and nothing was recorded as mastery evidence. The debrief below is for learning.
        </p>
      )}

      {o?.decision_review?.length ? (
        <section aria-labelledby="dec-h" className="rounded-xl border border-line p-5">
          <h3 id="dec-h" className="text-sm font-medium text-fg">Your decisions, in order</h3>
          <p className="mt-1 text-xs text-fg-subtle">
            Each decision is graded by the scenario rules: was it useful, did you investigate before changing the system, and did the change address the cause?
          </p>
          <ol className="mt-3 divide-y divide-line-subtle rounded-lg border border-line">
            {o.decision_review.map((r, i) => (
              <li key={i} className="grid grid-cols-[52px_minmax(0,1fr)_auto] gap-3 px-3 py-2 text-[13px]">
                <span className="font-mono text-xs text-fg-subtle">+{r.minute}m</span>
                <span className="min-w-0">
                  <span className="block text-fg">{r.kind === "mitigate" ? "Change: " : "Check: "}{r.label}</span>
                  {r.teach ? <span className="block text-xs text-fg-muted">{r.teach}</span> : null}
                  {r.kind === "mitigate" && r.informed === false ? <span className="block text-xs text-fg">Made before any useful investigation.</span> : null}
                </span>
                <span className={cn("text-xs", ["effective", "useful"].includes(r.assessment) ? "text-fg" : "text-fg-muted")}>{r.assessment}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {o ? (
        <section aria-labelledby="ai-h" className="rounded-xl border border-line p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h3 id="ai-h" className="text-sm font-medium text-fg">AI review of your root-cause analysis</h3>
            {rca?.status === "evaluated" ? <p className="text-lg font-semibold text-fg tabular-nums">{pct(rca.total_score)}</p> : null}
          </div>
          <p className="mt-1 text-xs text-fg-subtle">Advisory. Only criteria backed by your pinned evidence or your own words count. Never overrides the verified outcome.</p>
          {!rca ? <p className="mt-3 text-xs text-fg-muted">Loading…</p> : rca.status !== "evaluated" || !rca.result ? (
            <div className="mt-3 text-[13px] text-fg-muted">
              <p>Ungraded ({rca.error_code ?? rca.status}). No AI score was recorded; the verified outcome above stands.</p>
              <Button className="mt-2" size="sm" variant="secondary" disabled={retrying} onClick={async () => {
                setRetrying(true);
                const r = await opsRetryReview(session.id);
                setRetrying(false);
                if (r.ok) setList(r.data.evaluations);
              }}>
                {retrying ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}Retry review
              </Button>
            </div>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              <p className="text-[13px] text-fg">{rca.result.summary}</p>
              <ul className="divide-y divide-line-subtle rounded-lg border border-line">
                {rca.result.criteria?.map((c) => (
                  <li key={c.criterion} className="px-3 py-2">
                    <p className="flex justify-between gap-2 text-[13px] text-fg">
                      {RCA_LABEL[c.criterion] ?? c.criterion}
                      <span className="font-mono text-xs text-fg-muted">{c.evidence_status === "observed" ? c.score : 0}/{c.max_score}{c.evidence_status === "inferred" ? " (unsupported)" : ""}</span>
                    </p>
                    <p className="text-xs text-fg-muted">{c.rationale}</p>
                  </li>
                ))}
              </ul>
              {rca.result.gaps.length ? <List title="Gaps" items={rca.result.gaps} /> : null}
              <List title="Follow-up questions" items={rca.result.follow_up_questions} />
              <p className="font-mono text-[11px] text-fg-subtle">
                {rca.versions.provider}/{rca.versions.model} · {rca.versions.evaluation} · {rca.versions.rubric}
                {rca.usage.prompt_tokens !== null ? ` · ${rca.usage.prompt_tokens}+${rca.usage.completion_tokens ?? 0} tokens` : ""} · cost not tracked
                {rca.mastery_eligible ? " · recorded as unverified debugging evidence" : " · not recorded as evidence"}
              </p>
            </div>
          )}
        </section>
      ) : null}

      {d ? (
        <section aria-labelledby="debrief-h" className="flex flex-col gap-4">
          <h3 id="debrief-h" className="text-sm font-medium text-fg">Debrief</h3>
          <div className="rounded-lg border border-line p-4">
            <h4 className="mb-1 text-xs font-medium text-fg-subtle">Root cause</h4>
            <p className="text-[13px] text-fg">{d.root_causes.find((r) => r.correct)?.text}</p>
            <p className="mt-2 text-[13px] leading-relaxed text-fg-muted">{d.explanation}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <List title="Investigation path" items={d.investigation_path} ordered />
            <List title="Contributing factors" items={d.contributing_factors} />
            <List title="Misleading signals" items={d.misleading_signals.map((m) => `${m.signal}: ${m.why}`)} />
            <List title="Prevention" items={d.prevention} />
          </div>
          <div>
            <h4 className="mb-1 text-xs font-medium text-fg-subtle">Other hypotheses</h4>
            <ul className="flex flex-col gap-1.5 text-[13px]">
              {d.root_causes.filter((r) => !r.correct).map((r) => (
                <li key={r.id}><span className="text-fg">{r.text}</span> <span className="text-fg-muted">{r.explanation}</span></li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="mb-1 text-xs font-medium text-fg-subtle">Every available action</h4>
            <ul className="divide-y divide-line-subtle rounded-lg border border-line text-[13px]">
              {d.actions.map((a) => (
                <li key={a.id} className="px-3 py-2">
                  <p className="flex justify-between gap-2"><span className="text-fg">{actionLabel.get(a.id)}</span><span className="text-xs text-fg-muted">{QUALITY_LABEL[a.quality]}</span></p>
                  {a.teach ? <p className="text-xs text-fg-muted">{a.teach}</p> : null}
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Item({ ok, label, text }: { ok: boolean; label: string; text: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className="flex items-start gap-2">
      <Icon className={cn("mt-0.5 size-4 shrink-0", ok ? "text-fg" : "text-fg-subtle")} aria-hidden="true" />
      <div>
        <dt className="text-xs text-fg-subtle">{label}</dt>
        <dd className="text-fg">{text}</dd>
      </div>
    </div>
  );
}

function List({ title, items, ordered = false }: { title: string; items: string[]; ordered?: boolean }) {
  const L = ordered ? "ol" : "ul";
  return (
    <div>
      <h4 className="mb-1 text-xs font-medium text-fg-subtle">{title}</h4>
      <L className={cn("flex flex-col gap-1 pl-4 text-[13px] text-fg marker:text-fg-subtle", ordered ? "list-decimal" : "list-disc")}>
        {items.map((x, i) => <li key={i}>{x}</li>)}
      </L>
    </div>
  );
}

// ---------------------------------------------------------------- postmortem

export function PostmortemPanel({ session, onStarted }: { session: OpsSession; onStarted: () => void }) {
  const id = useId();
  const [pm, setPm] = useState<OpsPostmortem | null>(null);
  const [content, setContent] = useState<Record<string, string>>({});
  const [state, setState] = useState<"saved" | "unsaved" | "saving" | "conflict" | "error">("saved");
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<OpsEvaluation | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const rev = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    fetchPostmortem(session.id).then((r) => {
      if (!alive) return;
      if (!r.ok) return setError(r.error);
      setPm(r.data);
      setContent(r.data.content);
      latest.current = r.data.content;
      rev.current = r.data.revision;
      onStarted();
    });
    fetchOpsEvaluations(session.id).then((r) => {
      if (alive && r.ok) setReview(r.data.find((e) => e.kind === "postmortem") ?? null);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]);

  async function save(): Promise<boolean> {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    setState("saving");
    const r = await savePostmortem({ sessionId: session.id, baseRevision: rev.current, content: latest.current });
    if (!r.ok) {
      setError(r.error);
      setState(/changed elsewhere/i.test(r.error) ? "conflict" : "error");
      return false;
    }
    rev.current = r.data.revision;
    setPm(r.data);
    setState("saved");
    setError(null);
    return true;
  }

  function edit(k: string, v: string) {
    const next = { ...latest.current, [k]: v };
    latest.current = next;
    setContent(next);
    setState("unsaved");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void save(), 1500);
  }

  async function askReview() {
    if (state !== "saved" && !(await save())) return;
    setReviewing(true);
    const r = await reviewPostmortem(session.id);
    setReviewing(false);
    if (r.ok) setReview(r.data);
    else setError(r.error);
  }

  if (!pm) return <p className="text-sm text-fg-muted">{error ?? "Preparing the postmortem from your timeline and analysis…"}</p>;
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className="text-xs text-fg-muted">
            Revision {pm.revision} · {state === "saved" ? "All changes saved" : state === "saving" ? "Saving…" : state === "conflict" ? "Changed elsewhere: reload to continue" : state === "error" ? "Not saved" : "Unsaved changes"}
          </p>
          <a href={`/ops/sessions/${session.id}/postmortem.md`} className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg"><Download className="size-3.5" aria-hidden="true" />Export Markdown</a>
        </div>
        <p className="text-xs text-fg-subtle">Blameless: describe systems, decisions and signals, not individuals. Prefilled from your audit log and root-cause analysis.</p>
        {pm.sections.map((s) => (
          <div key={s.key}>
            <label htmlFor={`${id}-${s.key}`} className="mb-1 block text-xs font-medium text-fg">{s.title}</label>
            <textarea id={`${id}-${s.key}`} className={`${field} min-h-20 resize-y font-[inherit] leading-relaxed`} maxLength={8000} value={content[s.key] ?? ""} onChange={(e) => edit(s.key, e.target.value)} />
          </div>
        ))}
        {error && state !== "conflict" ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
      </div>
      <aside className="flex flex-col gap-3">
        <Button variant="secondary" size="sm" onClick={() => void askReview()} disabled={reviewing}>
          {reviewing ? <Loader2 className="animate-spin" aria-hidden="true" /> : <History aria-hidden="true" />}
          {reviewing ? "Reviewing…" : "Ask the AI to review this postmortem"}
        </Button>
        {review ? (
          review.status === "evaluated" && review.result ? (
            <div className="rounded-lg border border-line p-3 text-[13px]">
              <p className="mb-1 text-[11px] text-fg-subtle">AI review of revision {review.postmortem_revision} (advisory)</p>
              <p className="text-fg">{review.result.summary}</p>
              {review.result.gaps.length ? <div className="mt-2"><List title="Gaps" items={review.result.gaps} /></div> : null}
              {review.result.blameless_issues?.length ? <div className="mt-2"><List title="Blameless issues" items={review.result.blameless_issues} /></div> : null}
              <div className="mt-2"><List title="Follow-up questions" items={review.result.follow_up_questions} /></div>
            </div>
          ) : (
            <p className="text-xs text-fg-muted">Review unavailable ({review.error_code}). Nothing was scored.</p>
          )
        ) : <p className="text-xs text-fg-subtle">The reviewer checks the timeline against your audit log, causality, follow-ups and blamelessness.</p>}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- timeline & replay

export function TimelinePanel({ session }: { session: OpsSession }) {
  const [seq, setSeq] = useState<number | null>(null);
  const replay = useLoad(`replay:${session.revision}:${seq}`, () => fetchOpsReplay({ sessionId: session.id, seq }));
  const steps = replay.data?.steps ?? [];
  const firstErr = session.metric_catalog.find((m) => m.metric === "error_rate");
  const series = replay.data?.metrics.find((m) => m.key === firstErr?.key);
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section aria-label="Audit log">
        <h3 className="mb-2 text-xs font-medium text-fg-subtle">Audit log (every action, query and decision)</h3>
        <ol className="flex flex-col gap-1 font-mono text-xs">
          {steps.map((s) => (
            <li key={s.seq}>
              <button
                type="button"
                disabled={!s.has_snapshot}
                onClick={() => setSeq(s.seq === seq ? null : s.seq)}
                aria-current={s.seq === seq}
                className={cn("w-full rounded px-2 py-1 text-left", s.seq === seq ? "bg-surface-elevated text-fg" : "text-fg-muted hover:bg-surface-hover", !s.has_snapshot && "cursor-default hover:bg-transparent")}
              >
                <span className="text-fg-subtle">+{s.minute_before}m</span>{" "}
                <span className={s.accepted ? "text-fg" : "line-through"}>{s.kind === "command" ? `$ ${String(s.params.command ?? "")}` : s.label ?? s.kind}</span>
                {s.status_before !== s.status_after ? <span className="text-fg-subtle"> · {STATUS_LABEL[s.status_after as keyof typeof STATUS_LABEL]}</span> : null}
                {!s.accepted && s.reason ? <span className="block text-fg-subtle">{s.reason}</span> : null}
              </button>
            </li>
          ))}
        </ol>
      </section>
      <section aria-label="Replay">
        <h3 className="mb-2 text-xs font-medium text-fg-subtle">{seq === null ? "Current state" : `State after step ${seq}`} (select a step to replay)</h3>
        {replay.data ? (
          <div className="flex flex-col gap-2">
            <p className="text-[13px] text-fg">{replay.data.state.condition.label}: <span className="text-fg-muted">{replay.data.state.condition.summary}</span></p>
            <p className="font-mono text-xs text-fg-subtle">status {replay.data.state.status} · minute {replay.data.state.minute}</p>
            {series && firstErr ? <TimeChart title={`${firstErr.service} · ${firstErr.label}`} unit={firstErr.unit} points={series.points} /> : null}
            <ul className="grid grid-cols-2 gap-1 text-xs">
              {Object.entries(replay.data.state.health).map(([svc, h]) => (
                <li key={svc} className="flex justify-between rounded bg-surface px-2 py-1"><span className="text-fg">{svc}</span><span className="text-fg-muted">{h}</span></li>
              ))}
            </ul>
          </div>
        ) : <p className="text-xs text-fg-subtle">Loading…</p>}
      </section>
    </div>
  );
}
