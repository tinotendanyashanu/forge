import { ArrowRight, BookOpen, History, Play } from "lucide-react";
import { Suspense } from "react";

import { SessionList } from "@/components/history/session-list";
import { TrackGrid, TrackGridSkeleton } from "@/components/tracks/track-card";
import { TrackIcon } from "@/components/tracks/track-icon";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getSessions, getSkills } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";

export default function DashboardPage() {
  return (
    <PageContainer className="flex flex-col gap-12">
      <PageHeader
        eyebrow="Dashboard"
        title="Practise the way senior engineers think."
        description="Pick a skill and a difficulty, answer real questions, and get feedback grounded in a rubric. Multiple-choice answers are graded; written answers are saved, not scored. The AI interviewer evaluates written answers."
        actions={
          <ButtonLink href="/tracks" variant="secondary">
            <BookOpen aria-hidden="true" />
            Browse skills
          </ButtonLink>
        }
      />

      <Suspense fallback={<Skeleton className="h-28 w-full rounded-xl" />}>
        <ResumeCard />
      </Suspense>

      <section aria-labelledby="skills-heading">
        <SectionHeader
          id="skills-heading"
          title="Skill tracks"
          description="The curriculum, in prerequisite order. Skills without questions yet are marked."
          action={
            <ButtonLink href="/tracks" variant="ghost" size="sm">
              View all
              <ArrowRight aria-hidden="true" />
            </ButtonLink>
          }
        />
        <Suspense
          fallback={
            <LoadingRegion label="Loading skills">
              <TrackGridSkeleton />
            </LoadingRegion>
          }
        >
          <Skills />
        </Suspense>
      </section>

      <section aria-labelledby="recent-heading">
        <SectionHeader id="recent-heading" title="Recent sessions" />
        <Suspense
          fallback={
            <LoadingRegion label="Loading sessions">
              <Skeleton className="h-40 w-full rounded-xl" />
            </LoadingRegion>
          }
        >
          <RecentSessions />
        </Suspense>
      </section>
    </PageContainer>
  );
}

async function Skills() {
  const skills = await getSkills();
  if (skills.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No skills published"
        description="The database has no skills yet. Run `python -m app.seed` in the api directory."
      />
    );
  }
  return <TrackGrid skills={skills} />;
}

async function ResumeCard() {
  const sessions = await getSessions(10);
  const active = sessions?.find((s) => s.status === "active");
  if (!active) return null;
  return (
    <Card className="flex flex-col gap-5 p-5 animate-rise-in sm:flex-row sm:items-center sm:justify-between sm:p-6">
      <div className="flex min-w-0 items-center gap-4">
        <TrackIcon slug={active.skill.slug} className="size-11" />
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-fg-subtle">Continue where you left off</p>
          <p className="mt-1 truncate text-lg font-semibold tracking-tight text-fg">
            {active.skill.title} · {difficultyLabel[active.difficulty]}
          </p>
          <p className="mt-0.5 text-sm text-fg-muted tabular-nums">
            {active.answered_count} of {active.target_question_count} answered
          </p>
        </div>
      </div>
      <ButtonLink href={`/assessments/${active.id}`} className="w-full sm:w-auto">
        <Play aria-hidden="true" />
        Resume
      </ButtonLink>
    </Card>
  );
}

async function RecentSessions() {
  const sessions = await getSessions(5);
  if (!sessions || sessions.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No sessions yet"
        description="Start an assessment from any skill track. Your sessions and answers are saved, so you can come back to them later."
        action={
          <ButtonLink href="/tracks" variant="secondary" size="sm">
            Choose a skill
          </ButtonLink>
        }
      />
    );
  }
  return <SessionList sessions={sessions} />;
}
