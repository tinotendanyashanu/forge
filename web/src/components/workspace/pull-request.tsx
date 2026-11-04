"use client";

import {
  ArrowLeft,
  Bot,
  CircleCheck,
  CircleDashed,
  GitMerge,
  GitPullRequestArrow,
  LoaderCircle,
  MessageSquareReply,
  Send,
  UserRound,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  addPrComment,
  closePullRequest,
  decidePullRequest,
  fetchPullRequest,
  pushRevision,
  reviewPullRequest,
} from "@/app/workspace/actions";
import { Button, ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { PrComment, PullRequestDetail, ReviewMode, WorkspaceStatus } from "@/lib/workspace-types";
import { REVIEW_MODES } from "@/lib/workspace-types";

import { PassBadge, PrStatusBadge, VerifiedBadge } from "./badges";
import { DiffView } from "./diff-view";
import { Inline, Markdown } from "./markdown";
import { ReviewCard } from "./review-card";
import { EngTestResults } from "./test-results";
import { formatDistanceShort } from "./time";

type Tab = "conversation" | "files" | "checks" | "decision";
const OPEN = new Set(["open", "changes_requested"]);

export function PullRequestView({ initial, status }: { initial: PullRequestDetail; status: WorkspaceStatus | null }) {
  const [pr, setPr] = useState(initial);
  const [tab, setTab] = useState<Tab>("conversation");
  const [error, setError] = useState<string | null>(null);
  const latest = pr.revision_list[pr.revision_list.length - 1];
  const running = latest.job.status === "queued" || latest.job.status === "running";
  const open = OPEN.has(pr.status);
  const llmConfigured = Boolean(status?.llm.configured);

  const reload = useCallback(async () => {
    const res = await fetchPullRequest(pr.id);
    if (res.ok) setPr(res.data);
    return res.ok;
  }, [pr.id]);

  // Poll while checks run.
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => void reload(), 1500);
    return () => clearInterval(t);
  }, [running, reload]);

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "conversation", label: "Conversation", count: pr.comments.filter((c) => c.author !== "system").length },
    { id: "files", label: "Files changed", count: pr.diff.length },
    { id: "checks", label: "Checks" },
    { id: "decision", label: "Review decision" },
  ];

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pt-6 pb-16 sm:px-6 lg:px-10">
      <Link href={`/workspace/w/${pr.workspace_id}`} className="mb-4 inline-flex items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden="true" />Back to workspace
      </Link>
      <header className="flex flex-col gap-3 border-b border-line-subtle pb-5">
        <p className="font-mono text-[12px] text-fg-subtle">{pr.ticket.key} · {pr.project_title} · simulated pull request</p>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{pr.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-fg-muted">
          <PrStatusBadge status={pr.status} />
          <span>{pr.revisions} revision{pr.revisions === 1 ? "" : "s"}</span>
          {latest.submission ? (
            <>
              <PassBadge passed={latest.submission.passed} total={latest.submission.total} />
              <VerifiedBadge verified={latest.submission.verified} executed={latest.submission.executed} />
            </>
          ) : running ? (
            <span className="inline-flex items-center gap-1.5"><LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />Checks running</span>
          ) : null}
        </div>
      </header>

      <div role="tablist" aria-label="Pull request" className="mt-4 flex gap-1 overflow-x-auto border-b border-line-subtle">
        {tabs.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            className={cn("shrink-0 border-b-2 px-3 py-2 text-[13px]", tab === t.id ? "border-fg text-fg" : "border-transparent text-fg-muted hover:text-fg")}>
            {t.label}{t.count !== undefined ? <span className="ml-1.5 text-fg-subtle tabular-nums">{t.count}</span> : null}
          </button>
        ))}
      </div>
      {error ? <p role="alert" className="mt-4 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-fg">{error}</p> : null}

      <div className="mt-6" role="tabpanel">
        {tab === "conversation" ? <Conversation pr={pr} open={open} llmConfigured={llmConfigured} running={running} onChange={setPr} onError={setError} reload={reload} /> : null}
        {tab === "files" ? <FilesChanged pr={pr} open={open} reload={reload} onError={setError} /> : null}
        {tab === "checks" ? <Checks pr={pr} /> : null}
        {tab === "decision" ? <Decision pr={pr} open={open} running={running} onChange={setPr} onError={setError} /> : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ conversation

function Avatar({ author }: { author: PrComment["author"] }) {
  const Icon = author === "reviewer" ? Bot : author === "learner" ? UserRound : GitPullRequestArrow;
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-fg-muted">
      <Icon className="size-3.5" aria-hidden="true" />
    </span>
  );
}

const WHO: Record<PrComment["author"], string> = { learner: "You", reviewer: "AI reviewer", system: "FORGE" };
const CATEGORY: Record<string, string> = { proven_failure: "Proven failure", potential_concern: "Potential concern", suggestion: "Suggestion" };

function Conversation({
  pr, open, llmConfigured, running, onChange, onError, reload,
}: {
  pr: PullRequestDetail; open: boolean; llmConfigured: boolean; running: boolean;
  onChange: (p: PullRequestDetail) => void; onError: (e: string | null) => void; reload: () => Promise<boolean>;
}) {
  const [mode, setMode] = useState<ReviewMode>("senior");
  const [busy, setBusy] = useState<"review" | "revision" | null>(null);
  const [note, setNote] = useState("");
  const [revKey, setRevKey] = useState(() => crypto.randomUUID());
  const top = pr.comments.filter((c) => !c.parent_id);
  const replies = useMemo(() => {
    const m = new Map<string, PrComment[]>();
    for (const c of pr.comments) if (c.parent_id) m.set(c.parent_id, [...(m.get(c.parent_id) ?? []), c]);
    return m;
  }, [pr.comments]);
  const unanswered = pr.comments.filter((c) => c.author === "reviewer" && c.kind === "change_request" && !c.answered).length;

  async function review() {
    setBusy("review");
    onError(null);
    const res = await reviewPullRequest({ prId: pr.id, mode });
    setBusy(null);
    if (!res.ok) return onError(res.error);
    if (res.data.status === "ungraded") onError(`The AI review couldn't be completed (${res.data.error_code}). You can retry.`);
    await reload();
  }

  async function revise(e: React.FormEvent) {
    e.preventDefault();
    setBusy("revision");
    onError(null);
    const res = await pushRevision({ prId: pr.id, note, idempotencyKey: revKey });
    setBusy(null);
    if (!res.ok) return onError(res.error);
    onChange(res.data);
    setNote("");
    setRevKey(crypto.randomUUID());
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex flex-col gap-4">
        <article className="rounded-xl border border-line bg-surface p-4">
          <p className="mb-2 text-[12px] text-fg-subtle">Description</p>
          <Markdown text={pr.description} />
        </article>
        <ol className="flex flex-col gap-3" aria-label="Timeline">
          {top.map((c) => (
            <li key={c.id} className="flex gap-3">
              <Avatar author={c.author} />
              <div className="min-w-0 flex-1">
                <CommentBody c={c} />
                {(replies.get(c.id) ?? []).map((r) => (
                  <div key={r.id} className="mt-2 ml-4 flex gap-2">
                    <Avatar author={r.author} />
                    <div className="min-w-0 flex-1"><CommentBody c={r} /></div>
                  </div>
                ))}
                {open && c.author === "reviewer" ? <ReplyBox pr={pr} parent={c} reload={reload} onError={onError} /> : null}
              </div>
            </li>
          ))}
        </ol>
        {open ? <NewComment pr={pr} reload={reload} onError={onError} /> : null}
      </div>

      <aside className="flex flex-col gap-5">
        <section className="rounded-xl border border-line bg-surface p-3">
          <h2 className="mb-2 text-[13px] font-medium text-fg">Request an AI review</h2>
          <label className="sr-only" htmlFor="review-mode">Reviewer</label>
          <select id="review-mode" value={mode} onChange={(e) => setMode(e.target.value as ReviewMode)} disabled={!open}
            className="mb-2 h-9 w-full rounded-md border border-line bg-canvas px-2 text-[13px] text-fg">
            {REVIEW_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
          <p className="mb-2 text-[11.5px] text-fg-subtle">{REVIEW_MODES.find((m) => m.value === mode)?.description}</p>
          <Button size="sm" className="w-full" onClick={review} disabled={!open || running || busy !== null || !llmConfigured}>
            {busy === "review" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Bot aria-hidden="true" />}
            {busy === "review" ? "Reviewing…" : `Review revision ${pr.revision_list.length}`}
          </Button>
          {running ? <p className="mt-2 text-[11.5px] text-fg-subtle">Waiting for checks to finish.</p> : null}
          {!llmConfigured ? <p className="mt-2 text-[11.5px] text-fg-subtle">No AI provider is configured; review is waived for approval.</p> : null}
        </section>
        <section className="rounded-xl border border-line bg-surface p-3">
          <h2 className="mb-1 text-[13px] font-medium text-fg">Push a revision</h2>
          <p className="mb-2 text-[11.5px] text-fg-subtle">Edit in the workspace, then push. Every revision reruns all tests.</p>
          <form onSubmit={revise} className="flex flex-col gap-2">
            <label htmlFor="rev-note" className="sr-only">What changed in this revision</label>
            <textarea id="rev-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} disabled={!open}
              placeholder="What changed since the last revision?"
              className="resize-y rounded-md border border-line bg-canvas px-2 py-1.5 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none" />
            <div className="flex gap-2">
              <Button type="submit" size="sm" variant="secondary" disabled={!open || busy !== null}>
                {busy === "revision" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <GitPullRequestArrow aria-hidden="true" />}
                Push revision
              </Button>
              <ButtonLink href={`/workspace/w/${pr.workspace_id}`} size="sm" variant="ghost">Edit code</ButtonLink>
            </div>
          </form>
        </section>
        {unanswered ? (
          <p className="rounded-lg border border-line px-3 py-2 text-[12.5px] text-fg-muted">
            {unanswered} reviewer request{unanswered === 1 ? "" : "s"} still need{unanswered === 1 ? "s" : ""} a response before approval.
          </p>
        ) : null}
        <section aria-label="AI reviews">
          {pr.reviews.slice().reverse().slice(0, 3).map((r) => <div key={r.id} className="mb-3"><ReviewCard review={r} /></div>)}
        </section>
      </aside>
    </div>
  );
}

function CommentBody({ c }: { c: PrComment }) {
  const needsReply = c.author === "reviewer" && c.kind === "change_request";
  return (
    <div className={cn("rounded-xl border px-3 py-2", c.author === "system" ? "border-line-subtle text-fg-muted" : "border-line bg-surface")}>
      <p className="mb-1 flex flex-wrap items-center gap-x-2 text-[11.5px] text-fg-subtle">
        <span className="text-fg">{WHO[c.author]}</span>
        <span>revision {c.revision_number}</span>
        {c.path ? <span className="font-mono">{c.path}{c.line ? `:${c.line}` : ""}</span> : null}
        {c.category ? <span>{CATEGORY[c.category]}</span> : null}
        {c.severity && c.severity !== "question" ? <span className="uppercase">{c.severity}</span> : null}
        {c.severity === "question" ? <span>Question</span> : null}
        {needsReply ? (
          c.answered ? <span className="inline-flex items-center gap-1"><CircleCheck className="size-3" aria-hidden="true" />answered</span>
            : <span className="inline-flex items-center gap-1 text-fg"><CircleDashed className="size-3" aria-hidden="true" />needs response</span>
        ) : null}
        <span>{formatDistanceShort(c.created_at)}</span>
      </p>
      <div className="text-[13.5px] leading-relaxed text-fg"><Markdown text={c.body} className="flex flex-col gap-2 text-[13.5px] leading-relaxed text-fg" /></div>
    </div>
  );
}

function ReplyBox({ pr, parent, reload, onError }: { pr: PullRequestDetail; parent: PrComment; reload: () => Promise<boolean>; onError: (e: string | null) => void }) {
  const [openBox, setOpenBox] = useState(false);
  const [body, setBody] = useState("");
  const [id, setId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  if (!openBox) {
    return (
      <button type="button" onClick={() => setOpenBox(true)} className="mt-1.5 inline-flex items-center gap-1 rounded-md px-1 text-[12px] text-fg-muted hover:text-fg">
        <MessageSquareReply className="size-3.5" aria-hidden="true" />Respond
      </button>
    );
  }
  return (
    <form className="mt-2 flex flex-col gap-2" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      const res = await addPrComment({ prId: pr.id, body, parentId: parent.id, clientId: id });
      setBusy(false);
      if (!res.ok) return onError(res.error);
      setBody("");
      setId(crypto.randomUUID());
      setOpenBox(false);
      await reload();
    }}>
      <label htmlFor={`reply-${parent.id}`} className="sr-only">Your response</label>
      <textarea id={`reply-${parent.id}`} autoFocus value={body} onChange={(e) => setBody(e.target.value)} rows={3} maxLength={4000} required
        placeholder="Explain what you changed, or why you disagree."
        className="resize-y rounded-md border border-line bg-canvas px-2 py-1.5 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none" />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy || !body.trim()}><Send aria-hidden="true" />Respond</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpenBox(false)}>Cancel</Button>
      </div>
    </form>
  );
}

function NewComment({ pr, reload, onError, path, line, onDone }: {
  pr: PullRequestDetail; reload: () => Promise<boolean>; onError: (e: string | null) => void;
  path?: string; line?: number; onDone?: () => void;
}) {
  const [body, setBody] = useState("");
  const [id, setId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  return (
    <form className="flex flex-col gap-2" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      const res = await addPrComment({ prId: pr.id, body, path: path ?? null, line: line ?? null, clientId: id });
      setBusy(false);
      if (!res.ok) return onError(res.error);
      setBody("");
      setId(crypto.randomUUID());
      onDone?.();
      await reload();
    }}>
      <label htmlFor={`c-${path ?? "pr"}-${line ?? 0}`} className="text-[12px] text-fg-subtle">
        {path ? `Comment on ${path}:${line}` : "Add a comment"}
      </label>
      <textarea id={`c-${path ?? "pr"}-${line ?? 0}`} value={body} onChange={(e) => setBody(e.target.value)} rows={3} maxLength={4000} required autoFocus={!!path}
        className="resize-y rounded-md border border-line bg-canvas px-2 py-1.5 text-[13px] text-fg focus:border-neutral-500 focus:outline-none" />
      <div className="flex gap-2">
        <Button type="submit" size="sm" variant="secondary" disabled={busy || !body.trim()}>Comment</Button>
        {onDone ? <Button size="sm" variant="ghost" onClick={onDone}>Cancel</Button> : null}
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ files

function FilesChanged({ pr, open, reload, onError }: { pr: PullRequestDetail; open: boolean; reload: () => Promise<boolean>; onError: (e: string | null) => void }) {
  const [view, setView] = useState<"all" | number>("all");
  const [composer, setComposer] = useState<{ path: string; line: number } | null>(null);
  const diffs = view === "all" ? pr.diff : pr.revision_list.find((r) => r.number === view)?.diff_from_previous ?? [];
  const byLine = useMemo(() => {
    const m = new Map<string, PrComment[]>();
    for (const c of pr.comments) {
      if (!c.path || c.parent_id) continue;
      const k = `${c.path}:${c.line ?? ""}`;
      m.set(k, [...(m.get(k) ?? []), c]);
    }
    return m;
  }, [pr.comments]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <label className="flex items-center gap-2 text-fg-subtle">
          Show
          <select value={String(view)} onChange={(e) => setView(e.target.value === "all" ? "all" : Number(e.target.value))}
            className="h-8 rounded-md border border-line bg-canvas px-2 text-fg">
            <option value="all">All changes (vs original project)</option>
            {pr.revision_list.map((r) => <option key={r.number} value={r.number}>Revision {r.number} (vs {r.number === 1 ? "original" : `revision ${r.number - 1}`})</option>)}
          </select>
        </label>
        {open ? <span className="text-[12px] text-fg-subtle">Select a line number to comment.</span> : null}
      </div>
      <DiffView
        diffs={diffs}
        emptyText="No changes in this view."
        onComment={open && view === "all" ? (path, line) => setComposer({ path, line }) : undefined}
        renderAfter={(path, line) => {
          const here = byLine.get(`${path}:${line ?? ""}`) ?? [];
          const composing = composer && composer.path === path && composer.line === line;
          if (!here.length && !composing) return null;
          return (
            <div className="flex flex-col gap-2 py-1">
              {here.map((c) => <CommentBody key={c.id} c={c} />)}
              {composing ? <NewComment pr={pr} reload={reload} onError={onError} path={path} line={line ?? undefined} onDone={() => setComposer(null)} /> : null}
            </div>
          );
        }}
      />
    </div>
  );
}

// ------------------------------------------------------------------ checks

function Checks({ pr }: { pr: PullRequestDetail }) {
  return (
    <ol className="flex flex-col gap-6">
      {pr.revision_list.slice().reverse().map((r) => (
        <li key={r.number}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="text-[14px] font-medium text-fg">Revision {r.number}</h2>
            <span className="text-[12px] text-fg-subtle">snapshot #{r.snapshot_number} · {formatDistanceShort(r.created_at)}</span>
            {r.submission ? <><PassBadge passed={r.submission.passed} total={r.submission.total} /><VerifiedBadge verified={r.submission.verified} executed={r.submission.executed} /></> : null}
          </div>
          {r.note ? <p className="mb-2 text-[13px] text-fg-muted"><Inline text={r.note} /></p> : null}
          {r.job.status === "queued" || r.job.status === "running" ? (
            <p className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-3 text-[13px] text-fg-muted">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />{r.job.status === "queued" ? "Queued for the sandbox…" : "Running in the sandbox…"}
            </p>
          ) : r.job.status !== "completed" ? (
            <p role="alert" className="rounded-xl border border-line bg-surface px-3 py-3 text-[13px] text-fg">{r.job.error_message ?? "Checks could not run."}</p>
          ) : <EngTestResults results={r.job.results} />}
        </li>
      ))}
    </ol>
  );
}

// ------------------------------------------------------------------ decision

function Decision({ pr, open, running, onChange, onError }: {
  pr: PullRequestDetail; open: boolean; running: boolean; onChange: (p: PullRequestDetail) => void; onError: (e: string | null) => void;
}) {
  const [busy, setBusy] = useState<"decide" | "close" | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const c = pr.status === "approved" || pr.status === "closed" ? pr.decision ?? pr.criteria : pr.criteria;

  async function decide() {
    setBusy("decide");
    onError(null);
    const res = await decidePullRequest(pr.id);
    setBusy(null);
    if (!res.ok) return onError(res.error);
    onChange(res.data);
  }

  async function close() {
    setBusy("close");
    const res = await closePullRequest(pr.id);
    setBusy(null);
    setConfirmClose(false);
    if (!res.ok) return onError(res.error);
    onChange(res.data);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section aria-labelledby="criteria-heading" className="rounded-xl border border-line bg-surface p-4">
        <h2 id="criteria-heading" className="text-[15px] font-medium text-fg">Approval criteria</h2>
        <p className="mt-1 text-[13px] text-fg-muted">
          Deterministic and documented. The AI&apos;s recommendation is shown but never decides: a PR is approved only when
          every criterion holds for revision {c.revision}.
        </p>
        <ul className="mt-4 flex flex-col gap-2">
          {c.criteria.map((x) => (
            <li key={x.key} className="flex items-start gap-3 rounded-lg border border-line-subtle bg-canvas px-3 py-2">
              {x.met ? <CircleCheck className="mt-0.5 size-4 shrink-0 text-fg" aria-hidden="true" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-hidden="true" />}
              <div className="text-[13px]">
                <p className="text-fg">{x.label}<span className="sr-only">{x.met ? ": met" : ": not met"}</span></p>
                <p className="text-fg-muted">{x.detail}</p>
              </div>
            </li>
          ))}
        </ul>
        {c.ai_recommendation ? <p className="mt-3 text-[12px] text-fg-subtle">AI reviewer recommendation (advisory): {c.ai_recommendation.replace("_", " ")}</p> : null}
      </section>
      <aside className="flex flex-col gap-3">
        {pr.status === "approved" ? (
          <div className="rounded-xl border border-line bg-surface p-4 text-[13px] text-fg">
            <p className="flex items-center gap-2 font-medium"><GitMerge className="size-4" aria-hidden="true" />Approved</p>
            <p className="mt-1 text-fg-muted">Simulated merge complete. Verified test evidence has been added to your mastery and career records.</p>
            <ButtonLink href="/workspace/progress" size="sm" variant="secondary" className="mt-3">See your progress</ButtonLink>
          </div>
        ) : pr.status === "closed" ? (
          <p className="rounded-xl border border-line bg-surface p-4 text-[13px] text-fg-muted">This pull request was closed without merging.</p>
        ) : (
          <>
            <Button onClick={decide} disabled={!open || running || busy !== null}>
              {busy === "decide" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <GitMerge aria-hidden="true" />}
              Request final decision
            </Button>
            {running ? <p className="text-[12px] text-fg-subtle">Checks are still running.</p> : null}
            {confirmClose ? (
              <div className="flex items-center gap-2 text-[12.5px] text-fg-muted">
                Close without merging?
                <Button size="sm" variant="secondary" onClick={close}>Close</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmClose(false)}>Cancel</Button>
              </div>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setConfirmClose(true)} disabled={busy !== null}>Close pull request</Button>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
