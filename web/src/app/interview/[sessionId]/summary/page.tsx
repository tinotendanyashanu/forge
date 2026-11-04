import { ArrowRight, ChevronLeft, CircleCheck, CircleDashed, SkipForward } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { MODE_META } from "@/components/interview/modes";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageContainer } from "@/components/ui/page-container";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getInterviewSummary } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";

export const metadata: Metadata = { title: "Interview summary" };

export default function SummaryPage({ params }: PageProps<"/interview/[sessionId]/summary">) {
  return (
    <PageContainer width="narrow">
      <Suspense
        fallback={
          <LoadingRegion label="Loading summary" className="flex flex-col gap-6">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <Summary params={params} />
      </Suspense>
    </PageContainer>
  );
}

async function Summary({ params }: { params: PageProps<"/interview/[sessionId]/summary">["params"] }) {
  const { sessionId } = await params;
  const summary = await getInterviewSummary(sessionId);
  if (!summary) notFound();
  const { session } = summary;

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <Link href={`/interview/${session.id}`} className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        Back to transcript
      </Link>
      <header>
        <p className="text-[13px] font-medium text-fg-subtle">
          {session.status === "completed" ? "Interview complete" : "Interview in progress"}
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg sm:text-[28px]">
          {session.skill.title} · {MODE_META[session.mode].label}
        </h1>
        <p className="mt-2 text-sm text-fg-muted">
          Started at {difficultyLabel[session.start_difficulty]}, ended at{" "}
          {difficultyLabel[session.current_difficulty]}.
        </p>
      </header>

      <ol className="flex flex-col gap-3">
        {summary.challenges.map((c) => {
          const ev = c.final_evaluation;
          const Icon = c.status === "skipped" ? SkipForward : ev ? CircleCheck : CircleDashed;
          return (
            <li key={c.position}>
              <Card className="flex items-start gap-4 p-4 sm:p-5">
                <Icon className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-fg">{c.question_title}</p>
                  <p className="mt-1 text-xs text-fg-subtle">
                    {difficultyLabel[c.difficulty]} · {c.attempts} attempt{c.attempts === 1 ? "" : "s"} ·{" "}
                    {c.hints_used} hint{c.hints_used === 1 ? "" : "s"} · {c.follow_ups_asked} follow-up
                    {c.follow_ups_asked === 1 ? "" : "s"}
                    {c.said_dont_know ? " · said “I don't know”" : ""}
                  </p>
                </div>
                <p className="shrink-0 text-right text-sm tabular-nums">
                  {ev && ev.total_score !== null ? (
                    <span className="text-fg">{Math.round(ev.total_score * 100)}%</span>
                  ) : (
                    <span className="text-xs text-fg-subtle">
                      {c.status === "skipped" ? "Skipped" : "Not scored"}
                    </span>
                  )}
                </p>
              </Card>
            </li>
          );
        })}
      </ol>

      {summary.misconceptions.length > 0 ? (
        <section aria-labelledby="misconceptions-heading">
          <h2 id="misconceptions-heading" className="mb-3 text-[15px] font-medium text-fg">
            Misconceptions to revisit
          </h2>
          <ul className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4 text-sm text-fg-muted">
            {summary.misconceptions.map((m, i) => (
              <li key={i}>
                <span className="text-fg">{m.description}</span>
                {m.quote ? <span className="block text-[13px]">“{m.quote}”</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <ul className="flex flex-col gap-1 text-xs text-fg-subtle">
        {summary.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>

      <div className="flex flex-col-reverse gap-2 border-t border-line-subtle pt-5 sm:flex-row sm:justify-end">
        <ButtonLink href="/interview" variant="secondary">All interviews</ButtonLink>
        <ButtonLink href={`/interview?skill=${session.skill.slug}&mode=${session.mode}`}>
          New interview
          <ArrowRight aria-hidden="true" />
        </ButtonLink>
      </div>
    </div>
  );
}
