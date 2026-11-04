import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { difficultyLabel, pluralize } from "@/lib/format";
import { DIFFICULTIES, type SkillSummary } from "@/lib/types";

import { TrackIcon } from "./track-icon";

export function TrackCard({ skill }: { skill: SkillSummary }) {
  return (
    <Link href={`/tracks/${skill.slug}`} className="group block h-full rounded-2xl">
      <Card className="flex h-full flex-col p-6 transition-colors duration-150 group-hover:border-fg-subtle group-hover:bg-surface-raised">
        <div className="flex items-start justify-between gap-3">
          <TrackIcon slug={skill.slug} />
          <ArrowRight
            className="mt-1 size-4 text-fg-subtle transition-colors duration-150 group-hover:text-fg group-focus-visible:text-fg"
            aria-hidden="true"
          />
        </div>
        <h3 className="mt-5 text-base font-medium text-fg">{skill.title}</h3>
        <p className="mt-2 text-sm leading-6 text-fg-muted">
          {skill.summary}
        </p>
        <dl className="mt-auto flex flex-wrap gap-x-3 gap-y-1 pt-6 text-xs text-fg-subtle tabular-nums">
          {DIFFICULTIES.map((d) => (
            <div key={d} className="flex gap-1">
              <dt>{difficultyLabel[d]}</dt>
              <dd className="text-fg-muted">
                {skill.questions_by_difficulty[d] ?? 0}
              </dd>
            </div>
          ))}
        </dl>
        <span className="sr-only">
          {pluralize(skill.question_count, "question")} in{" "}
          {pluralize(skill.topic_count, "topic")}
        </span>
      </Card>
    </Link>
  );
}

export function TrackGrid({
  skills,
  className,
}: {
  skills: SkillSummary[];
  className?: string;
}) {
  return (
    <ul
      className={cn(
        "grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3",
        className,
      )}
    >
      {skills.map((skill, i) => (
        <li
          key={skill.slug}
          className="animate-rise-in"
          style={{ animationDelay: `${i * 25}ms` }}
        >
          <TrackCard skill={skill} />
        </li>
      ))}
    </ul>
  );
}

export function TrackGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <Card key={i} className="p-6">
          <Skeleton className="size-11 rounded-xl" />
          <Skeleton className="mt-4 h-4 w-2/5" />
          <Skeleton className="mt-3 h-3.5 w-full" />
          <Skeleton className="mt-2 h-3.5 w-3/4" />
          <Skeleton className="mt-6 h-3 w-4/5" />
        </Card>
      ))}
    </div>
  );
}
