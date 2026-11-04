"use client";

import {
  Anvil,
  ArrowRight,
  ArrowUp,
  CircleAlert,
  CircleHelp,
  Lightbulb,
  LoaderCircle,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  interviewAction,
  retryInterviewEvaluation,
  type InterviewActionName,
} from "@/app/actions";
import { Button, ButtonLink } from "@/components/ui/button";
import { MessageText } from "@/components/ui/message-text";
import { cn } from "@/lib/cn";
import { difficultyLabel } from "@/lib/format";
import type { InterviewState, InterviewTurn } from "@/lib/types";

import { EvaluationPanel } from "./evaluation-panel";
import { MODE_META } from "./modes";

const MAX_CHARS = 10_000;

type Spec =
  | { kind: "action"; action: InterviewActionName; clientTurnId: string; content?: string }
  | { kind: "evaluation"; evaluationId: string };
type Pending = { action: InterviewActionName | "retry"; content?: string };
// A failure keeps the exact request spec, so Retry resends the same client_turn_id.
type Failure = { message: string; retry: Spec | null };

function newId() {
  return crypto.randomUUID();
}

function InterviewerMark() {
  return (
    <span
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-hover text-fg"
      aria-hidden="true"
    >
      <Anvil className="size-[18px]" />
    </span>
  );
}

function Turn({
  turn,
  challengeNumber,
  onRetryEvaluation,
  retryDisabled,
}: {
  turn: InterviewTurn;
  challengeNumber: number | null;
  onRetryEvaluation: (evaluationId: string) => void;
  retryDisabled: boolean;
}) {
  if (turn.role === "learner") {
    const ev = turn.evaluation;
    return (
      <div className="flex flex-col items-end gap-1.5">
        <div className="max-w-[90%] rounded-3xl bg-surface-hover px-5 py-3 text-base leading-7 text-fg sm:max-w-[85%]">
          {turn.kind === "answer" ? <MessageText text={turn.content} /> : <p className="text-fg-muted italic">{turn.content}</p>}
        </div>
        {ev?.status === "pending" ? (
          <p className="text-xs text-fg-subtle">Evaluation in progress…</p>
        ) : null}
        {ev?.status === "ungraded" ? (
          <div className="flex items-center gap-2 text-xs text-fg-subtle">
            <span>Not evaluated</span>
            {ev.retryable ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={retryDisabled}
                onClick={() => onRetryEvaluation(ev.id)}
              >
                <RotateCcw aria-hidden="true" />
                Retry evaluation
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  if (turn.kind === "hint") {
    return (
      <div className="ml-10 flex gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
        <div>
          <p className="mb-1 text-xs font-medium text-fg-subtle">Hint {turn.hint_level} of 3</p>
          <div className="leading-relaxed text-fg">
            <MessageText text={turn.content} />
          </div>
        </div>
      </div>
    );
  }

  if (turn.kind === "notice") {
    return (
      <div className="ml-10 flex gap-3 rounded-xl border border-dashed border-line px-4 py-3 text-sm text-fg-muted">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p className="leading-relaxed">{turn.content}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {turn.kind === "question" && challengeNumber !== null ? (
        <div className="mb-2 flex items-center gap-3 text-xs text-fg-subtle" role="separator">
          <span className="h-px flex-1 bg-line-subtle" />
          Challenge {challengeNumber}
          <span className="h-px flex-1 bg-line-subtle" />
        </div>
      ) : null}
      <div className="flex gap-3">
        <InterviewerMark />
        <div className="min-w-0 flex-1 pt-0.5 text-base leading-7 text-fg">
          {turn.kind === "follow_up" ? (
            <p className="mb-1 text-xs font-medium text-fg-subtle">Follow-up</p>
          ) : null}
          <MessageText text={turn.content} />
        </div>
      </div>
    </div>
  );
}

export function InterviewChat({ initial }: { initial: InterviewState }) {
  const [state, setState] = useState(initial);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const composerHelpId = useId();

  const { session, current_challenge: challenge } = state;
  const open = challenge?.status === "open";
  const busy = pending !== null || Boolean(challenge?.awaiting_evaluation);
  const meta = MODE_META[session.mode];

  // Keep the newest message in view.
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  }, [state.turns.length, pending]);

  const perform = useCallback(
    async (spec: Spec) => {
      setFailure(null);
      setPending(
        spec.kind === "action"
          ? { action: spec.action, content: spec.content }
          : { action: "retry" },
      );
      const result =
        spec.kind === "action"
          ? await interviewAction({
              sessionId: session.id,
              action: spec.action,
              clientTurnId: spec.clientTurnId,
              content: spec.content,
            })
          : await retryInterviewEvaluation({
              sessionId: session.id,
              evaluationId: spec.evaluationId,
            });
      setPending(null);
      if (!result.ok) {
        setFailure({ message: result.error, retry: result.retryable ? spec : null });
        return;
      }
      setState(result.data);
      if (spec.kind === "action" && spec.action === "answers") setDraft("");
      if (spec.kind === "action" && spec.action === "continue") textareaRef.current?.focus();
    },
    [session.id],
  );

  const run = useCallback(
    (action: InterviewActionName, content?: string) =>
      perform({ kind: "action", action, clientTurnId: newId(), content }),
    [perform],
  );

  const retryEvaluation = useCallback(
    (evaluationId: string) => perform({ kind: "evaluation", evaluationId }),
    [perform],
  );

  function send() {
    const text = draft.trim();
    if (!text || busy || !open) return;
    if (text.length > MAX_CHARS) {
      setFailure({ message: `Keep your answer under ${MAX_CHARS.toLocaleString()} characters.`, retry: null });
      return;
    }
    void run("answers", text);
  }

  // Global shortcuts.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !open && state.can_continue && !busy) {
        e.preventDefault();
        void run("continue");
      } else if (e.altKey && e.code === "KeyH" && open && challenge?.can_request_hint && !busy) {
        e.preventDefault();
        void run("hints");
      } else if (e.altKey && e.code === "KeyK" && open && !busy) {
        e.preventDefault();
        void run("dont-know");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, challenge?.can_request_hint, open, run, state.can_continue]);

  // Number challenges by their question turns.
  let questionCount = 0;
  const lastTurnOfCurrent = challenge
    ? [...state.turns].reverse().find((t) => t.challenge_id === challenge.id)?.id
    : undefined;

  return (
    <div className="flex min-h-[calc(100dvh-3.5rem)] flex-col md:min-h-dvh">
      <header className="sticky top-14 z-20 border-b border-line-subtle bg-canvas md:top-0">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2 text-sm">
            <meta.icon className="size-4 shrink-0 text-fg-muted" aria-hidden="true" />
            <span className="truncate font-medium text-fg">
              {session.skill.title} · {meta.label}
            </span>
          </div>
          <p className="text-xs text-fg-subtle tabular-nums">
            {challenge ? `Challenge ${challenge.position} of ${session.target_challenge_count}` : null}
            {" · "}
            {difficultyLabel[session.current_difficulty]}
            <span className="hidden sm:inline"> · {session.model === "none" ? "AI grading off" : session.model}</span>
          </p>
        </div>
      </header>

      <div className="mx-auto w-full max-w-3xl flex-1 px-5 pt-10 pb-8 sm:px-6">
        <div role="log" aria-label="Interview transcript" aria-live="polite" className="flex flex-col gap-8">
          {state.turns.map((turn) => {
            const number = turn.kind === "question" ? ++questionCount : null;
            return (
              <div key={turn.id} className="flex flex-col gap-6">
                <Turn
                  turn={turn}
                  challengeNumber={number}
                  onRetryEvaluation={retryEvaluation}
                  retryDisabled={busy || !open}
                />
                {turn.id === lastTurnOfCurrent && challenge?.reveal ? (
                  <EvaluationPanel reveal={challenge.reveal} />
                ) : null}
              </div>
            );
          })}

          {pending?.action === "answers" && pending.content ? (
            <div className="flex justify-end">
              <div className="max-w-[90%] rounded-3xl bg-surface-hover px-5 py-3 text-base leading-7 text-fg opacity-70 sm:max-w-[85%]">
                <MessageText text={pending.content} />
              </div>
            </div>
          ) : null}
          {pending ? (
            <div className="flex items-center gap-3 text-sm text-fg-subtle" role="status">
              <InterviewerMark />
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {pending.action === "answers" || pending.action === "retry"
                ? "Evaluating your answer…"
                : "Thinking…"}
            </div>
          ) : null}
          <div ref={endRef} />
        </div>
      </div>

      <div className="sticky bottom-0 z-20 bg-canvas">
        <div className="mx-auto max-w-3xl px-4 pt-3 pb-4 sm:px-6">
          {failure ? (
            <div role="alert" className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg">
              <span className="flex items-start gap-2">
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {failure.message}
              </span>
              {failure.retry ? (
                <Button variant="secondary" size="sm" onClick={() => void perform(failure.retry!)}>
                  <RotateCcw aria-hidden="true" />
                  Retry
                </Button>
              ) : null}
            </div>
          ) : null}

          {session.status === "completed" ? (
            <div className="flex flex-col items-center gap-3 py-2 sm:flex-row sm:justify-between">
              <p className="text-sm text-fg-muted">Interview complete.</p>
              <ButtonLink href={`/interview/${session.id}/summary`}>
                View summary
                <ArrowRight aria-hidden="true" />
              </ButtonLink>
            </div>
          ) : !open ? (
            <div className="flex flex-col gap-2 py-1 sm:flex-row sm:items-center sm:justify-between">
              <Link href={`/interview/${session.id}/summary`} className="rounded text-sm text-fg-muted hover:text-fg">
                Session summary
              </Link>
              <Button onClick={() => void run("continue")} disabled={busy || !state.can_continue} aria-keyshortcuts="Meta+Enter Control+Enter">
                {pending?.action === "continue" ? (
                  <LoaderCircle className="animate-spin" aria-hidden="true" />
                ) : null}
                Next challenge
                <kbd className="ml-1 hidden rounded border border-canvas/20 px-1 font-mono text-[11px] sm:inline">⌘↵</kbd>
              </Button>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
              className="rounded-3xl border border-line bg-surface transition-colors focus-within:border-fg-muted"
            >
              <label htmlFor="interview-answer" className="sr-only">
                Your answer
              </label>
              <textarea
                id="interview-answer"
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={3}
                disabled={busy}
                placeholder="Reason through your answer…"
                aria-describedby={composerHelpId}
                className="field-sizing-content block max-h-64 min-h-24 w-full resize-none rounded-t-3xl bg-transparent px-5 pt-4 text-base leading-7 text-fg placeholder:text-fg-subtle focus:outline-none disabled:opacity-60"
              />
              <div className="flex items-center justify-between gap-2 px-2 pb-2">
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => void run("hints")}
                    disabled={busy || !challenge?.can_request_hint}
                    title={challenge?.hint_blocked_reason ?? "Ask for a hint (Alt+H)"}
                    aria-keyshortcuts="Alt+H"
                  >
                    <Lightbulb aria-hidden="true" />
                    Hint
                    <span className="text-fg-subtle tabular-nums">
                      {challenge ? challenge.max_hints - challenge.hints_used : 0}
                    </span>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => void run("dont-know")}
                    disabled={busy}
                    title="Say you don't know (Alt+K)"
                    aria-keyshortcuts="Alt+K"
                  >
                    <CircleHelp aria-hidden="true" />
                    <span className="hidden sm:inline">I don&apos;t know</span>
                    <span className="sm:hidden">Not sure</span>
                  </Button>
                </div>
                <Button
                  type="submit"
                  size="sm"
                  disabled={busy || !draft.trim()}
                  aria-label="Send answer"
                  className="size-9 rounded-full px-0"
                >
                  {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <ArrowUp aria-hidden="true" />}
                </Button>
              </div>
            </form>
          )}
          <p id={composerHelpId} className={cn("mt-3 text-center text-xs leading-relaxed text-fg-subtle", !open && "sr-only")}>
            Enter to send · Shift+Enter for a new line · Alt+H hint · Alt+K I don&apos;t know
            {challenge?.hint_blocked_reason && open ? ` · ${challenge.hint_blocked_reason}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
