import { Check, Clock, GraduationCap } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { LessonStatusBadge } from "@/components/lessons/lesson-status";
import { TrackIcon } from "@/components/tracks/track-icon";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getLessonProgress, getLessons } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";
import type { LessonSummary, Ref } from "@/lib/types";

export const metadata: Metadata = { title: "Lessons" };

export default function LessonsPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Learn"
        title="Lessons"
        description="Learn a concept before you are assessed on it. Each lesson ends with scored questions; reading alone never counts as mastery."
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading lessons" className="flex flex-col gap-3">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-xl" />
            ))}
          </LoadingRegion>
        }
      >
        <LessonList />
      </Suspense>
    </PageContainer>
  );
}

async function LessonList() {
  const [lessons, progress] = await Promise.all([getLessons(), getLessonProgress()]);
  if (lessons.length === 0) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="No lessons yet"
        description="Lessons appear here once they have been loaded with the seed command."
      />
    );
  }
  const done = new Set((progress ?? []).filter((p) => p.completed_at).map((p) => p.slug));
  const groups = new Map<string, { skill: Ref; lessons: LessonSummary[] }>();
  for (const lesson of lessons) {
    const group = groups.get(lesson.skill.slug) ?? { skill: lesson.skill, lessons: [] };
    group.lessons.push(lesson);
    groups.set(lesson.skill.slug, group);
  }

  return (
    <div className="flex flex-col gap-10">
      <p className="text-sm text-fg-muted">
        {done.size} of {lessons.length} read
      </p>
      {[...groups.values()].map(({ skill, lessons: items }) => (
        <section key={skill.slug} aria-labelledby={`skill-${skill.slug}`} className="flex flex-col gap-3">
          <h2 id={`skill-${skill.slug}`} className="flex items-center gap-3 text-[15px] font-medium text-fg">
            <TrackIcon slug={skill.slug} className="size-7" />
            {skill.title}
          </h2>
          <ul className="grid gap-3 md:grid-cols-2">
            {items.map((lesson) => (
              <li key={lesson.slug}>
                <Link href={`/lessons/${lesson.slug}`} className="group block h-full rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg">
                  <Card className="flex h-full flex-col gap-3 p-5 transition-colors group-hover:border-neutral-600">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-[15px] font-medium text-fg">{lesson.title}</h3>
                      {done.has(lesson.slug) ? (
                        <span className="flex shrink-0 items-center gap-1 text-xs text-fg-muted">
                          <Check className="size-3.5" aria-hidden="true" />
                          Read
                        </span>
                      ) : null}
                    </div>
                    <p className="text-sm leading-relaxed text-pretty text-fg-muted">{lesson.summary}</p>
                    <div className="mt-auto flex flex-wrap items-center gap-2 pt-1 text-xs text-fg-subtle">
                      <span>{difficultyLabel[lesson.difficulty]}</span>
                      <span aria-hidden="true">·</span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="size-3.5" aria-hidden="true" />
                        {lesson.estimated_minutes} min
                      </span>
                      {lesson.topic ? (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>{lesson.topic.title}</span>
                        </>
                      ) : null}
                      <span className="ml-auto">
                        <LessonStatusBadge status={lesson.status} />
                      </span>
                    </div>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
