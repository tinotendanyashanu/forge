import { CircleAlert, Compass, Network, Target, X } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { removeGoal, setGoal } from "@/app/actions";
import { LaunchButton } from "@/components/mastery/launch-button";
import { MODE_META } from "@/components/interview/modes";
import { TrackIcon } from "@/components/tracks/track-icon";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCurriculum, getGoals, getRecommendations } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";
import { DIFFICULTIES, type Recommendation } from "@/lib/types";

export const metadata: Metadata = { title: "Learning path" };

const KIND_LABEL: Record<Recommendation["kind"], string> = {
  review: "Review due",
  relearn: "Relearn",
  remediate: "Close a gap",
  prerequisite: "Prerequisite first",
  practice: "Build evidence",
  advance: "Level up",
  start: "Start",
  practical: "Verified practice",
  practical_retry: "Retry a challenge",
};

export default function LearnPage({ searchParams }: PageProps<"/learn">) {
  return (
    <PageContainer className="flex flex-col gap-12">
      <PageHeader
        eyebrow="My learning path"
        title="What to do next, and why"
        description="Recommendations come from your recorded evidence, review schedule, prerequisites and goals. Nothing here is guessed."
        actions={
          <ButtonLink href="/learn/graph" variant="secondary">
            <Network aria-hidden="true" />
            Skill graph
          </ButtonLink>
        }
      />
      <Suspense fallback={null}>
        <ErrorNote searchParams={searchParams} />
      </Suspense>
      <section aria-labelledby="next-heading">
        <SectionHeader id="next-heading" title="Recommended next" />
        <Suspense
          fallback={
            <LoadingRegion label="Loading recommendations" className="flex flex-col gap-3">
              {Array.from({ length: 3 }, (_, i) => (
                <Skeleton key={i} className="h-28 w-full rounded-xl" />
              ))}
            </LoadingRegion>
          }
        >
          <Recommendations />
        </Suspense>
      </section>
      <section aria-labelledby="goals-heading">
        <SectionHeader
          id="goals-heading"
          title="Goals"
          description="Goals pull their skill, and every prerequisite on the way, up your path."
        />
        <Suspense fallback={<Skeleton className="h-32 w-full rounded-xl" />}>
          <Goals />
        </Suspense>
      </section>
    </PageContainer>
  );
}

async function ErrorNote({ searchParams }: { searchParams: PageProps<"/learn">["searchParams"] }) {
  const { error } = await searchParams;
  if (!error) return null;
  return (
    <p role="alert" className="flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg">
      <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
      {error === "goal" ? "That goal couldn't be saved." : "That activity couldn't be started. Check that the API is running and try again."}
    </p>
  );
}

async function Recommendations() {
  const recs = await getRecommendations(6);
  if (!recs || recs.length === 0) {
    return (
      <EmptyState
        icon={Compass}
        title={recs ? "You're up to date" : "Your path starts with a first attempt"}
        description={
          recs
            ? "No reviews are due and nothing new is unlocked right now. Check back after your next review date."
            : "Answer a few questions in any skill and FORGE will build your path from that evidence."
        }
        action={<ButtonLink href="/tracks" size="sm">Browse skills</ButtonLink>}
      />
    );
  }
  return (
    <ol className="flex flex-col gap-3">
      {recs.map((r, i) => (
        <li key={r.key} className="animate-rise-in" style={{ animationDelay: `${i * 30}ms` }}>
          <Card className="flex flex-col gap-5 p-6 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 gap-4">
              <TrackIcon slug={r.skill.slug} />
              <div className="min-w-0">
                <p className="text-xs font-medium text-fg-subtle">
                  {i === 0 ? "Up next · " : ""}
                  {KIND_LABEL[r.kind]}
                </p>
                <h3 className="mt-1.5 text-base font-medium text-fg">
                  {r.skill.title} · {difficultyLabel[r.activity.difficulty]}{" "}
                  <span className="font-normal text-fg-muted">
                    {r.activity.type === "interview" && r.activity.mode
                      ? `${MODE_META[r.activity.mode].label} interview`
                      : r.activity.type === "coding"
                        ? "coding challenge"
                        : "assessment"}
                  </span>
                </h3>
                <ul className="mt-2 flex flex-col gap-1 text-sm leading-relaxed text-fg-muted">
                  {r.reasons.map((reason) => (
                    <li key={reason} className="flex gap-2">
                      <span aria-hidden="true" className="text-fg-subtle">–</span>
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
              <LaunchButton activity={r.activity} variant={i === 0 ? "primary" : "secondary"} />
              {r.interview_alternative ? (
                <LaunchButton
                  activity={r.interview_alternative}
                  variant="ghost"
                  label="Use the AI interviewer"
                />
              ) : null}
            </div>
          </Card>
        </li>
      ))}
    </ol>
  );
}

async function Goals() {
  const [goals, curriculum] = await Promise.all([getGoals(), getCurriculum()]);
  const assessable = curriculum.skills.filter((s) => s.assessable);
  return (
    <Card className="flex flex-col gap-6 p-6">
      {goals && goals.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {goals.map((g) => (
            <li key={g.skill.slug} className="flex items-center gap-2 rounded-full border border-line py-1 pr-1 pl-3 text-sm text-fg">
              <Target className="size-3.5 text-fg-muted" aria-hidden="true" />
              {g.skill.title} · {difficultyLabel[g.target_level]}
              <form action={removeGoal}>
                <input type="hidden" name="skill" value={g.skill.slug} />
                <button
                  type="submit"
                  aria-label={`Remove goal ${g.skill.title}`}
                  className="flex size-6 items-center justify-center rounded-md text-fg-subtle hover:bg-surface-hover hover:text-fg"
                >
                  <X className="size-3.5" aria-hidden="true" />
                </button>
              </form>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-fg-muted">No goals yet. Set one to focus your path.</p>
      )}
      <form action={setGoal} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1.5 text-xs text-fg-subtle">
          Skill
          <select name="skill" required className="forge-field">
            {curriculum.skills.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.title}{s.assessable ? "" : " (no assessments yet)"}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-xs text-fg-subtle">
          Target level
          <select name="level" defaultValue="intermediate" className="forge-field">
            {DIFFICULTIES.map((d) => (
              <option key={d} value={d}>{difficultyLabel[d]}</option>
            ))}
          </select>
        </label>
        <Button type="submit" variant="secondary">Set goal</Button>
      </form>
      <p className="text-xs text-fg-subtle">{assessable.length} of {curriculum.skills.length} skills have assessments today.</p>
    </Card>
  );
}
