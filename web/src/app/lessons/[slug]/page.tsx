import { Check, ChevronLeft, CircleAlert, Clock, ExternalLink, Info, ListChecks, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { completeLesson } from "@/app/actions";
import { LessonStatusBadge } from "@/components/lessons/lesson-status";
import { LaunchButton } from "@/components/mastery/launch-button";
import { TrackIcon } from "@/components/tracks/track-icon";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageContainer } from "@/components/ui/page-container";
import { Skeleton } from "@/components/ui/skeleton";
import { Inline, Markdown, slugify } from "@/components/workspace/markdown";
import { getLesson, getLessonProgress } from "@/lib/api";
import { difficultyLabel, formatDateTime } from "@/lib/format";
import type { LessonDetail } from "@/lib/types";

export async function generateMetadata({ params }: PageProps<"/lessons/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const lesson = await getLesson(slug).catch(() => null);
  return { title: lesson ? lesson.title : "Lesson" };
}

export default function LessonPage({ params, searchParams }: PageProps<"/lessons/[slug]">) {
  return (
    <PageContainer className="flex flex-col gap-8">
      <Link
        href="/lessons"
        className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted transition-colors hover:text-fg"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        All lessons
      </Link>
      <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
        <Lesson params={params} searchParams={searchParams} />
      </Suspense>
    </PageContainer>
  );
}

async function Lesson({
  params,
  searchParams,
}: {
  params: PageProps<"/lessons/[slug]">["params"];
  searchParams: PageProps<"/lessons/[slug]">["searchParams"];
}) {
  const [{ slug }, { error }] = await Promise.all([params, searchParams]);
  const [lesson, progress] = await Promise.all([getLesson(slug), getLessonProgress()]);
  if (!lesson) notFound();
  const done = new Map((progress ?? []).map((p) => [p.slug, p.completed_at]));
  const completedAt = done.get(lesson.slug) ?? null;
  const sections = [...lesson.body.matchAll(/^##\s+(.+?)\s*$/gm)].map((m) => m[1]);

  return (
    <article className="flex flex-col gap-10 animate-fade-in">
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3 text-[13px] text-fg-subtle">
          <Link href={`/tracks/${lesson.skill.slug}`} className="inline-flex items-center gap-2 rounded text-fg-muted hover:text-fg">
            <TrackIcon slug={lesson.skill.slug} className="size-6" />
            {lesson.skill.title}
          </Link>
          {lesson.topic ? <span>· {lesson.topic.title}</span> : null}
          <span>· {difficultyLabel[lesson.difficulty]}</span>
          <span className="inline-flex items-center gap-1">
            · <Clock className="size-3.5" aria-hidden="true" /> {lesson.estimated_minutes} min
          </span>
        </div>
        <h1 className="max-w-3xl text-[28px] leading-tight font-semibold tracking-[-0.035em] text-balance text-fg sm:text-[34px]">
          {lesson.title}
        </h1>
        <p className="max-w-2xl text-[15px] leading-7 text-pretty text-fg-muted sm:text-base">{lesson.summary}</p>
        <div className="flex flex-wrap items-center gap-2">
          <LessonStatusBadge status={lesson.status} />
          {completedAt ? (
            <span className="inline-flex items-center gap-1 text-xs text-fg-muted">
              <Check className="size-3.5" aria-hidden="true" />
              Read {formatDateTime(completedAt)}
            </span>
          ) : null}
        </div>
      </header>

      {error ? (
        <p role="alert" className="flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg">
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          That couldn&apos;t be saved. Check that the API is running and try again.
        </p>
      ) : null}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_240px]">
        <div className="flex min-w-0 flex-col gap-10">
          <Card className="flex flex-col gap-3 p-5 sm:p-6">
            <h2 className="flex items-center gap-2 text-[15px] font-medium text-fg">
              <ListChecks className="size-4" aria-hidden="true" />
              By the end you can
            </h2>
            <ul className="ml-5 list-disc space-y-1.5 text-sm leading-relaxed text-fg-muted">
              {lesson.objectives.map((o) => (
                <li key={o}><Inline text={o} /></li>
              ))}
            </ul>
            {lesson.prerequisites.length ? (
              <div className="mt-2 border-t border-line-subtle pt-3">
                <p className="mb-2 text-xs font-medium text-fg-subtle">Read first</p>
                <ul className="flex flex-wrap gap-2">
                  {lesson.prerequisites.map((p) => (
                    <li key={p.slug}>
                      <Link
                        href={`/lessons/${p.slug}`}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-sm text-fg-muted hover:text-fg"
                      >
                        {done.get(p.slug) ? <Check className="size-3.5" aria-label="Read" /> : null}
                        {p.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>

          <Markdown text={lesson.body} prose />

          <Misconceptions lesson={lesson} />
          <References lesson={lesson} />
          <KnowledgeCheck lesson={lesson} completedAt={completedAt} />
        </div>

        <aside aria-label="On this page" className="hidden lg:block">
          <nav className="sticky top-24 flex flex-col gap-2 text-sm">
            <p className="text-xs font-medium text-fg-subtle">On this page</p>
            {sections.map((s) => (
              <a key={s} href={`#${slugify(s)}`} className="rounded text-fg-muted hover:text-fg">
                {s}
              </a>
            ))}
          </nav>
        </aside>
      </div>
    </article>
  );
}

function Misconceptions({ lesson }: { lesson: LessonDetail }) {
  return (
    <section aria-labelledby="misconceptions-heading" className="flex flex-col gap-3">
      <h2 id="misconceptions-heading" className="flex items-center gap-2 text-[15px] font-medium text-fg">
        <TriangleAlert className="size-4" aria-hidden="true" />
        Misconceptions to avoid
      </h2>
      <ul className="flex flex-col gap-2">
        {lesson.misconceptions.map((m) => (
          <li key={m} className="rounded-lg border border-line px-4 py-3 text-sm leading-relaxed text-fg-muted">
            <Inline text={m} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function References({ lesson }: { lesson: LessonDetail }) {
  return (
    <section aria-labelledby="references-heading" className="flex flex-col gap-3">
      <h2 id="references-heading" className="text-[15px] font-medium text-fg">Further reading</h2>
      <ul className="flex flex-col gap-1.5">
        {lesson.resources.map((r) => (
          <li key={r.url}>
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded text-sm text-fg-muted underline-offset-4 hover:text-fg hover:underline"
            >
              {r.title}
              <ExternalLink className="size-3.5" aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function KnowledgeCheck({ lesson, completedAt }: { lesson: LessonDetail; completedAt: string | null }) {
  return (
    <section aria-labelledby="check-heading">
      <Card className="flex flex-col gap-5 p-5 sm:p-6">
        <div>
          <h2 id="check-heading" className="text-[15px] font-medium text-fg">Show what you learned</h2>
          <p className="mt-1.5 flex gap-2 text-sm leading-relaxed text-fg-muted">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Reading a lesson is not evidence of mastery. A scored assessment at this level is, and these questions check this lesson&apos;s objectives.
          </p>
        </div>
        {lesson.checks.length ? (
          <ul className="flex flex-col gap-1 text-sm text-fg-muted">
            {lesson.checks.map((c) => (
              <li key={c.slug} className="flex gap-2">
                <span aria-hidden="true" className="text-fg-subtle">–</span>
                {c.title}
                <span className="text-xs text-fg-subtle">
                  {difficultyLabel[c.difficulty]} · {c.format === "single_choice" ? "scored" : "written"}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <LaunchButton
            activity={{ type: "assessment", skill_slug: lesson.skill.slug, difficulty: lesson.difficulty, mode: null }}
            label={`Take the ${difficultyLabel[lesson.difficulty].toLowerCase()} assessment`}
          />
          {completedAt ? null : (
            <form action={completeLesson}>
              <input type="hidden" name="lesson" value={lesson.slug} />
              <Button type="submit" size="sm" variant="secondary">
                <Check aria-hidden="true" />
                Mark as read
              </Button>
            </form>
          )}
        </div>
        <p className="text-xs text-fg-subtle">
          Version {lesson.version} · updated {formatDateTime(lesson.updated_at)} · {lesson.provenance}
        </p>
      </Card>
    </section>
  );
}
