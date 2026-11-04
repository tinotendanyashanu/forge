"use client";

import { ClipboardCheck, Lightbulb, Loader2, Plus, Send } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import {
  evaluateDesign,
  fetchDesignReview,
  requestDesignHint,
  sendDesignMessage,
  startDesignReview,
} from "@/app/actions";
import { Button } from "@/components/ui/button";
import { MessageText } from "@/components/ui/message-text";
import { cn } from "@/lib/cn";
import type { DesignLabStatus, DesignMessage, DesignReview, DesignReviewMode } from "@/lib/types";
import { DESIGN_REVIEW_MODES } from "@/lib/types";

import { MODE_INFO } from "./components";
import { EvaluationView } from "./evaluation-view";

export function ReviewPanel({
  projectId,
  reviews,
  initialReview,
  status,
  flush,
  hasNodes,
  nodeNames,
  onHighlight,
}: {
  projectId: string;
  reviews: DesignReview[];
  initialReview: DesignReview | null;
  status: DesignLabStatus | null;
  flush: () => Promise<boolean>;
  hasNodes: boolean;
  nodeNames: Record<string, string>;
  onHighlight: (ids: string[]) => void;
}) {
  const [review, setReview] = useState<DesignReview | null>(initialReview);
  const [list, setList] = useState(reviews);
  const [choosing, setChoosing] = useState(!initialReview);
  const [mode, setMode] = useState<DesignReviewMode>("guided");
  const [busy, setBusy] = useState<null | "start" | "send" | "hint" | "evaluate">(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [view, setView] = useState<"chat" | "evaluation">("chat");
  const pendingId = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const id = useId();

  const messages = review?.messages ?? [];
  const evaluations = review?.evaluations ?? [];
  const configured = status?.llm.configured ?? false;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  async function start() {
    setBusy("start");
    setError(null);
    const res = await startDesignReview({ projectId, mode });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    setReview({ ...res.data, evaluations: [] });
    setList((l) => [res.data, ...l]);
    setChoosing(false);
    setView("chat");
  }

  async function open(reviewId: string) {
    const res = await fetchDesignReview(reviewId);
    if (!res.ok) return setError(res.error);
    setReview(res.data);
    setChoosing(false);
  }

  function append(ms: DesignMessage[]) {
    setReview((r) => {
      if (!r) return r;
      const seen = new Set((r.messages ?? []).map((m) => m.id));
      return { ...r, messages: [...(r.messages ?? []), ...ms.filter((m) => !seen.has(m.id))] };
    });
  }

  async function send() {
    if (!review || !draft.trim()) return;
    setBusy("send");
    setError(null);
    // Reuse the id when retrying, so the server never records the message twice.
    pendingId.current ??= crypto.randomUUID();
    if (!(await flush())) {
      setBusy(null);
      return setError("Save your design first: resolve the save problem shown above.");
    }
    const res = await sendDesignMessage({ reviewId: review.id, content: draft, clientMessageId: pendingId.current });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    pendingId.current = null;
    setDraft("");
    append(res.data.messages);
  }

  async function hint() {
    if (!review) return;
    setBusy("hint");
    const res = await requestDesignHint(review.id);
    setBusy(null);
    if (!res.ok) return setError(res.error);
    append([res.data]);
    setReview((r) => (r ? { ...r, hints_used: r.hints_used + 1 } : r));
  }

  async function evaluate() {
    if (!review) return;
    setBusy("evaluate");
    setError(null);
    if (!(await flush())) {
      setBusy(null);
      return setError("Save your design first: resolve the save problem shown above.");
    }
    const res = await evaluateDesign(review.id);
    setBusy(null);
    if (!res.ok) return setError(res.error);
    const refreshed = await fetchDesignReview(review.id);
    if (refreshed.ok) setReview(refreshed.data);
    setView("evaluation");
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {!configured ? (
        <p className="m-4 mb-0 rounded-lg border border-line bg-surface-elevated p-3 text-xs leading-relaxed text-fg-muted">
          No AI provider is configured on the API, so reviews and evaluations will be recorded as unavailable. Set the
          FORGE_LLM_* variables for Ollama Cloud and restart the API. Designing, versions and ADRs work without it.
        </p>
      ) : (
        <p className="px-4 pt-3 font-mono text-[11px] text-fg-subtle">Reviewer: {status?.llm.provider}/{status?.llm.model}</p>
      )}

      {choosing || !review ? (
        <div className="flex flex-col gap-3 p-4">
          <fieldset>
            <legend className="mb-2 text-xs font-medium text-fg">Review mode</legend>
            <div className="flex flex-col gap-1.5">
              {DESIGN_REVIEW_MODES.map((m) => (
                <label
                  key={m}
                  className={cn(
                    "flex cursor-pointer gap-2.5 rounded-lg border px-3 py-2.5",
                    mode === m ? "border-fg bg-surface-elevated" : "border-line hover:bg-surface-hover",
                  )}
                >
                  <input type="radio" name={`${id}-mode`} value={m} checked={mode === m} onChange={() => setMode(m)} className="mt-1 accent-white" />
                  <span>
                    <span className="block text-[13px] text-fg">{MODE_INFO[m].label}</span>
                    <span className="block text-xs text-fg-muted">{MODE_INFO[m].description}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => void start()} disabled={busy !== null}>
              {busy === "start" ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}Start review
            </Button>
            {review ? <Button size="sm" variant="ghost" onClick={() => setChoosing(false)}>Cancel</Button> : null}
          </div>
          {list.length ? (
            <div>
              <h3 className="mb-1.5 text-xs font-medium text-fg-subtle">Previous reviews</h3>
              <ul className="flex flex-col gap-1">
                {list.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => void open(r.id)} className="w-full rounded-md px-2 py-1.5 text-left text-xs text-fg-muted hover:bg-surface-hover hover:text-fg">
                      {MODE_INFO[r.mode].label} · {new Date(r.created_at).toLocaleString()}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-1 border-b border-line-subtle px-3 py-2">
            <span className="mr-auto truncate text-xs text-fg-muted">
              {MODE_INFO[review.mode].label} · depth {review.depth}/3
            </span>
            <Button size="sm" variant={view === "chat" ? "secondary" : "ghost"} onClick={() => setView("chat")}>Conversation</Button>
            <Button size="sm" variant={view === "evaluation" ? "secondary" : "ghost"} onClick={() => setView("evaluation")}>
              Evaluation{evaluations.length ? ` (${evaluations.length})` : ""}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setChoosing(true)} aria-label="New review"><Plus aria-hidden="true" /></Button>
          </div>

          {view === "chat" ? (
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" aria-live="polite">
              <ol className="flex flex-col gap-3">
                {messages.map((m) => (
                  <li
                    key={m.id}
                    className={cn(
                      "rounded-lg px-3 py-2.5 text-[13px] leading-relaxed",
                      m.role === "learner" && "ml-6 bg-surface-elevated text-fg",
                      m.role === "interviewer" && "mr-6 border border-line text-fg",
                      m.role === "system" && "text-xs text-fg-muted",
                    )}
                  >
                    <p className="mb-1 text-[11px] text-fg-subtle">
                      {m.role === "learner" ? "You" : m.role === "interviewer" ? "Interviewer (AI)" : m.kind === "hint" ? "Hint" : "FORGE"}
                    </p>
                    <MessageText text={m.content} />
                  </li>
                ))}
                {busy === "send" ? (
                  <li className="mr-6 flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-xs text-fg-muted">
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />The interviewer is reading your design…
                  </li>
                ) : null}
              </ol>
              <div ref={endRef} />
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {evaluations.length ? (
                <div className="flex flex-col gap-6">
                  {evaluations.map((ev, i) => (
                    <details key={ev.id} open={i === 0} className="group">
                      <summary className="mb-3 cursor-pointer text-xs text-fg-muted">
                        Version {ev.architecture_version} · {new Date(ev.created_at).toLocaleString()} · {ev.status}
                      </summary>
                      <EvaluationView ev={ev} nodeNames={nodeNames} onEvidence={onHighlight} />
                    </details>
                  ))}
                </div>
              ) : (
                <p className="text-xs leading-relaxed text-fg-muted">
                  No evaluations yet. Explain your design in the conversation, then request an evaluation. Your current
                  design is snapshotted as a version and graded against 12 criteria.
                </p>
              )}
            </div>
          )}

          <form
            className="border-t border-line-subtle p-3"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <label htmlFor={`${id}-msg`} className="sr-only">Your answer</label>
            <textarea
              id={`${id}-msg`}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                pendingId.current = null;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void send();
                }
              }}
              maxLength={8000}
              placeholder="Explain your reasoning or answer the question…"
              className="min-h-20 w-full resize-y rounded-md border border-line bg-canvas px-2.5 py-2 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none"
            />
            {error ? <p role="alert" className="mb-2 text-xs text-fg">{error}</p> : null}
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" size="sm" disabled={busy !== null || !draft.trim()}>
                {busy === "send" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Send aria-hidden="true" />}Send
              </Button>
              <Button size="sm" variant="secondary" onClick={() => void hint()} disabled={busy !== null}>
                <Lightbulb aria-hidden="true" />Hint{review.hints_used ? ` (${review.hints_used} used)` : ""}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => void evaluate()} disabled={busy !== null || !hasNodes} className="ml-auto">
                {busy === "evaluate" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ClipboardCheck aria-hidden="true" />}
                {busy === "evaluate" ? "Evaluating…" : "Evaluate design"}
              </Button>
            </div>
            <p className="mt-1.5 text-[11px] text-fg-subtle">⌘/Ctrl + Enter to send. Hints are recorded: after more than one, an evaluation can&apos;t count as a success.</p>
          </form>
        </>
      )}
    </div>
  );
}
