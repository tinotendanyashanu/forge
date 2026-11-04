"use client";

import {
  ArrowLeft,
  CircleAlert,
  FlaskConical,
  GitPullRequest,
  LoaderCircle,
  RotateCcw,
  Save,
  Send,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createEngJob,
  deleteFile,
  fetchEngJob,
  fetchFile,
  fetchWorkspace,
  openPullRequest,
  resetWorkspace,
  restoreSnapshot,
  revealWorkspaceHint,
  saveFile,
} from "@/app/workspace/actions";
import { Button, ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { EngJob, Snapshot, WorkspaceDetail, WorkspaceStatus } from "@/lib/workspace-types";

import { LevelBadge } from "./badges";
import { FileEditor } from "./file-editor";
import { FileTree } from "./file-tree";
import { ChangesPanel, CollaboratePanel, HistoryPanel, ReviewPanel, TestsPanel, TicketPanel } from "./panels";

type BufStatus = "clean" | "dirty" | "saving" | "conflict" | "error";
type Buf = { content: string; saved: string; revision: number; status: BufStatus; message?: string };
type Panel = "ticket" | "tests" | "changes" | "history" | "review" | "collaborate" | "pr";
const PANELS: { id: Panel; label: string }[] = [
  { id: "ticket", label: "Ticket" },
  { id: "tests", label: "Tests" },
  { id: "changes", label: "Changes" },
  { id: "history", label: "History" },
  { id: "review", label: "Review" },
  { id: "collaborate", label: "Collaborate" },
];
const TERMINAL = new Set(["completed", "failed", "blocked"]);
const POLL_MS = 1000;
const POLL_LIMIT_MS = 180_000;
const AUTOSAVE_MS = 900;

function firstFile(ws: WorkspaceDetail): string | null {
  const prefer = ws.files.find((f) => /(^|\/)(routes|service|main|repository)\.(py|ts)$/.test(f.path));
  return (prefer ?? ws.files.find((f) => f.path.endsWith(".md")) ?? ws.files[0])?.path ?? null;
}

export function WorkspaceIde({ initial, status }: { initial: WorkspaceDetail; status: WorkspaceStatus | null }) {
  const router = useRouter();
  const [ws, setWs] = useState(initial);
  const [bufs, setBufs] = useState<Record<string, Buf>>({});
  const bufsRef = useRef(bufs);
  const [tabs, setTabs] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>("ticket");
  const [job, setJob] = useState<EngJob | null>(initial.latest_job);
  const [pending, setPending] = useState<{ kind: "run" | "submit"; key: string } | null>(null);
  const [error, setError] = useState<{ message: string; retry?: () => void } | null>(null);
  const [hints, setHints] = useState(initial.hints);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [reviewSubmission, setReviewSubmission] = useState<string | null>(initial.latest_job?.submission_id ?? null);
  const [reveal, setReveal] = useState<{ line: number; nonce: number } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const canExecute = Boolean(status?.execution.accepts_jobs);
  const llmConfigured = Boolean(status?.llm.configured);

  useEffect(() => {
    bufsRef.current = bufs;
  }, [bufs]);

  const patch = useCallback((path: string, fn: (b: Buf) => Buf) => {
    setBufs((all) => (all[path] ? { ...all, [path]: fn(all[path]) } : all));
  }, []);

  const refreshDetail = useCallback(async () => {
    const res = await fetchWorkspace(ws.id);
    if (res.ok) setWs(res.data);
  }, [ws.id]);

  const openFile = useCallback(async (path: string, line?: number | null) => {
    setTabs((t) => (t.includes(path) ? t : [...t, path]));
    setActive(path);
    if (!bufsRef.current[path]) {
      const res = await fetchFile({ workspaceId: ws.id, path });
      if (!res.ok) {
        setError({ message: res.error });
        return;
      }
      setBufs((all) => all[path] ? all : { ...all, [path]: { content: res.data.content, saved: res.data.content, revision: res.data.revision, status: "clean" } });
    }
    if (line) setReveal({ line, nonce: Date.now() });
  }, [ws.id]);

  // Open a sensible first file once.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    const first = firstFile(initial);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial file load
    if (first) void openFile(first);
  }, [initial, openFile]);

  // ---------------------------------------------------------------- saving

  const saveOne = useCallback(async (path: string): Promise<boolean> => {
    const b = bufsRef.current[path];
    if (!b || (b.status !== "dirty" && b.status !== "error")) return b?.status !== "conflict";
    const sent = b.content;
    patch(path, (x) => ({ ...x, status: "saving" }));
    const res = await saveFile({ workspaceId: ws.id, path, content: sent, baseRevision: b.revision });
    if (res.ok) {
      patch(path, (x) => ({ ...x, saved: sent, revision: res.data.revision, status: x.content === sent ? "clean" : "dirty", message: undefined }));
      return true;
    }
    const conflict = res.error.includes("changed elsewhere") || res.error.includes("deleted elsewhere");
    patch(path, (x) => ({ ...x, status: conflict ? "conflict" : "error", message: res.error }));
    return false;
  }, [patch, ws.id]);

  const saveAll = useCallback(async (): Promise<boolean> => {
    const dirty = Object.entries(bufsRef.current).filter(([, b]) => b.status !== "clean").map(([p]) => p);
    let ok = true;
    for (const p of dirty) ok = (await saveOne(p)) && ok;
    if (dirty.length) {
      void refreshDetail();
      setRefreshKey((k) => k + 1);
    }
    return ok;
  }, [refreshDetail, saveOne]);

  // Debounced autosave.
  const anyDirty = Object.values(bufs).some((b) => b.status === "dirty");
  useEffect(() => {
    if (!anyDirty) return;
    const t = setTimeout(() => void saveAll(), AUTOSAVE_MS);
    return () => clearTimeout(t);
  }, [bufs, anyDirty, saveAll]);

  // Warn before leaving with unsaved work.
  useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => {
      if (Object.values(bufsRef.current).some((b) => b.status !== "clean")) e.preventDefault();
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, []);

  function edit(path: string, value: string) {
    patch(path, (b) => ({ ...b, content: value, status: b.status === "conflict" ? "conflict" : value === b.saved ? "clean" : "dirty" }));
  }

  async function reloadFromServer(path: string) {
    const res = await fetchFile({ workspaceId: ws.id, path });
    if (!res.ok) return setError({ message: res.error });
    setBufs((all) => ({ ...all, [path]: { content: res.data.content, saved: res.data.content, revision: res.data.revision, status: "clean" } }));
  }

  async function keepMine(path: string) {
    const res = await fetchFile({ workspaceId: ws.id, path });
    const b = bufsRef.current[path];
    if (!b) return;
    // The file may have been deleted elsewhere: recreate it.
    const base = res.ok ? res.data.revision : null;
    const saved = await saveFile({ workspaceId: ws.id, path, content: b.content, baseRevision: base });
    if (!saved.ok) return patch(path, (x) => ({ ...x, status: "error", message: saved.error }));
    patch(path, (x) => ({ ...x, saved: b.content, revision: saved.data.revision, status: "clean", message: undefined }));
    void refreshDetail();
  }

  // ---------------------------------------------------------------- files

  async function createFile(path: string): Promise<string | null> {
    const res = await saveFile({ workspaceId: ws.id, path, content: "", baseRevision: null });
    if (!res.ok) return res.error;
    setBufs((all) => ({ ...all, [res.data.path]: { content: "", saved: "", revision: res.data.revision, status: "clean" } }));
    await refreshDetail();
    void openFile(res.data.path);
    return null;
  }

  async function removeFile(path: string): Promise<string | null> {
    const b = bufsRef.current[path];
    const meta = ws.files.find((f) => f.path === path);
    const revision = b?.revision ?? meta?.revision;
    if (!revision) return "File not found";
    const res = await deleteFile({ workspaceId: ws.id, path, baseRevision: revision });
    if (!res.ok) return res.error;
    setBufs((all) => {
      const next = { ...all };
      delete next[path];
      return next;
    });
    closeTab(path);
    await refreshDetail();
    setRefreshKey((k) => k + 1);
    return null;
  }

  function closeTab(path: string) {
    setTabs((t) => {
      const next = t.filter((x) => x !== path);
      setActive((a) => (a === path ? next[next.length - 1] ?? null : a));
      return next;
    });
  }

  async function replaceAll(next: WorkspaceDetail) {
    setWs(next);
    const existing = new Set(next.files.map((f) => f.path));
    setBufs({});
    bufsRef.current = {};
    const keep = tabs.filter((t) => existing.has(t));
    setTabs(keep);
    const nextActive = active && existing.has(active) ? active : keep[0] ?? firstFile(next);
    setActive(nextActive);
    for (const t of new Set([...keep, ...(nextActive ? [nextActive] : [])])) await openFile(t);
    setRefreshKey((k) => k + 1);
  }

  async function reset() {
    setConfirmReset(false);
    if (!(await saveAll())) return setError({ message: "Resolve unsaved changes before resetting." });
    const fresh = await fetchWorkspace(ws.id);
    const res = await resetWorkspace({ workspaceId: ws.id, expectedRevision: fresh.ok ? fresh.data.revision : ws.revision });
    if (!res.ok) return setError({ message: res.error });
    await replaceAll(res.data);
  }

  const restore = useCallback(async (n: number) => {
    if (!(await saveAll())) return setError({ message: "Resolve unsaved changes before restoring." });
    const fresh = await fetchWorkspace(ws.id);
    const res = await restoreSnapshot({ workspaceId: ws.id, number: n, expectedRevision: fresh.ok ? fresh.data.revision : ws.revision });
    if (!res.ok) return setError({ message: res.error });
    await replaceAll(res.data);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- replaceAll reads current tabs
  }, [saveAll, ws.id, ws.revision, tabs, active]);

  async function hint() {
    const res = await revealWorkspaceHint(ws.id);
    if (res.ok) setHints(res.data.hints);
    else setError({ message: res.error });
  }

  // ---------------------------------------------------------------- jobs

  const execute = useCallback(async (kind: "run" | "submit", key: string = crypto.randomUUID()) => {
    if (!canExecute || pending) return;
    setError(null);
    if (!(await saveAll())) {
      setError({ message: "Some files couldn't be saved. Resolve them before running tests." });
      return;
    }
    setPending({ kind, key });
    setPanel("tests");
    const created = await createEngJob({ workspaceId: ws.id, kind, idempotencyKey: key });
    if (!created.ok) {
      setPending(null);
      setError({ message: created.error, retry: created.retryable ? () => void execute(kind, key) : undefined });
      return;
    }
    let current = created.data;
    setJob(current);
    const started = Date.now();
    while (!TERMINAL.has(current.status) && Date.now() - started < POLL_LIMIT_MS) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      const next = await fetchEngJob(current.id);
      if (!next.ok) continue;
      current = next.data;
      setJob(current);
    }
    setPending(null);
    setRefreshKey((k) => k + 1);
    if (!TERMINAL.has(current.status)) {
      setError({ message: "Still waiting for a worker. The job stays queued; check back shortly." });
    } else if (current.submission_id) {
      setReviewSubmission(current.submission_id);
    }
  }, [canExecute, pending, saveAll, ws.id]);

  const commands = useMemo(() => ({
    save: () => void saveAll(),
    run: () => void execute("run"),
    submit: () => void execute("submit"),
  }), [execute, saveAll]);

  // ---------------------------------------------------------------- render

  const dirtySet = useMemo(() => new Set(Object.entries(bufs).filter(([, b]) => b.status !== "clean").map(([p]) => p)), [bufs]);
  const buf = active ? bufs[active] : undefined;
  const saving = Object.values(bufs).some((b) => b.status === "saving");
  const saveLabel = saving ? "Saving…" : dirtySet.size ? `${dirtySet.size} unsaved` : "All changes saved";
  const conflicts = Object.entries(bufs).filter(([, b]) => b.status === "conflict" || b.status === "error");
  const jumpTo = useCallback((path: string, line: number | null) => void openFile(path, line), [openFile]);

  return (
    <div className="flex flex-col lg:h-dvh">
      {/* Top bar */}
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line-subtle px-4 py-2.5">
        <Link href="/workspace" className="rounded-md p-1 text-fg-muted hover:text-fg" aria-label="Back to FORGE Workspace">
          <ArrowLeft className="size-4" aria-hidden="true" />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-[11px] text-fg-subtle">{ws.project.ticket.key} · {ws.project.skill.title} · v{ws.version}{ws.outdated ? " (newer version available)" : ""}</p>
          <h1 className="truncate text-[15px] font-medium text-fg">{ws.project_title}</h1>
        </div>
        <LevelBadge level={ws.level} />
        {ws.status === "completed" ? <span className="rounded-md bg-fg px-2 py-0.5 text-xs text-canvas">Completed</span> : null}
        <span className="text-xs text-fg-subtle" role="status" aria-live="polite">{saveLabel}</span>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => void saveAll()} aria-keyshortcuts="Meta+S Control+S" disabled={!dirtySet.size}>
            <Save aria-hidden="true" />Save
          </Button>
          {confirmReset ? (
            <span className="flex items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-xs text-fg-muted">
              Reset every file to the original? A snapshot is kept.
              <Button size="sm" variant="secondary" onClick={() => void reset()}>Reset</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmReset(false)}>Cancel</Button>
            </span>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirmReset(true)}><RotateCcw aria-hidden="true" />Reset</Button>
          )}
          <Button size="sm" variant="secondary" onClick={commands.run} disabled={!canExecute || !!pending} aria-keyshortcuts="Meta+Enter Control+Enter">
            {pending?.kind === "run" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <FlaskConical aria-hidden="true" />}
            Run tests
          </Button>
          <Button size="sm" variant="secondary" onClick={commands.submit} disabled={!canExecute || !!pending} aria-keyshortcuts="Meta+Shift+Enter Control+Shift+Enter">
            {pending?.kind === "submit" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            Submit
          </Button>
          {ws.open_pull_request ? (
            <ButtonLink href={`/workspace/pulls/${ws.open_pull_request}`} size="sm"><GitPullRequest aria-hidden="true" />View pull request</ButtonLink>
          ) : (
            <Button size="sm" onClick={() => setPanel("pr")} disabled={!canExecute}><GitPullRequest aria-hidden="true" />Open pull request</Button>
          )}
        </div>
      </header>

      {error ? (
        <div role="alert" className="flex items-center justify-between gap-3 border-b border-line-subtle bg-surface px-4 py-2 text-[13px] text-fg">
          <span className="flex items-start gap-2"><CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{error.message}</span>
          <span className="flex gap-1.5">
            {error.retry ? <Button size="sm" variant="secondary" onClick={error.retry}>Retry</Button> : null}
            <Button size="sm" variant="ghost" onClick={() => setError(null)} aria-label="Dismiss"><X aria-hidden="true" /></Button>
          </span>
        </div>
      ) : null}
      {!canExecute ? (
        <p className="border-b border-line-subtle bg-surface px-4 py-1.5 text-[12px] text-fg-muted">
          Code execution is not available on this server, so tests can&apos;t run. You can still read, edit and save.
        </p>
      ) : null}

      <div className="grid lg:min-h-0 lg:flex-1 lg:grid-cols-[230px_minmax(0,1fr)_minmax(360px,420px)]">
        <aside className="max-h-72 min-h-0 border-b border-line-subtle lg:max-h-none lg:border-r lg:border-b-0" aria-label="Project files">
          <FileTree files={ws.files} active={active} dirty={dirtySet} onOpen={(p) => void openFile(p)} onCreate={createFile} onDelete={removeFile} />
        </aside>

        <section className="flex min-h-[65vh] min-w-0 flex-col lg:min-h-0" aria-label="Editor">
          <div role="tablist" aria-label="Open files" className="flex overflow-x-auto border-b border-line-subtle">
            {tabs.map((t) => (
              <div key={t} className={cn("group flex shrink-0 items-center border-r border-line-subtle", t === active ? "bg-surface text-fg" : "text-fg-muted")}>
                <button role="tab" aria-selected={t === active} type="button" onClick={() => setActive(t)} className="max-w-56 truncate py-2 pr-1 pl-3 font-mono text-[12px] hover:text-fg">
                  {t.split("/").pop()}{dirtySet.has(t) ? " •" : ""}
                </button>
                <button type="button" onClick={() => closeTab(t)} aria-label={`Close ${t}`} className="mr-1 rounded p-1 text-fg-subtle hover:text-fg">
                  <X className="size-3" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          {conflicts.map(([p, b]) => (
            <div key={p} role="alert" className="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle bg-surface px-3 py-2 text-[12.5px] text-fg">
              <span><span className="font-mono">{p}</span>: {b.message}</span>
              {b.status === "conflict" ? (
                <span className="flex gap-1.5">
                  <Button size="sm" variant="secondary" onClick={() => void reloadFromServer(p)}>Load saved version</Button>
                  <Button size="sm" variant="ghost" onClick={() => void keepMine(p)}>Keep my version</Button>
                </span>
              ) : <Button size="sm" variant="secondary" onClick={() => void saveOne(p)}>Retry save</Button>}
            </div>
          ))}
          <div className="min-h-0 flex-1">
            {active && buf ? (
              <FileEditor path={active} value={buf.content} onChange={(v) => edit(active, v)} commands={commands} revealLine={reveal} />
            ) : (
              <p className="p-6 text-sm text-fg-muted">{active ? "Loading file…" : "Select a file to start."}</p>
            )}
          </div>
          {active ? (
            <p className="border-t border-line-subtle px-3 py-1 font-mono text-[11px] text-fg-subtle">{active}</p>
          ) : null}
        </section>

        <aside className="flex min-h-0 flex-col border-t border-line-subtle lg:border-t-0 lg:border-l" aria-label="Task panels">
          <div role="tablist" aria-label="Panels" className="flex overflow-x-auto border-b border-line-subtle px-1">
            {PANELS.map((p) => (
              <button key={p.id} role="tab" type="button" id={`tab-${p.id}`} aria-selected={panel === p.id} aria-controls="panel-body"
                onClick={() => setPanel(p.id)}
                className={cn("shrink-0 border-b-2 px-2.5 py-2 text-[12.5px]", panel === p.id ? "border-fg text-fg" : "border-transparent text-fg-muted hover:text-fg")}>
                {p.label}
              </button>
            ))}
          </div>
          <div id="panel-body" role="tabpanel" aria-labelledby={`tab-${panel}`} className="min-h-0 flex-1 overflow-y-auto p-4">
            {panel === "ticket" ? <TicketPanel ws={ws} hints={hints} onHint={() => void hint()} /> : null}
            {panel === "tests" ? <TestsPanel ws={ws} job={job} pending={!!pending} /> : null}
            {panel === "changes" ? <ChangesPanel ws={ws} refreshKey={refreshKey} snapshots={snapshots} /> : null}
            {panel === "history" ? (
              <HistoryPanel ws={ws} snapshots={snapshots} onSnapshotsChange={setSnapshots} onRestore={restore} refreshKey={refreshKey}
                onReviewSubmission={(id) => { setReviewSubmission(id); setPanel("review"); }} />
            ) : null}
            {panel === "review" ? <ReviewPanel key={reviewSubmission ?? "none"} ws={ws} submissionId={reviewSubmission} llmConfigured={llmConfigured} onJump={jumpTo} /> : null}
            {panel === "collaborate" ? <CollaboratePanel ws={ws} llmConfigured={llmConfigured} /> : null}
            {panel === "pr" ? (
              <OpenPrForm ws={ws} onOpen={async (title, description, key) => {
                if (!(await saveAll())) return "Some files couldn't be saved.";
                const res = await openPullRequest({ workspaceId: ws.id, title, description, idempotencyKey: key });
                if (!res.ok) return res.error;
                router.push(`/workspace/pulls/${res.data.id}`);
                return null;
              }} />
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

function OpenPrForm({ ws, onOpen }: { ws: WorkspaceDetail; onOpen: (title: string, description: string, key: string) => Promise<string | null> }) {
  const t = ws.project.ticket;
  const [title, setTitle] = useState(`${t.key}: ${t.title}`.slice(0, 160));
  const [description, setDescription] = useState(
    `## What changed\n\n\n## Why\n\n\n## How I tested it\n\n\n## Risks and rollout\n\n`,
  );
  const [key] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(await onOpen(title.trim(), description.trim(), key));
        setBusy(false);
      }}
    >
      <h2 className="text-[15px] font-medium text-fg">Open a pull request</h2>
      <p className="text-[12.5px] text-fg-muted">
        A simulated, internal pull request: nothing is pushed to any external repository. Opening it snapshots your saved
        work and runs every public and hidden test.
      </p>
      <label className="flex flex-col gap-1 text-[12px] text-fg-subtle">
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} minLength={5} maxLength={160} required
          className="h-9 rounded-md border border-line bg-canvas px-2 text-[13px] text-fg focus:border-neutral-500 focus:outline-none" />
      </label>
      <label className="flex flex-col gap-1 text-[12px] text-fg-subtle">
        Description: explain what you changed, why, and how you tested it
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={12} minLength={20} maxLength={8000} required
          className="resize-y rounded-md border border-line bg-canvas px-3 py-2 font-mono text-[12.5px] leading-relaxed text-fg focus:border-neutral-500 focus:outline-none" />
      </label>
      {error ? <p role="alert" className="text-[13px] text-fg">{error}</p> : null}
      <Button type="submit" disabled={busy}>
        {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <GitPullRequest aria-hidden="true" />}
        Open pull request
      </Button>
    </form>
  );
}
