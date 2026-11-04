import { CalendarCheck, RotateCcw } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { LaunchButton } from "@/components/mastery/launch-button";
import { TrackIcon } from "@/components/tracks/track-icon";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getMastery, getReviewQueue } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Activity, Difficulty } from "@/lib/types";

export const metadata: Metadata = { title: "Daily review" };

export default function ReviewPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Spaced repetition"
        title="Daily review"
        description="Skills come back when you're about to forget them (SM-2 scheduling). Passing pushes the next review further out; missing brings it back tomorrow."
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading reviews" className="flex flex-col gap-3">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <Queue />
      </Suspense>
    </PageContainer>
  );
}

async function Queue() {
  const [queue, overview] = await Promise.all([getReviewQueue(), getMastery()]);
  if (!queue) {
    return (
      <EmptyState
        icon={CalendarCheck}
        title="No reviews scheduled"
        description="Reviews are scheduled from your answers. Complete an assessment or interview and the first review will appear here."
      />
    );
  }
  const levels = new Map<string, Difficulty>(
    (overview?.skills ?? []).map((s) => [s.skill.slug, s.demonstrated_level ?? "beginner"]),
  );

  return (
    <>
      <section aria-labelledby="due-heading">
        <SectionHeader
          id="due-heading"
          title="Due today"
          description={
            queue.total_due > queue.due.length
              ? `${queue.total_due} due. Showing the ${queue.daily_limit} most important; the rest wait for tomorrow.`
              : `Up to ${queue.daily_limit} a day, most overdue and weakest first.`
          }
        />
        {queue.due.length === 0 ? (
          <EmptyState
            icon={CalendarCheck}
            title="Nothing due"
            description="You're caught up. Skills you reviewed today won't reappear until tomorrow at the earliest."
          />
        ) : (
          <ol className="flex flex-col gap-3">
            {queue.due.map((c) => {
              const activity: Activity = {
                type: c.needs_relearning ? "interview" : "assessment",
                skill_slug: c.skill.slug,
                difficulty: levels.get(c.skill.slug) ?? "beginner",
                mode: c.needs_relearning ? "tutor" : null,
              };
              return (
                <li key={c.skill.slug}>
                  <Card className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex gap-4">
                      <TrackIcon slug={c.skill.slug} />
                      <div>
                        <h3 className="text-[15px] font-medium text-fg">{c.skill.title}</h3>
                        <p className="mt-1 text-sm text-fg-muted tabular-nums">
                          {c.overdue_days > 0 ? `${c.overdue_days} day${c.overdue_days === 1 ? "" : "s"} overdue` : "Due today"}
                          {" · "}interval {c.interval_days} day{c.interval_days === 1 ? "" : "s"}
                          {c.lapses ? ` · ${c.lapses} lapse${c.lapses === 1 ? "" : "s"}` : ""}
                          {c.missed_reviews ? ` · ${c.missed_reviews} missed` : ""}
                        </p>
                        {c.needs_relearning ? (
                          <p className="mt-1 flex items-center gap-1.5 text-xs text-fg-subtle">
                            <RotateCcw className="size-3.5" aria-hidden="true" />
                            Several reviews in a row were missed, so this is a guided relearn.
                          </p>
                        ) : null}
                      </div>
                    </div>
                    <LaunchButton activity={activity} label="Review now" />
                  </Card>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section aria-labelledby="upcoming-heading">
        <SectionHeader id="upcoming-heading" title="Coming up this week" />
        {queue.upcoming.length === 0 ? (
          <p className="text-sm text-fg-muted">Nothing scheduled in the next seven days.</p>
        ) : (
          <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
            {queue.upcoming.map((c) => (
              <li key={c.skill.slug} className="flex items-center justify-between gap-4 px-5 py-3.5 text-sm">
                <span className="text-fg">{c.skill.title}</span>
                <span className="text-xs text-fg-subtle tabular-nums">
                  <time dateTime={c.due_at}>{formatDateTime(c.due_at)}</time> · every {c.interval_days} day
                  {c.interval_days === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
