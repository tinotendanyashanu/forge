import { ChevronRight, MessagesSquare, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { MODE_META } from "@/components/interview/modes";
import { StartInterviewForm } from "@/components/interview/start-interview-form";
import { TrackIcon } from "@/components/tracks/track-icon";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getInterviews, getLlmStatus, getSkills } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { INTERVIEW_MODES, type InterviewMode } from "@/lib/types";

export const metadata: Metadata = { title: "Interview" };

export default function InterviewPage({ searchParams }: PageProps<"/interview">) {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="AI interviewer"
        title="Reason it through, out loud"
        description="One focused question at a time. Answer in your own words; the interviewer follows up on gaps before revealing the reference answer."
      />
      <Suspense fallback={<Skeleton className="h-[480px] w-full rounded-xl" />}>
        <Start searchParams={searchParams} />
      </Suspense>
      <section aria-labelledby="recent-interviews">
        <SectionHeader id="recent-interviews" title="Recent interviews" />
        <Suspense
          fallback={
            <LoadingRegion label="Loading interviews">
              <Skeleton className="h-32 w-full rounded-xl" />
            </LoadingRegion>
          }
        >
          <Recent />
        </Suspense>
      </section>
    </PageContainer>
  );
}

async function Start({ searchParams }: { searchParams: PageProps<"/interview">["searchParams"] }) {
  const [skills, status, params] = await Promise.all([getSkills(), getLlmStatus(), searchParams]);
  const skill = typeof params.skill === "string" ? params.skill : undefined;
  const modeParam = typeof params.mode === "string" ? params.mode : undefined;
  const mode = INTERVIEW_MODES.includes(modeParam as InterviewMode) ? (modeParam as InterviewMode) : undefined;

  return (
    <div className="flex flex-col gap-4">
      {status && !status.configured ? (
        <p role="note" className="flex items-start gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg-muted">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium text-fg">AI evaluation isn&apos;t configured.</span>{" "}
            You can still practise. Answers are saved but won&apos;t be graded until an LLM
            provider is set in the API&apos;s environment.
          </span>
        </p>
      ) : status && !status.reachable ? (
        <p role="note" className="flex items-start gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg-muted">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium text-fg">{status.model} isn&apos;t reachable right now.</span>{" "}
            Answers will be saved and you can retry evaluation later.
          </span>
        </p>
      ) : null}
      <Card className="p-5 sm:p-6">
        <StartInterviewForm
          skills={skills.filter((s) => s.question_count > 0)}
          defaultSkill={skill}
          defaultMode={mode}
        />
      </Card>
    </div>
  );
}

async function Recent() {
  const sessions = await getInterviews(8);
  if (!sessions || sessions.length === 0) {
    return (
      <EmptyState
        icon={MessagesSquare}
        title="No interviews yet"
        description="Your interviews, follow-ups and evaluations are saved, so you can come back to any of them."
      />
    );
  }
  return (
    <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {sessions.map((s) => (
        <li key={s.id}>
          <Link
            href={s.status === "active" ? `/interview/${s.id}` : `/interview/${s.id}/summary`}
            className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-surface-raised focus-visible:-outline-offset-2 sm:px-5"
          >
            <TrackIcon slug={s.skill.slug} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-fg">
                {s.skill.title} · {MODE_META[s.mode].label}
              </p>
              <p className="mt-1 text-xs text-fg-subtle tabular-nums">
                <time dateTime={s.started_at}>{formatDateTime(s.started_at)}</time> ·{" "}
                {s.challenges_finished} of {s.target_challenge_count} challenges
              </p>
            </div>
            <span className={s.status === "active" ? "rounded-md border border-fg px-2 py-0.5 text-xs text-fg" : "text-xs text-fg-subtle"}>
              {s.status === "active" ? "Resume" : "Summary"}
            </span>
            <ChevronRight className="size-4 text-fg-subtle" aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
