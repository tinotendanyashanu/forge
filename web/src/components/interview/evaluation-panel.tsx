import { CircleCheck, CircleDashed, ExternalLink, Eye, Quote } from "lucide-react";
import type { ReactNode } from "react";

import { InlineText } from "@/components/ui/rich-text";
import { cn } from "@/lib/cn";
import type { EvaluationFull, Reveal } from "@/lib/types";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line-subtle px-5 py-4">
      <h3 className="mb-2.5 text-[13px] font-medium text-fg-subtle">{title}</h3>
      {children}
    </section>
  );
}

const pct = (n: number) => `${Math.round(n * 100)}%`;

/** Criterion-level breakdown. Only rendered for a valid (evaluated) result. */
function ScoreBreakdown({ evaluation }: { evaluation: EvaluationFull }) {
  return (
    <Section title="Rubric breakdown">
      <div className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <p className="text-2xl font-semibold text-fg tabular-nums">
          {pct(evaluation.total_score ?? 0)}
          <span className="ml-1.5 text-xs font-normal text-fg-subtle">evidence-backed score</span>
        </p>
        {evaluation.confidence !== null ? (
          <p className="text-xs text-fg-subtle tabular-nums">
            Grader confidence {pct(evaluation.confidence)}
          </p>
        ) : null}
        {evaluation.model_total_score !== null &&
        evaluation.model_total_score !== evaluation.total_score ? (
          <p className="text-xs text-fg-subtle tabular-nums">
            Model estimate {pct(evaluation.model_total_score)} (unverified, not counted)
          </p>
        ) : null}
      </div>
      <ol className="flex flex-col gap-3">
        {evaluation.criteria.map((c) => (
          <li key={c.criterion_id} className="flex flex-col gap-1.5">
            <div className="flex items-start gap-3">
              <span
                className="mt-1.5 flex shrink-0 gap-0.5"
                role="img"
                aria-label={`${c.score} of ${c.max_score}`}
              >
                {Array.from({ length: c.max_score }, (_, i) => (
                  <span
                    key={i}
                    className={cn("h-1.5 w-4 rounded-full", i < c.score ? "bg-fg" : "bg-line")}
                  />
                ))}
              </span>
              <p className="flex-1 text-sm leading-relaxed text-fg">
                <InlineText text={c.criterion} />
              </p>
              <span
                className={cn(
                  "shrink-0 rounded-md border px-1.5 py-0.5 text-[11px]",
                  c.evidence === "observed"
                    ? "border-fg text-fg"
                    : "border-line text-fg-subtle",
                )}
                title={
                  c.evidence === "inferred"
                    ? "The model gave credit but its quote wasn't found in your answer, so it isn't counted."
                    : undefined
                }
              >
                {c.evidence === "observed" ? "Observed" : c.evidence === "inferred" ? "Inferred" : "Not shown"}
              </span>
            </div>
            {c.evidence_quote ? (
              <p className="ml-12 flex gap-2 text-[13px] leading-relaxed text-fg-muted">
                <Quote className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />
                <span>{c.evidence_quote}</span>
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </Section>
  );
}

export function EvaluationPanel({ reveal }: { reveal: Reveal }) {
  const ev = reveal.final_evaluation;
  const valid = ev !== null && ev.status === "evaluated";

  return (
    <section
      aria-label="Evaluation and reference answer"
      className="overflow-hidden rounded-xl border border-line bg-surface animate-rise-in"
    >
      <div className="flex items-center gap-2 px-5 py-3.5 text-sm font-medium text-fg">
        <Eye className="size-4 text-fg-muted" aria-hidden="true" />
        Review
      </div>

      {valid ? (
        <>
          <ScoreBreakdown evaluation={ev} />
          {ev.demonstrated_concepts.length + ev.missing_concepts.length > 0 ? (
            <Section title="Concepts">
              <ul className="flex flex-wrap gap-1.5">
                {ev.demonstrated_concepts.map((c) => (
                  <li key={`d-${c}`} className="inline-flex items-center gap-1 rounded-md bg-surface-hover px-2 py-0.5 text-xs text-fg">
                    <CircleCheck className="size-3" aria-hidden="true" />
                    {c}
                  </li>
                ))}
                {ev.missing_concepts.map((c) => (
                  <li key={`m-${c}`} className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs text-fg-muted">
                    <CircleDashed className="size-3" aria-hidden="true" />
                    <span className="sr-only">Missing: </span>
                    {c}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
          {ev.misconceptions.length > 0 ? (
            <Section title="Misconceptions in your answer">
              <ul className="flex flex-col gap-2 text-sm text-fg-muted">
                {ev.misconceptions.map((m) => (
                  <li key={m.description}>
                    <span className="text-fg">{m.description}</span>
                    {m.quote ? <span className="block text-[13px]">“{m.quote}”</span> : null}
                    {!m.observed ? <span className="block text-xs text-fg-subtle">Inferred by the model, not quoted.</span> : null}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
          {ev.injection_suspected ? (
            <Section title="Note">
              <p className="text-sm text-fg-muted">
                Your answer contained instructions aimed at the grader. They were ignored and
                this evaluation doesn&apos;t count toward progress.
              </p>
            </Section>
          ) : null}
        </>
      ) : (
        <Section title="Score">
          <p className="text-sm text-fg-muted">
            No valid evaluation exists for this challenge, so no score is shown.
          </p>
        </Section>
      )}

      <Section title="Reference explanation">
        <p className="text-sm leading-relaxed text-fg">
          <InlineText text={reveal.explanation} />
        </p>
      </Section>
      <Section title="Rubric">
        <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm leading-relaxed text-fg-muted marker:text-fg-subtle">
          {reveal.rubric.map((r) => (
            <li key={r}>
              <InlineText text={r} />
            </li>
          ))}
        </ol>
      </Section>
      <Section title="Common misconceptions">
        <ul className="flex flex-col gap-1.5 text-sm text-fg-muted">
          {reveal.known_misconceptions.map((m) => (
            <li key={m}>– <InlineText text={m} /></li>
          ))}
        </ul>
      </Section>
      <Section title="Learn more">
        <ul className="flex flex-col gap-1">
          {reveal.resources.map((r) => (
            <li key={r.url}>
              <a
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded text-sm text-fg underline decoration-line underline-offset-4 hover:decoration-fg"
              >
                {r.title}
                <ExternalLink className="size-3.5 text-fg-subtle" aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
      </Section>
      {valid ? (
        <p className="border-t border-line-subtle px-5 py-3 text-xs text-fg-subtle">
          Graded by {ev.provider} · {ev.model}. Only quotes found in your answer count toward the
          score. A single AI evaluation never changes mastery on its own.
        </p>
      ) : null}
    </section>
  );
}
