"use client";

import { CheckCircle2, Circle, CircleDashed, CircleSlash, ExternalLink, Loader2, Play, Send, Timer } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { careerAttemptAction, careerRespond, careerSectionAction, fetchCareerAttempt } from "@/app/actions";
import { Button, ButtonLink } from "@/components/ui/button";
import { MessageText } from "@/components/ui/message-text";
import { cn } from "@/lib/cn";
import type { AttemptSection, AttemptView, CareerItem } from "@/lib/types";

import { KIND_LABEL, LEVEL_LABEL, TRACK_LABEL, pct } from "./format";

const field = "forge-field";
const STATUS_ICON = { pending: Circle, in_progress: CircleDashed, completed: CheckCircle2, unavailable: CircleSlash, skipped: CircleSlash } as const;
const STATUS_TEXT = { pending: "Not started", in_progress: "In progress", completed: "Completed", unavailable: "Unavailable", skipped: "Skipped" } as const;

function useCountdown(view: AttemptView, onExpire: () => void) {
  // Offset between the server clock and this browser, measured at load: the deadline is the server's.
  const [offset] = useState(() => new Date(view.server_time).getTime() - Date.now());
  const deadline = view.deadline_at ? new Date(view.deadline_at).getTime() : null;
  const [left, setLeft] = useState<number | null>(() => (deadline ? deadline - (Date.now() + offset) : null));
  const fired = useRef(false);
  useEffect(() => {
    if (!deadline || view.status !== "in_progress") return;
    const t = setInterval(() => {
      const ms = deadline - (Date.now() + offset);
      setLeft(ms);
      if (ms <= 0 && !fired.current) {
        fired.current = true;
        onExpire();
      }
    }, 1000);
    return () => clearInterval(t);
  }, [deadline, offset, view.status, onExpire]);
  return deadline ? left : null;
}

function fmt(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function AttemptWorkspace({ initial }: { initial: AttemptView }) {
  const [view, setView] = useState(initial);
  const [active, setActive] = useState(initial.sections.find((s) => s.status === "in_progress" || s.status === "pending")?.key ?? initial.sections[0]?.key);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmFinal, setConfirmFinal] = useState(false);
  const closed = ["finalized", "expired", "abandoned"].includes(view.status);
  const left = useCountdown(view, () => void refresh());

  async function refresh() {
    const r = await fetchCareerAttempt(view.id);
    if (r.ok) setView(r.data);
  }

  async function run<T>(label: string, fn: () => Promise<{ ok: true; data: T } | { ok: false; error: string }>, apply?: (d: T) => void) {
    setBusy(label);
    setError(null);
    const r = await fn();
    setBusy(null);
    if (!r.ok) {
      setError(r.error);
      if (/time is up|ended/i.test(r.error)) await refresh();
      return;
    }
    if (apply) apply(r.data);
  }

  const sec = view.sections.find((s) => s.key === active);
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs text-fg-subtle"><Link href="/career" className="hover:text-fg">FORGE Career</Link> / {TRACK_LABEL[view.track]} · {LEVEL_LABEL[view.level]} · {view.purpose} · template v{view.template.version}</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-fg">{view.title}</h1>
        </div>
        <div className="flex items-center gap-3">
          {left !== null && view.status === "in_progress" ? (
            <p role="timer" aria-live={left < 300000 ? "assertive" : "off"} className={cn("flex items-center gap-1.5 rounded-lg border px-3 py-1.5 font-mono text-sm tabular-nums", left < 600000 ? "border-fg text-fg" : "border-line text-fg-muted")}>
              <Timer className="size-4" aria-hidden="true" />{left > 0 ? fmt(left) : "Time is up"}
            </p>
          ) : view.status === "in_progress" ? <p className="text-xs text-fg-subtle">Untimed</p> : null}
          {closed && view.report_id ? <ButtonLink href={`/career/reports/${view.report_id}`} size="sm">View report</ButtonLink> : null}
        </div>
      </header>
      {error ? <p role="alert" className="rounded-lg border border-line bg-surface-elevated px-3 py-2 text-sm text-fg">{error}</p> : null}

      {view.status === "created" ? (
        <div className="rounded-xl border border-line bg-surface p-6">
          <p className="text-sm text-fg">Ready when you are.</p>
          <p className="mt-1 max-w-2xl text-sm text-fg-muted">
            {view.time_limit_minutes ? `Starting begins a ${view.time_limit_minutes}-minute server-side clock. It keeps running if you close or refresh the page; work after the deadline doesn't count.` : "This assessment is untimed."}
            {" "}Formal feedback is shown after you finalize.
          </p>
          <Button className="mt-4" onClick={() => void run("start", () => careerAttemptAction({ attemptId: view.id, action: "start" }), () => void refresh())} disabled={busy !== null}>
            {busy === "start" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Play aria-hidden="true" />}Start assessment
          </Button>
        </div>
      ) : null}

      {view.status !== "created" ? (
        <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <nav aria-label="Sections">
            <ol className="flex flex-col gap-1">
              {view.sections.map((s) => {
                const Icon = STATUS_ICON[s.status];
                return (
                  <li key={s.key}>
                    <button type="button" onClick={() => setActive(s.key)} aria-current={active === s.key ? "step" : undefined}
                      className={cn("flex w-full items-start gap-2 rounded-lg border px-3 py-2 text-left", active === s.key ? "border-fg bg-surface-elevated" : "border-line hover:bg-surface-hover")}>
                      <Icon className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
                      <span className="min-w-0"><span className="block text-[13px] text-fg">{s.title}</span>
                        <span className="text-[11px] text-fg-subtle">{STATUS_TEXT[s.status]} · ~{s.minutes} min</span></span>
                    </button>
                  </li>
                );
              })}
            </ol>
            {!closed ? (
              <div className="mt-4 flex flex-col gap-2">
                <Button variant={confirmFinal ? "primary" : "secondary"} size="sm" disabled={busy !== null}
                  onClick={() => {
                    if (!confirmFinal) return setConfirmFinal(true);
                    void run("finalize", () => careerAttemptAction({ attemptId: view.id, action: "finalize" }), () => void refresh());
                  }}>
                  {busy === "finalize" ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
                  {confirmFinal ? "Confirm: finalize and score" : "Finalize assessment"}
                </Button>
                {confirmFinal ? <p className="text-[11px] text-fg-subtle">Unstarted sections are recorded as skipped. This can&apos;t be undone.</p> : null}
              </div>
            ) : <p className="mt-4 text-xs text-fg-muted">This assessment has {view.status === "expired" ? "expired (finalized at the deadline)" : view.status}.</p>}
          </nav>
          {sec ? (
            <SectionPanel key={sec.key + view.revision} sec={sec} attemptId={view.id} closed={closed} busy={busy}
              onStart={() => void run(`s:${sec.key}`, () => careerSectionAction({ attemptId: view.id, key: sec.key, action: "start" }), setView)}
              onComplete={() => void run(`c:${sec.key}`, () => careerSectionAction({ attemptId: view.id, key: sec.key, action: "complete" }), setView)}
              onView={setView} onError={setError} formal={view.purpose === "formal"} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SectionPanel({ sec, attemptId, closed, busy, onStart, onComplete, onView, onError, formal }: {
  sec: AttemptSection; attemptId: string; closed: boolean; busy: string | null; formal: boolean;
  onStart: () => void; onComplete: () => void; onView: (v: AttemptView) => void; onError: (e: string | null) => void;
}) {
  const link = sec.link as Record<string, unknown>;
  const urls: [string, string][] = [];
  if (typeof link.url === "string") urls.push([String(link.url), `Open in ${KIND_LABEL[sec.kind]}`]);
  if (link.urls && typeof link.urls === "object") for (const [k, v] of Object.entries(link.urls as Record<string, string>)) urls.push([v, `Open challenge: ${k}`]);
  const repeated = (Array.isArray(link.repeated) ? link.repeated.length : link.repeated) ? true : false;
  return (
    <section aria-label={sec.title} className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-5">
      <header>
        <p className="text-xs text-fg-subtle">{KIND_LABEL[sec.kind]} · weight {sec.weight}{sec.critical ? " · critical section" : ""}</p>
        <h2 className="text-lg font-medium text-fg">{sec.title}</h2>
        <p className="mt-1 text-[13px] text-fg-muted">{sec.objectives.map((o) => o.replace(/[.\s]*$/, ".")).join(" ")}</p>
        <p className="mt-1 text-xs text-fg-subtle">Competencies: {sec.dimensions.join(", ")}</p>
      </header>

      {sec.status === "pending" && !closed ? (
        <div>
          <Button onClick={onStart} disabled={busy !== null}>{busy === `s:${sec.key}` ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Play aria-hidden="true" />}Start section</Button>
          <p className="mt-2 text-xs text-fg-subtle">Starting creates the activity in the relevant FORGE lab. Only work done after this point and before the deadline counts.</p>
        </div>
      ) : null}

      {sec.status === "unavailable" ? (
        <p className="rounded-lg border border-dashed border-line p-3 text-[13px] text-fg-muted">{String(link.reason ?? "This section is unavailable.")}</p>
      ) : null}

      {sec.status !== "pending" && sec.status !== "unavailable" ? (
        <div className="flex flex-col gap-3">
          {urls.length ? (
            <ul className="flex flex-wrap gap-2">
              {urls.map(([href, label]) => (
                <li key={href}><a href={href} target="_blank" rel="noopener" className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[13px] text-fg hover:bg-surface-hover">
                  {label}<ExternalLink className="size-3.5" aria-hidden="true" /></a></li>
              ))}
            </ul>
          ) : null}
          {Array.isArray(link.instructions) ? (
            <ol className="list-decimal pl-5 text-[13px] text-fg">{(link.instructions as string[]).map((x) => <li key={x}>{x}</li>)}</ol>
          ) : null}
          {typeof link.formal_rules === "string" ? <p className="text-xs text-fg-subtle">{String(link.formal_rules)}</p> : null}
          {typeof link.constraint_change === "string" ? <p className="text-xs text-fg-muted">Changed constraint for this exercise: <span className="font-mono text-fg">{String(link.constraint_change)}</span></p> : null}
          {repeated ? <p className="text-xs text-fg-muted">FORGE had no unseen alternative for part of this section, so some content repeats something you&apos;ve seen. This is noted in the report.</p> : null}
          {sec.items.map((it) => <ItemEditor key={it.slug} item={it} sec={sec} attemptId={attemptId} closed={closed || sec.status !== "in_progress"} onView={onView} onError={onError} formal={formal} />)}
          {sec.status === "in_progress" && !closed ? (
            <div className="flex items-center gap-3 border-t border-line-subtle pt-3">
              <Button variant="secondary" onClick={onComplete} disabled={busy !== null}>
                {busy === `c:${sec.key}` ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}Mark section complete
              </Button>
              <span className="text-xs text-fg-subtle">Records the results produced so far in this section.</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {sec.result && !("recorded" in sec.result) ? <ResultView result={sec.result} /> : sec.result ? <p className="text-xs text-fg-subtle">Results recorded. They are shown after you finalize.</p> : null}
    </section>
  );
}

function ResultView({ result }: { result: Record<string, unknown> }) {
  const r = result as { score?: number | null; evidence?: string; unavailable?: boolean; skipped?: boolean; note?: string };
  if (r.skipped) return <p className="text-xs text-fg-subtle">Skipped: no evidence recorded.</p>;
  if (r.unavailable) return null;
  return (
    <div className="rounded-lg border border-line-subtle bg-canvas p-3 text-[13px]">
      <p className="text-fg">Section result: <span className="font-mono">{pct(r.score ?? null)}</span> <span className="text-xs text-fg-subtle">· {r.evidence}</span></p>
      {r.note ? <p className="mt-1 text-xs text-fg-muted">{r.note}</p> : null}
    </div>
  );
}

function ItemEditor({ item, sec, attemptId, closed, onView, onError, formal }: {
  item: CareerItem; sec: AttemptSection; attemptId: string; closed: boolean; formal: boolean;
  onView: (v: AttemptView) => void; onError: (e: string | null) => void;
}) {
  const id = useId();
  const key = `forge:career:${attemptId}:${sec.key}:${item.slug}`;
  const [draft, setDraft] = useState(() => {
    try { return window.localStorage.getItem(key) ?? ""; } catch { return ""; }
  });
  const [busy, setBusy] = useState(false);
  const client = useRef<string | null>(null);
  const resp = item.response;
  const locked = closed || (resp && resp.status !== "ungraded");

  async function submit() {
    setBusy(true);
    onError(null);
    client.current ??= crypto.randomUUID();
    const r = await careerRespond({ attemptId, key: sec.key, item: item.slug, content: draft, clientId: client.current });
    setBusy(false);
    if (!r.ok) {
      client.current = null;
      return onError(r.error);
    }
    try { window.localStorage.removeItem(key); } catch {}
    onView(r.data);
  }

  return (
    <article className="flex flex-col gap-2 rounded-lg border border-line p-4">
      <h3 className="text-sm font-medium text-fg">{item.title}</h3>
      {item.context ? <p className="text-[13px] text-fg-muted">{item.context}</p> : null}
      {item.summary ? <p className="text-[13px] text-fg-muted">{item.summary}</p> : null}
      {item.prompt ? <div className="text-[13px] text-fg"><MessageText text={item.prompt} /></div> : null}
      {item.requirements ? <ul className="list-disc pl-4 text-[13px] text-fg">{item.requirements.map((x) => <li key={x}>{x}</li>)}</ul> : null}
      {item.criteria ? <p className="text-xs text-fg-subtle">Assessed on: {item.criteria.join(" · ")}</p> : null}
      {resp && resp.status !== "ungraded" ? (
        <div className="rounded-md bg-canvas p-3 text-[13px]">
          <p className="mb-1 text-[11px] text-fg-subtle">Your answer ({resp.status === "pending" ? "being evaluated" : "submitted"})</p>
          <p className="whitespace-pre-wrap text-fg">{resp.content}</p>
          {resp.score !== null ? <p className="mt-2 text-xs text-fg-muted">AI evaluation (advisory): {pct(resp.score)}{resp.eligible === false ? " · not counted as evidence" : ""}</p>
            : formal ? <p className="mt-2 text-xs text-fg-subtle">Feedback is withheld until the assessment is finalized.</p> : null}
        </div>
      ) : null}
      {resp?.status === "ungraded" ? <p className="text-xs text-fg-muted">The evaluation couldn&apos;t be completed ({resp.error_code}). No score was recorded; you can submit again.</p> : null}
      {!locked ? (
        <>
          <label htmlFor={`${id}-a`} className="sr-only">Your answer to {item.title}</label>
          <textarea id={`${id}-a`} className={`${field} min-h-40 resize-y`} maxLength={20000} value={draft}
            onChange={(e) => { setDraft(e.target.value); client.current = null; try { window.localStorage.setItem(key, e.target.value); } catch {} }}
            placeholder="Explain your decision, the alternatives you considered, the risks, and how you would communicate it." />
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={() => void submit()} disabled={busy || draft.trim().length < 40}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}{busy ? "Submitting…" : "Submit answer"}
            </Button>
            <span className="text-[11px] text-fg-subtle">Draft saved in this browser. One submission per item in formal assessments.</span>
          </div>
        </>
      ) : null}
    </article>
  );
}
