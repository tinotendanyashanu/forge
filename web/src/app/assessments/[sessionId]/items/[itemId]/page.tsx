import { ChevronLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { FeedbackView } from "@/components/assessment/feedback-view";
import { QuestionView } from "@/components/assessment/question-view";
import { PageContainer } from "@/components/ui/page-container";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getFeedback } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Answer review" };

type Params = PageProps<"/assessments/[sessionId]/items/[itemId]">["params"];

export default function ReviewPage({
  params,
}: PageProps<"/assessments/[sessionId]/items/[itemId]">) {
  return (
    <PageContainer width="narrow">
      <Suspense
        fallback={
          <LoadingRegion label="Loading answer" className="flex flex-col gap-6">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-7 w-3/4" />
            <Skeleton className="h-80 w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <Review params={params} />
      </Suspense>
    </PageContainer>
  );
}

async function Review({ params }: { params: Params }) {
  const { sessionId, itemId } = await params;
  const feedback = await getFeedback(sessionId, itemId);
  if (!feedback) notFound();

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <Link
        href={`/assessments/${sessionId}`}
        className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted transition-colors hover:text-fg"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        Back to session
      </Link>
      <QuestionView
        question={feedback.question}
        position={feedback.position}
        total={feedback.session.target_question_count}
      />
      <p className="-mt-3 text-xs text-fg-subtle">
        Answered{" "}
        <time dateTime={feedback.answer.submitted_at}>
          {formatDateTime(feedback.answer.submitted_at)}
        </time>
      </p>
      <FeedbackView feedback={feedback} />
    </div>
  );
}
