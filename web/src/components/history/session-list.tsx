import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { TrackIcon } from "@/components/tracks/track-icon";
import { difficultyLabel, formatDateTime } from "@/lib/format";
import type { Assessment } from "@/lib/types";

export function SessionList({ sessions }: { sessions: Assessment[] }) {
  return (
    <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {sessions.map((s) => {
        const active = s.status === "active";
        return (
          <li key={s.id}>
            <Link
              href={`/assessments/${s.id}`}
              className="group flex items-center gap-4 px-4 py-3.5 transition-colors duration-150 hover:bg-surface-raised focus-visible:-outline-offset-2 sm:px-5"
            >
              <TrackIcon slug={s.skill.slug} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-fg">
                  {s.skill.title} · {difficultyLabel[s.difficulty]}
                </p>
                <p className="mt-1 text-xs text-fg-subtle tabular-nums">
                  <time dateTime={s.started_at}>{formatDateTime(s.started_at)}</time>
                  {" · "}
                  {s.answered_count} of {s.target_question_count} answered
                </p>
              </div>
              <span
                className={
                  active
                    ? "shrink-0 rounded-md border border-fg px-2 py-0.5 text-xs font-medium text-fg"
                    : "shrink-0 text-xs text-fg-subtle"
                }
              >
                {active ? "Resume" : "Completed"}
              </span>
              <ChevronRight
                className="size-4 shrink-0 text-fg-subtle transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-fg"
                aria-hidden="true"
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
