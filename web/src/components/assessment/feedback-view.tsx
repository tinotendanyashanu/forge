import {
  Check,
  CircleCheck,
  CircleX,
  ExternalLink,
  Hourglass,
  X,
} from "lucide-react";
import type { ReactNode, Ref } from "react";

import { InlineText } from "@/components/ui/rich-text";
import { cn } from "@/lib/cn";
import type { Feedback } from "@/lib/types";

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-line-subtle px-5 py-4">
      <h3 className="mb-2.5 text-[13px] font-medium text-fg-subtle">{title}</h3>
      {children}
    </section>
  );
}

function Outcome({ feedback }: { feedback: Feedback }) {
  const { evaluation } = feedback;
  const pending = evaluation.status === "pending_ai_evaluation";
  const Icon = pending ? Hourglass : evaluation.is_correct ? CircleCheck : CircleX;
  const label = pending
    ? "Saved, not scored"
    : evaluation.is_correct
      ? "Correct"
      : "Incorrect";
  return (
    <div className="flex items-start gap-3">
      <Icon
        className={cn(
          "mt-0.5 size-5 shrink-0",
          pending || !evaluation.is_correct ? "text-fg-muted" : "text-fg",
        )}
        aria-hidden="true"
      />
      <div>
        <p className="text-[15px] font-medium text-fg">{label}</p>
        <p className="mt-1 text-sm leading-relaxed text-fg-muted">
          {evaluation.summary}
        </p>
      </div>
    </div>
  );
}

/**
 * Everything revealed after submission. Free-text answers are never scored
 * here; they show the rubric for self-review; the AI interviewer evaluates written answers.
 */
export function FeedbackView({
  feedback,
  headingRef,
}: {
  feedback: Feedback;
  headingRef?: Ref<HTMLHeadingElement>;
}) {
  const isChoice = feedback.question.format === "single_choice";
  const chosen = feedback.answer.selected_option_key;

  return (
    <section
      aria-labelledby="feedback-heading"
      className="overflow-hidden rounded-xl border border-line bg-surface animate-rise-in"
    >
      <div className="px-5 py-4">
        <h2
          id="feedback-heading"
          ref={headingRef}
          tabIndex={-1}
          className="sr-only"
        >
          Feedback
        </h2>
        <Outcome feedback={feedback} />
      </div>

      {isChoice ? (
        <Section title="Options">
          <ul className="flex flex-col gap-1.5">
            {feedback.options.map((o) => {
              const picked = o.key === chosen;
              return (
                <li
                  key={o.key}
                  className={cn(
                    "flex items-start gap-3 rounded-lg border px-3 py-2.5 text-sm",
                    o.is_correct
                      ? "border-fg text-fg"
                      : picked
                        ? "border-line text-fg-muted line-through decoration-fg-subtle"
                        : "border-transparent text-fg-subtle",
                  )}
                >
                  <span className="w-4 shrink-0 font-mono text-xs uppercase leading-5">
                    {o.key}
                  </span>
                  <span className="flex-1 leading-5">
                    <InlineText text={o.text} />
                  </span>
                  <span className="shrink-0 text-xs leading-5 no-underline">
                    {o.is_correct ? (
                      <span className="inline-flex items-center gap-1 text-fg">
                        <Check className="size-3.5" aria-hidden="true" />
                        Correct answer
                      </span>
                    ) : picked ? (
                      <span className="inline-flex items-center gap-1">
                        <X className="size-3.5" aria-hidden="true" />
                        Your answer
                      </span>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : (
        <Section title="Your answer">
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-fg-muted">
            {feedback.answer.response_text}
          </p>
        </Section>
      )}

      <Section title="Explanation">
        <p className="text-sm leading-relaxed text-fg">
          <InlineText text={feedback.explanation} />
        </p>
      </Section>

      <Section title={isChoice ? "What a strong explanation covers" : "Rubric"}>
        <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm leading-relaxed text-fg-muted marker:text-fg-subtle">
          {feedback.rubric.map((r) => (
            <li key={r}>
              <InlineText text={r} />
            </li>
          ))}
        </ol>
      </Section>

      <div className="grid sm:grid-cols-2">
        <Section title="Key concepts">
          <ul className="flex flex-wrap gap-1.5">
            {feedback.expected_concepts.map((c) => (
              <li
                key={c}
                className="rounded-md bg-surface-hover px-2 py-0.5 text-xs text-fg-muted"
              >
                <InlineText text={c} />
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Common misconceptions">
          <ul className="flex flex-col gap-1.5 text-sm leading-relaxed text-fg-muted">
            {feedback.misconceptions.map((m) => (
              <li key={m} className="flex gap-2">
                <span aria-hidden="true" className="text-fg-subtle">
                  –
                </span>
                <span>
                  <InlineText text={m} />
                </span>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <Section title="Learn more">
        <ul className="flex flex-col gap-1">
          {feedback.resources.map((r) => (
            <li key={r.url}>
              <a
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded text-sm text-fg underline decoration-line underline-offset-4 transition-colors hover:decoration-fg"
              >
                {r.title}
                <ExternalLink className="size-3.5 text-fg-subtle" aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
      </Section>
    </section>
  );
}
