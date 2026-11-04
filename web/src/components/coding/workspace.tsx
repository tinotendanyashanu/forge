"use client";

import {
  ArrowRight,
  CircleAlert,
  FlaskConical,
  Lightbulb,
  LoaderCircle,
  RotateCcw,
  Send,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { createCodingJob, fetchCodingJob, revealCodeHint, saveCodeDraft } from "@/app/actions";
import { Button, ButtonLink } from "@/components/ui/button";
import type { ChallengeDetail, ChallengeState, CodeLanguage, CodingJob, ExecutionStatus } from "@/lib/types";

import { CodeEditor } from "./code-editor";
import { TestResults } from "./test-results";

type SaveState = "saved" | "saving" | "unsaved" | "conflict" | "error";
type Pending = { kind: "run" | "submit"; key: string };
const TERMINAL = new Set(["completed", "failed", "blocked"]);
const POLL_MS = 1000;
const POLL_LIMIT_MS = 120_000;

export function Workspace({
  challenge,
  initial,
  status,
}: {
  challenge: ChallengeDetail;
  initial: ChallengeState | null;
  status: ExecutionStatus | null;
}) {
  const startLang = (initial?.draft?.language ?? challenge.languages[0]) as CodeLanguage;
  const [language, setLanguage] = useState<CodeLanguage>(startLang);
  const draftFor = (lang: CodeLanguage) => initial?.drafts[lang];
  const [code, setCode] = useState(draftFor(startLang)?.code ?? challenge.starters[startLang] ?? "");
  const [revision, setRevision] = useState<number | null>(draftFor(startLang)?.revision ?? null);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [hints, setHints] = useState<string[]>(initial?.hints ?? []);
  const [job, setJob] = useState<CodingJob | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<{ message: string; retry: Pending | null } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const dirty = useRef(false);

  const canExecute = Boolean(status?.accepts_jobs);

  // Autosave: debounce edits to the backend draft, with optimistic revisions.
  useEffect(() => {
    if (!dirty.current) return;
    const t = setTimeout(async () => {
      setSaveState("saving");
      const res = await saveCodeDraft({ slug: challenge.slug, language, code, baseRevision: revision });
      if (res.ok) {
        setRevision(res.data.revision);
        setSaveState("saved");
        dirty.current = false;
      } else {
        setSaveState(res.error.includes("changed elsewhere") ? "conflict" : "error");
      }
    }, 1200);
    return () => clearTimeout(t);
  }, [code, language, revision, challenge.slug]);

  function edit(next: string) {
    // One state update per keystroke: the effect below only schedules the save.
    dirty.current = true;
    setCode(next);
    setSaveState((prev) => (prev === "conflict" ? prev : "unsaved"));
  }

  function switchLanguage(next: CodeLanguage) {
    setLanguage(next);
    setCode(draftFor(next)?.code ?? challenge.starters[next] ?? "");
    setRevision(draftFor(next)?.revision ?? null);
    setJob(null);
  }

  const execute = useCallback(
    async (p: Pending) => {
      if (!canExecute || pending) return;
      setPending(p);
      setError(null);
      const created = await createCodingJob({ slug: challenge.slug, language, code, kind: p.kind, idempotencyKey: p.key });
      if (!created.ok) {
        setPending(null);
        setError({ message: created.error, retry: created.retryable ? p : null });
        return;
      }
      let current = created.data;
      setJob(current);
      const started = Date.now();
      while (!TERMINAL.has(current.status) && Date.now() - started < POLL_LIMIT_MS) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        const next = await fetchCodingJob(current.id);
        if (!next.ok) continue; // transient: keep polling until the limit
        current = next.data;
        setJob(current);
      }
      setPending(null);
      if (!TERMINAL.has(current.status)) {
        setError({ message: "Still waiting for a worker. The job stays queued; check back shortly.", retry: null });
      }
    },
    [canExecute, challenge.slug, code, language, pending],
  );

  const run = useCallback(() => void execute({ kind: "run", key: crypto.randomUUID() }), [execute]);
  const submit = useCallback(() => void execute({ kind: "submit", key: crypto.randomUUID() }), [execute]);

  async function hint() {
    const res = await revealCodeHint({ slug: challenge.slug, language });
    if (res.ok) setHints(res.data.hints);
    else setError({ message: res.error, retry: null });
  }

  function reset() {
    setConfirmReset(false);
    edit(challenge.starters[language] ?? "");
  }

  const summary = job?.status === "completed" && job.total !== null ? `${job.passed} / ${job.total} passed` : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {challenge.languages.length > 1 ? (
            <label className="flex items-center gap-2 text-xs text-fg-subtle">
              Language
              <select
                value={language}
                onChange={(e) => switchLanguage(e.target.value as CodeLanguage)}
                className="h-8 rounded-lg border border-line bg-canvas px-2 text-sm text-fg"
              >
                {challenge.languages.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </label>
          ) : null}
          <span className="text-xs text-fg-subtle" role="status" aria-live="polite">
            {saveState === "saving" ? "Saving…" : saveState === "unsaved" ? "Unsaved changes"
              : saveState === "conflict" ? "Draft changed in another tab. Reload to continue."
              : saveState === "error" ? "Couldn't save draft" : "Draft saved"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {confirmReset ? (
            <>
              <span className="text-xs text-fg-muted">Replace your code with the starter?</span>
              <Button size="sm" variant="secondary" onClick={reset}>Reset</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmReset(false)}>Cancel</Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirmReset(true)}>
              <RotateCcw aria-hidden="true" />
              Reset
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={hint} disabled={hints.length >= challenge.hint_count}>
            <Lightbulb aria-hidden="true" />
            Hint <span className="text-fg-subtle tabular-nums">{challenge.hint_count - hints.length}</span>
          </Button>
          <Button size="sm" variant="secondary" onClick={run} disabled={!canExecute || Boolean(pending)} aria-keyshortcuts="Meta+Enter Control+Enter">
            {pending?.kind === "run" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <FlaskConical aria-hidden="true" />}
            Run tests
          </Button>
          <Button size="sm" onClick={submit} disabled={!canExecute || Boolean(pending)} aria-keyshortcuts="Meta+Shift+Enter Control+Shift+Enter">
            {pending?.kind === "submit" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            Submit
          </Button>
        </div>
      </div>

      <CodeEditor
        value={code}
        language={language}
        onChange={edit}
        onRun={run}
        onSubmit={submit}
        label={`${challenge.title} solution in ${language}`}
      />

      {hints.length ? (
        <ol className="flex flex-col gap-2" aria-label="Hints">
          {hints.map((h, i) => (
            <li key={h} className="flex gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-fg">
              <Lightbulb className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
              <span><span className="text-xs text-fg-subtle">Hint {i + 1}. </span>{h}</span>
            </li>
          ))}
        </ol>
      ) : null}

      {error ? (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg">
          <span className="flex items-start gap-2">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {error.message}
          </span>
          {error.retry ? (
            <Button size="sm" variant="secondary" onClick={() => void execute(error.retry!)}>Retry</Button>
          ) : null}
        </div>
      ) : null}

      <section aria-labelledby="results-heading" aria-live="polite" className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 id="results-heading" className="text-sm font-medium text-fg">
            {job ? (job.kind === "run" ? "Public test results" : "Submission results") : "Results"}
          </h2>
          {summary ? <span className="text-sm text-fg tabular-nums">{summary}</span> : null}
        </div>
        {!job ? (
          <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-fg-muted">
            Run the public tests while you work. Submit to run every test, including hidden ones.
          </p>
        ) : job.status === "queued" || job.status === "running" ? (
          <p className="flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-4 text-sm text-fg-muted">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {job.status === "queued" ? "Queued for the sandbox…" : "Running in the sandbox…"}
          </p>
        ) : job.status !== "completed" ? (
          <p role="alert" className="rounded-xl border border-line bg-surface px-4 py-4 text-sm text-fg">
            {job.error_message ?? "The job could not be completed."}
          </p>
        ) : (
          <>
            <TestResults results={job.results} />
            {job.submission_id ? (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-fg-subtle">
                  {job.sandbox_verified
                    ? "Executed in the verified sandbox. Counts as verified practical evidence."
                    : "Not executed in a verified sandbox: this result is not evidence."}
                </p>
                <ButtonLink href={`/lab/submissions/${job.submission_id}`} size="sm" variant="secondary">
                  Submission and AI review
                  <ArrowRight aria-hidden="true" />
                </ButtonLink>
              </div>
            ) : null}
          </>
        )}
      </section>

      {initial?.solved ? (
        <p className="text-xs text-fg-subtle">
          You&apos;ve solved this challenge.{" "}
          <Link href={`/lab/submissions?challenge=${challenge.slug}`} className="underline underline-offset-4">
            See your submissions and the reference solution
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
