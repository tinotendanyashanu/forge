import { ArrowRight, Flag } from "lucide-react";

import { AnswerHistoryList } from "@/components/history/answer-history-list";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { difficultyLabel } from "@/lib/format";
import type { AnswerHistoryItem, Assessment } from "@/lib/types";

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="rounded-lg border border-line-subtle px-4 py-3">
      <dt className="text-xs text-fg-subtle">{label}</dt>
      <dd className="mt-1 text-xl font-semibold text-fg tabular-nums">{value}</dd>
      {note ? <dd className="mt-0.5 text-xs text-fg-subtle">{note}</dd> : null}
    </div>
  );
}

export function SessionSummary({
  session,
  answers,
}: {
  session: Assessment;
  answers: AnswerHistoryItem[];
}) {
  const graded = answers.filter((a) => a.evaluation_status === "graded");
  const correct = graded.filter((a) => a.is_correct).length;
  const pending = answers.length - graded.length;

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <header>
        <p className="flex items-center gap-2 text-[13px] font-medium text-fg-subtle">
          <Flag className="size-4" aria-hidden="true" />
          Assessment complete
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg sm:text-[28px]">
          {session.skill.title} · {difficultyLabel[session.difficulty]}
        </h1>
      </header>

      <Card className="p-5">
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Stat label="Answered" value={answers.length} />
          <Stat
            label="Multiple choice correct"
            value={correct}
            note={`of ${graded.length} graded`}
          />
          <Stat label="Written answers" value={pending} note="Not scored" />
        </dl>
        <p className="mt-4 text-xs leading-relaxed text-fg-subtle">
          These are counts from this session only, not a measure of mastery.
          Written answers in assessments are saved but never scored: compare them with the model answer, or practise explaining the topic in the AI interviewer, where written answers are evaluated.
        </p>
      </Card>

      <section aria-labelledby="answers-heading">
        <h2 id="answers-heading" className="mb-4 text-[15px] font-medium text-fg">
          Your answers
        </h2>
        {answers.length > 0 ? (
          <AnswerHistoryList items={answers} showSkill={false} />
        ) : (
          <EmptyState
            icon={Flag}
            title="No answers in this session"
            description="The question pool changed before any questions were answered."
          />
        )}
      </section>

      <div className="flex flex-col-reverse gap-2 border-t border-line-subtle pt-5 sm:flex-row sm:justify-end">
        <ButtonLink href="/progress" variant="secondary">
          View progress
        </ButtonLink>
        <ButtonLink href={`/tracks/${session.skill.slug}`}>
          Start another
          <ArrowRight aria-hidden="true" />
        </ButtonLink>
      </div>
    </div>
  );
}
