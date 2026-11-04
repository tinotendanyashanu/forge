"use client";

import {
  ArrowRight,
  CircleAlert,
  CornerDownLeft,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, useTransition, type FormEvent } from "react";

import { submitAnswer, type AnswerInput } from "@/app/actions";
import { HintDisclosure } from "@/components/practice/hint-disclosure";
import { Button } from "@/components/ui/button";
import { InlineText } from "@/components/ui/rich-text";
import { cn } from "@/lib/cn";
import type { Assessment, Feedback, SessionItem } from "@/lib/types";

import { FeedbackView } from "./feedback-view";

const MAX_CHARS = 10_000;

type SubmitError = { message: string; retryable: boolean };

// Set when the learner advances, so the next question (a fresh, keyed mount)
// scrolls to the top and takes focus. Not set on first load or back-navigation.
let advancedFromPrevious = false;

export function QuestionRunner({
  session,
  item,
}: {
  session: Assessment;
  item: SessionItem;
}) {
  const router = useRouter();
  const { question } = item;
  const isChoice = question.format === "single_choice";

  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [error, setError] = useState<SubmitError | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [submitting, startSubmit] = useTransition();
  const [advancing, startAdvance] = useTransition();
  const feedbackHeadingRef = useRef<HTMLHeadingElement>(null);
  const textId = useId();
  const helpId = useId();
  const validationId = useId();

  useEffect(() => {
    if (!advancedFromPrevious) return;
    advancedFromPrevious = false;
    window.scrollTo({ top: 0 });
    document.getElementById("question-heading")?.focus();
  }, []);

  const locked = feedback !== null || submitting;
  const trimmed = text.trim();

  function buildInput(): AnswerInput | null {
    if (isChoice) {
      if (!selected) {
        setValidation("Choose an option before submitting.");
        return null;
      }
      return { sessionId: session.id, itemId: item.id, selectedOptionKey: selected };
    }
    if (!trimmed) {
      setValidation("Write an answer before submitting.");
      return null;
    }
    if (trimmed.length > MAX_CHARS) {
      setValidation(`Keep your answer under ${MAX_CHARS.toLocaleString()} characters.`);
      return null;
    }
    return { sessionId: session.id, itemId: item.id, responseText: trimmed };
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (locked) return;
    const input = buildInput();
    if (!input) return;
    setValidation(null);
    setError(null);
    startSubmit(async () => {
      const result = await submitAnswer(input);
      if (result.ok) {
        setFeedback(result.data);
        requestAnimationFrame(() => feedbackHeadingRef.current?.focus());
      } else {
        setError({ message: result.error, retryable: result.retryable });
      }
    });
  }

  function advance() {
    // The server decides what comes next; refreshing re-runs the page's fetch.
    advancedFromPrevious = true;
    startAdvance(() => router.refresh());
  }

  const finished = feedback?.session.status === "completed";

  return (
    <div className="flex flex-col gap-5">
      {question.hint && !feedback ? <HintDisclosure hint={question.hint} /> : null}

      <form onSubmit={submit} noValidate aria-label="Your answer" className="flex flex-col gap-3">
        {isChoice ? (
          <fieldset disabled={locked} aria-describedby={validation ? validationId : undefined}>
            <legend className="sr-only">Choose one answer</legend>
            <div className="flex flex-col gap-2">
              {question.options.map((o) => {
                const checked = selected === o.key;
                return (
                  <label
                    key={o.key}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3.5 transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-fg",
                      checked
                        ? "border-fg bg-surface-raised"
                        : "border-line bg-surface hover:border-neutral-600",
                      locked && "cursor-default",
                      locked && !checked && "opacity-60",
                    )}
                  >
                    <input
                      type="radio"
                      name="option"
                      value={o.key}
                      checked={checked}
                      onChange={() => {
                        setSelected(o.key);
                        setValidation(null);
                      }}
                      className="sr-only"
                    />
                    <span
                      aria-hidden="true"
                      className={cn(
                        "flex size-6 shrink-0 items-center justify-center rounded-md border font-mono text-xs uppercase",
                        checked ? "border-fg bg-fg text-canvas" : "border-line text-fg-muted",
                      )}
                    >
                      {o.key}
                    </span>
                    <span className="text-sm leading-6 text-fg">
                      <InlineText text={o.text} />
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ) : (
          <div className="rounded-xl border border-line bg-surface transition-colors focus-within:border-neutral-500">
            <div className="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
              <label htmlFor={textId} className="text-sm font-medium text-fg">
                Your answer
              </label>
              <span className="text-xs text-fg-subtle tabular-nums">
                {trimmed.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
              </span>
            </div>
            <textarea
              id={textId}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setValidation(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  submit();
                }
              }}
              readOnly={locked}
              rows={9}
              maxLength={MAX_CHARS + 500}
              placeholder="Explain your reasoning as you would to a colleague. Mention trade-offs and edge cases."
              aria-describedby={validation ? `${helpId} ${validationId}` : helpId}
              aria-invalid={validation ? true : undefined}
              className="block min-h-48 w-full resize-y bg-transparent px-4 py-3 text-[15px] leading-relaxed text-fg placeholder:text-fg-subtle focus:outline-none read-only:text-fg-muted"
            />
            <p id={helpId} className="border-t border-line-subtle px-4 py-2.5 text-xs text-fg-subtle">
              Written answers are saved and marked for AI evaluation, which
              isn&apos;t available yet. They are not scored.
              <span className="hidden sm:inline"> Press ⌘ Enter to submit.</span>
            </p>
          </div>
        )}

        {validation ? (
          <p id={validationId} role="alert" className="text-sm text-fg">
            {validation}
          </p>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="flex flex-col gap-3 rounded-lg border border-line bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <p className="flex items-start gap-2 text-sm text-fg">
              <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {error.message}
            </p>
            {error.retryable ? (
              <Button variant="secondary" size="sm" onClick={() => submit()}>
                <RotateCcw aria-hidden="true" />
                Retry
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={advance} disabled={advancing}>
                Reload question
              </Button>
            )}
          </div>
        ) : null}

        {!feedback ? (
          <div className="flex justify-end">
            <Button type="submit" disabled={submitting} className="w-full sm:w-auto">
              {submitting ? (
                <>
                  <LoaderCircle className="animate-spin" aria-hidden="true" />
                  Submitting…
                </>
              ) : (
                <>
                  Submit answer
                  <CornerDownLeft aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        ) : null}
      </form>

      {feedback ? (
        <>
          <FeedbackView feedback={feedback} headingRef={feedbackHeadingRef} />
          <div className="flex justify-end border-t border-line-subtle pt-5">
            <Button onClick={advance} disabled={advancing} className="w-full sm:w-auto">
              {advancing ? (
                <>
                  <LoaderCircle className="animate-spin" aria-hidden="true" />
                  Loading…
                </>
              ) : (
                <>
                  {finished ? "See results" : "Next question"}
                  <ArrowRight aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
