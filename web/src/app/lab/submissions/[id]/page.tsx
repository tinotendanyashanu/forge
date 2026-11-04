import { ArrowRight, ChevronLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { ReviewPanel } from "@/components/coding/review-panel";
import { TestResults } from "@/components/coding/test-results";
import { ButtonLink } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/rich-text";
import { PageContainer } from "@/components/ui/page-container";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCodeSubmission } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Submission" };

export default function SubmissionPage({ params }: PageProps<"/lab/submissions/[id]">) {
  return (
    <PageContainer className="flex flex-col gap-8">
      <Suspense fallback={<LoadingRegion label="Loading submission"><Skeleton className="h-96 w-full rounded-xl" /></LoadingRegion>}>
        <Submission params={params} />
      </Suspense>
    </PageContainer>
  );
}

async function Submission({ params }: { params: PageProps<"/lab/submissions/[id]">["params"] }) {
  const { id } = await params;
  const s = await getCodeSubmission(id);
  if (!s) notFound();
  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <Link href="/lab/submissions" className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        Submission history
      </Link>
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs text-fg-subtle">
            {s.language} · <time dateTime={s.created_at}>{formatDateTime(s.created_at)}</time> ·{" "}
            {s.verified ? "verified sandbox" : s.executed ? "unverified" : "not executed"}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{s.challenge_title}</h1>
          <p className="mt-2 text-lg tabular-nums text-fg">
            {s.executed ? `${s.passed} of ${s.total} tests passed` : "Tests were not executed"}
          </p>
        </div>
        <ButtonLink href={`/lab/challenges/${s.challenge_slug}`} variant="secondary">
          Back to the challenge
          <ArrowRight aria-hidden="true" />
        </ButtonLink>
      </header>

      <div className="grid gap-8 xl:grid-cols-2">
        <section aria-labelledby="code-heading" className="flex min-w-0 flex-col gap-3">
          <h2 id="code-heading" className="text-sm font-medium text-fg">Your code</h2>
          <CodeBlock code={s.code} language={s.language} />
          <h2 className="mt-4 text-sm font-medium text-fg">Test results</h2>
          <TestResults results={s.results} />
        </section>
        <section aria-labelledby="review-heading" className="flex min-w-0 flex-col gap-3">
          <h2 id="review-heading" className="text-sm font-medium text-fg">AI code review</h2>
          <ReviewPanel submissionId={s.id} initial={s.review} />
          {s.reference_solution ? (
            <>
              <h2 className="mt-4 text-sm font-medium text-fg">Reference solution</h2>
              <CodeBlock code={s.reference_solution} language={s.language} />
              {s.misconceptions ? (
                <ul className="flex flex-col gap-1 text-sm text-fg-muted">
                  {s.misconceptions.map((m) => <li key={m}>– {m}</li>)}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="text-xs text-fg-subtle">The reference solution unlocks after you pass every hidden test.</p>
          )}
        </section>
      </div>
    </div>
  );
}
