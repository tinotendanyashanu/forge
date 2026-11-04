"use client";

import { Camera, EyeOff, Lightbulb, LoaderCircle, RefreshCw, RotateCcw, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  createSnapshot,
  fetchDiff,
  fetchExerciseResponses,
  fetchHistory,
  fetchSnapshots,
  fetchSubmission,
  fetchSubmissions,
  requestSubmissionReview,
  submitExerciseResponse,
} from "@/app/workspace/actions";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/rich-text";
import type {
  EngJob,
  ExerciseResponse,
  FileDiff,
  HistoryEvent,
  ReviewMode,
  Snapshot,
  SubmissionDetail,
  SubmissionSummary,
  WorkspaceDetail,
} from "@/lib/workspace-types";
import { REVIEW_MODES } from "@/lib/workspace-types";

import { PassBadge, VerifiedBadge } from "./badges";
import { DiffView } from "./diff-view";
import { Markdown } from "./markdown";
import { ReviewCard } from "./review-card";
import { EngTestResults } from "./test-results";
import { formatDistanceShort } from "./time";

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-[11px] font-medium tracking-wide text-fg-subtle uppercase">{children}</h3>;
}

function Alert({ text }: { text: string | null }) {
  return text ? <p role="alert" className="rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-fg">{text}</p> : null;
}

// ------------------------------------------------------------------ ticket

export function TicketPanel({ ws, hints, onHint }: { ws: WorkspaceDetail; hints: string[]; onHint: () => void }) {
  const p = ws.project;
  const t = p.ticket;
  return (
    <div className="flex flex-col gap-5">
      <section aria-labelledby="ticket-title">
        <p className="font-mono text-[11px] text-fg-subtle">{t.key} · {t.type} · {t.priority} · from {t.reporter}</p>
        <h2 id="ticket-title" className="mt-1 text-[15px] font-medium text-fg">{t.title}</h2>
        <div className="mt-3"><Markdown text={t.body} /></div>
      </section>
      <section aria-labelledby="ac-heading">
        <h3 id="ac-heading" className="mb-2 text-[13px] font-medium text-fg">Acceptance criteria</h3>
        <ol className="ml-5 list-decimal space-y-1.5 text-[13px] leading-relaxed text-fg-muted">
          {t.acceptance_criteria.map((c) => <li key={c}><Markdown text={c} className="inline" /></li>)}
        </ol>
      </section>
      <details className="group rounded-lg border border-line-subtle px-3 py-2">
        <summary className="cursor-pointer text-[13px] text-fg">Background</summary>
        <div className="mt-2"><Markdown text={p.description} /></div>
      </details>
      <details className="group rounded-lg border border-line-subtle px-3 py-2">
        <summary className="cursor-pointer text-[13px] text-fg">Architecture</summary>
        <div className="mt-2"><Markdown text={p.architecture} /></div>
      </details>
      <details className="group rounded-lg border border-line-subtle px-3 py-2">
        <summary className="cursor-pointer text-[13px] text-fg">Setup and running tests</summary>
        <div className="mt-2"><Markdown text={p.setup} /></div>
      </details>
      <section aria-labelledby="hints-heading">
        <div className="mb-2 flex items-center justify-between">
          <h3 id="hints-heading" className="text-[13px] font-medium text-fg">Hints</h3>
          <Button size="sm" variant="ghost" onClick={onHint} disabled={hints.length >= ws.hint_count}>
            <Lightbulb aria-hidden="true" />Reveal ({ws.hint_count - hints.length} left)
          </Button>
        </div>
        {hints.length ? (
          <ol className="flex flex-col gap-2">
            {hints.map((h, i) => <li key={h} className="rounded-lg border border-line-subtle bg-surface px-3 py-2 text-[13px] text-fg"><span className="text-fg-subtle">{i + 1}. </span><Markdown text={h} className="inline" /></li>)}
          </ol>
        ) : <p className="text-[12px] text-fg-subtle">Using more than one hint means a pass doesn&apos;t count as a clean success for mastery.</p>}
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ tests

export function TestsPanel({ ws, job, pending }: { ws: WorkspaceDetail; job: EngJob | null; pending: boolean }) {
  const p = ws.project;
  return (
    <div className="flex flex-col gap-5">
      <section aria-live="polite">
        <div className="mb-2 flex items-center justify-between gap-2">
          <Heading>{job ? (job.kind === "run" ? "Public test run" : "Submission") : "Results"}</Heading>
          {job?.status === "completed" && job.total !== null ? <PassBadge passed={job.passed ?? 0} total={job.total} /> : null}
        </div>
        {!job ? (
          <p className="rounded-xl border border-dashed border-line px-4 py-5 text-center text-[13px] text-fg-muted">
            Run the public tests while you work. Submit to run every test, including hidden ones.
          </p>
        ) : job.status === "queued" || job.status === "running" || pending ? (
          <p className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-3 text-[13px] text-fg-muted">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {job.status === "queued" ? "Queued for the sandbox…" : "Running in the sandbox…"}
          </p>
        ) : job.status !== "completed" ? (
          <p role="alert" className="rounded-xl border border-line bg-surface px-3 py-3 text-[13px] text-fg">{job.error_message ?? "The job could not be completed."}</p>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-[11px] text-fg-subtle">
              Snapshot #{job.snapshot_number} ·{" "}
              {job.sandbox_verified ? "executed in the verified sandbox" : job.backend === "mock" ? "mock runner: nothing executed" : "not verified"}
            </p>
            <EngTestResults results={job.results} />
          </div>
        )}
      </section>
      <section>
        <Heading>Public tests ({p.public_tests})</Heading>
        <ul className="flex flex-col gap-1 text-[13px] text-fg-muted">
          {p.public_tests_detail.map((t) => <li key={t.name}>{t.name} <span className="text-[11px] text-fg-subtle">· {t.suite}</span></li>)}
        </ul>
        {Object.entries(p.public_check_sources).map(([suite, src]) => (
          <details key={suite} className="mt-2 rounded-lg border border-line-subtle px-3 py-2">
            <summary className="cursor-pointer text-[12px] text-fg">Public {suite} test driver</summary>
            <div className="mt-2"><CodeBlock code={src} language={suite === "python" ? "python" : "javascript"} /></div>
          </details>
        ))}
      </section>
      <section>
        <Heading>Hidden tests ({p.hidden_tests})</Heading>
        <p className="mb-2 flex items-center gap-1.5 text-[12px] text-fg-subtle"><EyeOff className="size-3.5" aria-hidden="true" />Names only. Inputs and expected values stay on the server.</p>
        <ul className="flex flex-col gap-1 text-[13px] text-fg-muted">
          {p.hidden_test_names.map((n) => <li key={n}>{n}</li>)}
        </ul>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ changes

export function ChangesPanel({ ws, refreshKey, snapshots }: { ws: WorkspaceDetail; refreshKey: number; snapshots: Snapshot[] }) {
  const [against, setAgainst] = useState<number | null>(null);
  const [diffs, setDiffs] = useState<FileDiff[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetchDiff({ workspaceId: ws.id, against });
    if (res.ok) {
      setDiffs(res.data);
      setError(null);
    } else setError(res.error);
  }, [ws.id, against]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on open and after saves
    void load();
  }, [load, refreshKey]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-[12px] text-fg-subtle">
          Compare with
          <select
            value={against ?? ""}
            onChange={(e) => setAgainst(e.target.value ? Number(e.target.value) : null)}
            className="h-8 rounded-md border border-line bg-canvas px-2 text-[13px] text-fg"
          >
            <option value="">Original project (v{ws.version})</option>
            {snapshots.map((s) => <option key={s.number} value={s.number}>Snapshot #{s.number}{s.label ? ` · ${s.label}` : ""}</option>)}
          </select>
        </label>
        <Button size="sm" variant="ghost" onClick={() => void load()}><RefreshCw aria-hidden="true" />Refresh</Button>
      </div>
      <p className="text-[11px] text-fg-subtle">Shows saved changes. Unsaved edits appear after autosave.</p>
      <Alert text={error} />
      {diffs === null ? <p className="text-[13px] text-fg-subtle">Loading changes…</p> : <DiffView diffs={diffs} emptyText="No changes yet." />}
    </div>
  );
}

// ------------------------------------------------------------------ history

const KIND: Record<Snapshot["kind"], string> = { manual: "Snapshot", run: "Test run", submission: "Submission", pull_request: "Pull request" };
const ACTION: Record<string, string> = {
  "workspace.created": "Workspace created", "file.created": "Created", "file.updated": "Saved", "file.deleted": "Deleted",
  "snapshot.created": "Snapshot", "snapshot.restored": "Restored snapshot", "workspace.reset": "Reset to original",
  "job.run": "Ran public tests", "job.submit": "Submitted", "hint.revealed": "Revealed a hint", "review.requested": "AI review",
  "pr.opened": "Opened pull request", "pr.revision": "Pushed revision", "pr.decided": "Requested decision", "pr.closed": "Closed pull request",
  "exercise.submitted": "Collaboration exercise",
};

export function HistoryPanel({
  ws,
  snapshots,
  onSnapshotsChange,
  onRestore,
  onReviewSubmission,
  refreshKey,
}: {
  ws: WorkspaceDetail;
  snapshots: Snapshot[];
  onSnapshotsChange: (s: Snapshot[]) => void;
  onRestore: (n: number) => Promise<void>;
  onReviewSubmission: (id: string) => void;
  refreshKey: number;
}) {
  const [label, setLabel] = useState("");
  const [subs, setSubs] = useState<SubmissionSummary[]>([]);
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    void Promise.all([fetchSnapshots(ws.id), fetchSubmissions(ws.id), fetchHistory(ws.id)]).then(([s, sub, h]) => {
      if (!live) return;
      if (s.ok) onSnapshotsChange(s.data);
      if (sub.ok) setSubs(sub.data);
      if (h.ok) setEvents(h.data);
    });
    return () => { live = false; };
  }, [ws.id, refreshKey, onSnapshotsChange]);

  async function snap(e: React.FormEvent) {
    e.preventDefault();
    const res = await createSnapshot({ workspaceId: ws.id, label: label.trim() || null });
    if (!res.ok) return setError(res.error);
    setLabel("");
    setError(null);
    onSnapshotsChange([res.data, ...snapshots]);
  }

  return (
    <div className="flex flex-col gap-5">
      <section>
        <Heading>Attempts</Heading>
        {subs.length ? (
          <ul className="divide-y divide-line-subtle rounded-xl border border-line">
            {subs.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div className="text-[13px] text-fg">
                  Attempt {s.number}
                  <span className="ml-2 text-[11px] text-fg-subtle">{formatDistanceShort(s.created_at)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <PassBadge passed={s.passed} total={s.total} />
                  <VerifiedBadge verified={s.verified} executed={s.executed} />
                  <Button size="sm" variant="ghost" onClick={() => onReviewSubmission(s.id)}>Review</Button>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="text-[13px] text-fg-subtle">No submissions yet.</p>}
      </section>
      <section>
        <Heading>Snapshots</Heading>
        <form onSubmit={snap} className="mb-3 flex gap-2">
          <label htmlFor="snap-label" className="sr-only">Snapshot label</label>
          <input id="snap-label" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} placeholder="Label (optional)"
            className="h-8 min-w-0 flex-1 rounded-md border border-line bg-canvas px-2 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none" />
          <Button type="submit" size="sm" variant="secondary"><Camera aria-hidden="true" />Snapshot</Button>
        </form>
        <Alert text={error} />
        <ul className="flex flex-col gap-1">
          {snapshots.map((s) => (
            <li key={s.number} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-[13px] hover:bg-surface">
              <span className="min-w-0 truncate text-fg-muted">
                <span className="text-fg">#{s.number}</span> {KIND[s.kind]}{s.label ? ` · ${s.label}` : ""}
                <span className="ml-2 text-[11px] text-fg-subtle">{s.files_changed} files changed · {formatDistanceShort(s.created_at)}</span>
              </span>
              {confirm === s.number ? (
                <span className="flex shrink-0 gap-1">
                  <Button size="sm" variant="secondary" onClick={async () => { setConfirm(null); await onRestore(s.number); }}>Restore</Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
                </span>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirm(s.number)} aria-label={`Restore snapshot ${s.number}`}><RotateCcw aria-hidden="true" /></Button>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <Heading>Implementation history</Heading>
        <ol className="flex flex-col gap-1 text-[12.5px]">
          {events.slice(0, 60).map((e, i) => (
            <li key={i} className="flex justify-between gap-3 text-fg-muted">
              <span className="min-w-0 truncate">
                {ACTION[e.action] ?? e.action}
                {typeof e.detail.path === "string" ? <span className="ml-1 font-mono text-[11.5px] text-fg-subtle">{e.detail.path}</span> : null}
              </span>
              <span className="shrink-0 text-[11px] text-fg-subtle">{formatDistanceShort(e.at)}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ review

export function ReviewPanel({
  ws,
  submissionId,
  llmConfigured,
  onJump,
}: {
  ws: WorkspaceDetail;
  submissionId: string | null;
  llmConfigured: boolean;
  onJump: (path: string, line: number | null) => void;
}) {
  const [sub, setSub] = useState<SubmissionDetail | null>(null);
  const [mode, setMode] = useState<ReviewMode>("senior");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!submissionId) return;
    let live = true;
    void fetchSubmission(submissionId).then((res) => {
      if (!live) return;
      if (res.ok) setSub(res.data);
      else setError(res.error);
    });
    return () => { live = false; };
  }, [submissionId]);

  if (!submissionId) {
    return <p className="rounded-xl border border-dashed border-line px-4 py-5 text-center text-[13px] text-fg-muted">Submit your changes first. An AI review looks at a submitted attempt and its real test results.</p>;
  }

  async function request() {
    if (!sub) return;
    setBusy(true);
    setError(null);
    const res = await requestSubmissionReview({ submissionId: sub.id, mode });
    setBusy(false);
    if (!res.ok) return setError(res.error);
    const fresh = await fetchSubmission(sub.id);
    if (fresh.ok) setSub(fresh.data);
  }

  return (
    <div className="flex flex-col gap-4">
      {sub ? (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-fg">
          Attempt {sub.number}
          <PassBadge passed={sub.passed} total={sub.total} />
          <VerifiedBadge verified={sub.verified} executed={sub.executed} />
        </div>
      ) : null}
      <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-3">
        <fieldset>
          <legend className="mb-2 text-[12px] text-fg-subtle">Reviewer</legend>
          <div className="grid gap-1.5">
            {REVIEW_MODES.map((m) => (
              <label key={m.value} className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1 text-[13px] hover:bg-surface-hover">
                <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} className="mt-1 accent-white" />
                <span><span className="text-fg">{m.label}</span><span className="block text-[11.5px] text-fg-subtle">{m.description}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        <Button size="sm" onClick={request} disabled={busy || !llmConfigured || !sub}>
          {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
          {busy ? "Reviewing…" : "Request AI review"}
        </Button>
        {!llmConfigured ? <p className="text-[11.5px] text-fg-subtle">No AI provider is configured on this server.</p> : null}
        <p className="text-[11px] text-fg-subtle">Reviews are advisory. Only tests decide correctness, and reviews are never mastery evidence.</p>
      </div>
      <Alert text={error} />
      {sub?.reviews.slice().reverse().map((r) => <ReviewCard key={r.id} review={r} onJump={onJump} />)}
      {sub?.reference_diff ? (
        <details className="rounded-xl border border-line px-3 py-2">
          <summary className="cursor-pointer text-[13px] text-fg">Reference solution (unlocked: every test passed)</summary>
          <p className="my-2 text-[12px] text-fg-muted">One possible solution. Compare its trade-offs with yours.</p>
          <DiffView diffs={sub.reference_diff} defaultOpen={false} />
          {sub.misconceptions?.length ? (
            <ul className="mt-3 ml-5 list-disc space-y-1 text-[12.5px] text-fg-muted">{sub.misconceptions.map((m) => <li key={m}>{m}</li>)}</ul>
          ) : null}
        </details>
      ) : null}
      {ws.project.rubric.length ? (
        <details className="rounded-xl border border-line-subtle px-3 py-2">
          <summary className="cursor-pointer text-[12px] text-fg-muted">Review rubric ({ws.project.rubric_version})</summary>
          <ol className="mt-2 ml-5 list-decimal space-y-1 text-[12.5px] text-fg-muted">{ws.project.rubric.map((r) => <li key={r}>{r}</li>)}</ol>
        </details>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ collaboration

const EX_KIND: Record<string, string> = {
  requirement_change: "Requirement change", clarify_requirements: "Clarify requirements", review_junior_code: "Code review",
  stakeholder_explanation: "Stakeholder update", implementation_plan: "Implementation plan", estimate: "Estimate",
  adr: "Architecture decision record", deployment_plan: "Deployment and rollback plan",
};

export function CollaboratePanel({ ws, llmConfigured }: { ws: WorkspaceDetail; llmConfigured: boolean }) {
  const [responses, setResponses] = useState<ExerciseResponse[]>([]);
  useEffect(() => {
    let live = true;
    void fetchExerciseResponses(ws.id).then((r) => { if (live && r.ok) setResponses(r.data); });
    return () => { live = false; };
  }, [ws.id]);

  if (!ws.project.exercises.length) return <p className="text-[13px] text-fg-subtle">This project has no collaboration exercises.</p>;
  return (
    <div className="flex flex-col gap-5">
      <p className="text-[12px] text-fg-subtle">
        Simulated workplace scenarios. They are reviewed by AI against a rubric, are advisory, and are not evidence of real
        employment experience.
      </p>
      {ws.project.exercises.map((ex) => (
        <ExerciseCard key={ex.slug} ws={ws} exercise={ex} llmConfigured={llmConfigured}
          responses={responses.filter((r) => r.exercise_slug === ex.slug)}
          onNew={(r) => setResponses((all) => [r, ...all])} />
      ))}
    </div>
  );
}

function ExerciseCard({
  ws,
  exercise,
  responses,
  onNew,
  llmConfigured,
}: {
  ws: WorkspaceDetail;
  exercise: WorkspaceDetail["project"]["exercises"][number];
  responses: ExerciseResponse[];
  onNew: (r: ExerciseResponse) => void;
  llmConfigured: boolean;
}) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clientId, setClientId] = useState(() => crypto.randomUUID());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await submitExerciseResponse({ workspaceId: ws.id, slug: exercise.slug, body, clientId });
    setBusy(false);
    if (!res.ok) return setError(res.error);
    onNew(res.data);
    setBody("");
    setClientId(crypto.randomUUID());
  }

  const latest = responses[0];
  return (
    <section className="rounded-xl border border-line bg-surface p-3" aria-labelledby={`ex-${exercise.slug}`}>
      <p className="text-[11px] text-fg-subtle">{EX_KIND[exercise.kind] ?? exercise.kind}</p>
      <h3 id={`ex-${exercise.slug}`} className="text-[14px] font-medium text-fg">{exercise.title}</h3>
      <div className="mt-2"><Markdown text={exercise.prompt} /></div>
      <details className="mt-2">
        <summary className="cursor-pointer text-[12px] text-fg-muted">What reviewers look for</summary>
        <ul className="mt-1 ml-5 list-disc space-y-1 text-[12px] text-fg-muted">{exercise.rubric.map((r) => <li key={r}>{r}</li>)}</ul>
      </details>
      <form onSubmit={submit} className="mt-3 flex flex-col gap-2">
        <label htmlFor={`ex-body-${exercise.slug}`} className="sr-only">Your response</label>
        <textarea id={`ex-body-${exercise.slug}`} value={body} onChange={(e) => setBody(e.target.value)} rows={6} maxLength={12000}
          placeholder="Write your response…"
          className="w-full resize-y rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] leading-relaxed text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none" />
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-fg-subtle tabular-nums">{body.trim().length} / 40 minimum</span>
          <Button type="submit" size="sm" disabled={busy || body.trim().length < 40 || !llmConfigured}>
            {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            {busy ? "Reviewing…" : "Submit for review"}
          </Button>
        </div>
      </form>
      <Alert text={error} />
      {latest ? (
        <div className="mt-3 rounded-lg border border-line-subtle bg-canvas p-3 text-[13px]">
          {latest.status === "evaluated" && latest.evaluation ? (
            <>
              <p className="text-fg">Score {Math.round((latest.score ?? 0) * 100)}% {latest.eligible ? "" : "· low confidence, not counted"}</p>
              <p className="mt-1 text-fg-muted">{latest.evaluation.summary}</p>
              <ul className="mt-2 flex flex-col gap-1.5">
                {latest.evaluation.criteria.map((c) => (
                  <li key={c.criterion} className="text-[12.5px] text-fg-muted">
                    <span className="text-fg">{c.score}/{c.max_score}</span> {c.description}
                    {c.evidence_status === "inferred" ? <span className="text-fg-subtle"> (credit not supported by a quote; not counted)</span> : null}
                  </li>
                ))}
              </ul>
              {latest.evaluation.follow_up_questions.length ? (
                <p className="mt-2 text-[12.5px] text-fg">Follow-up: {latest.evaluation.follow_up_questions[0]}</p>
              ) : null}
            </>
          ) : (
            <p className="text-fg-muted">Review unavailable ({latest.error_code?.replaceAll("_", " ") ?? "pending"}). Your answer was saved.</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
