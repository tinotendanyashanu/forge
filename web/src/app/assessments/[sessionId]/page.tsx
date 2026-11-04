import { ChevronLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { QuestionRunner } from "@/components/assessment/question-runner";
import { QuestionView } from "@/components/assessment/question-view";
import { SessionSummary } from "@/components/assessment/session-summary";
import { PageContainer } from "@/components/ui/page-container";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getAnswerHistory, getNextQuestion } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";

export const metadata: Metadata = { title: "Assessment" };

export default function AssessmentPage({
  params,
}: PageProps<"/assessments/[sessionId]">) {
  return (
    <PageContainer width="narrow">
      <Suspense fallback={<AssessmentSkeleton />}>
        <Assessment params={params} />
      </Suspense>
    </PageContainer>
  );
}

async function Assessment({
  params,
}: {
  params: PageProps<"/assessments/[sessionId]">["params"];
}) {
  const { sessionId } = await params;
  // Idempotent: returns the same question until it is answered, so a refresh
  // resumes exactly where the learner left off.
  const next = await getNextQuestion(sessionId);
  if (!next) notFound();

  if (next.status === "completed") {
    const answers = (await getAnswerHistory({ sessionId, limit: 100 })) ?? [];
    return <SessionSummary session={next.session} answers={[...answers].reverse()} />;
  }

  const { session, item } = next;
  const progress = Math.round((session.answered_count / session.target_question_count) * 100);

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <div className="flex flex-col gap-3">
        <Link
          href={`/tracks/${session.skill.slug}`}
          className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted transition-colors hover:text-fg"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
          {session.skill.title} · {difficultyLabel[session.difficulty]}
        </Link>
        <div
          role="progressbar"
          aria-label="Assessment progress"
          aria-valuemin={0}
          aria-valuemax={session.target_question_count}
          aria-valuenow={session.answered_count}
          aria-valuetext={`${session.answered_count} of ${session.target_question_count} answered`}
          className="h-1 overflow-hidden rounded-full bg-surface-hover"
        >
          <div
            className="h-full rounded-full bg-fg transition-[width] duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <QuestionView
        question={item.question}
        position={item.position}
        total={session.target_question_count}
      />
      {/* Keyed by item so local answer state resets for each new question. */}
      <QuestionRunner key={item.id} session={session} item={item} />
    </div>
  );
}

function AssessmentSkeleton() {
  return (
    <LoadingRegion label="Loading question" className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-1 w-full" />
      </div>
      <div>
        <Skeleton className="h-3.5 w-36" />
        <Skeleton className="mt-3 h-7 w-3/4" />
        <Skeleton className="mt-4 h-5 w-64" />
      </div>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-xl" />
        ))}
      </div>
    </LoadingRegion>
  );
}
