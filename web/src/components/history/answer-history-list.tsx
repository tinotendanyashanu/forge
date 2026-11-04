import { ChevronRight, CircleCheck, CircleX, Hourglass } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/cn";
import { difficultyLabel, formatDateTime, formatLabel, outcomeLabel } from "@/lib/format";
import type { AnswerHistoryItem } from "@/lib/types";

function OutcomeIcon({ item }: { item: AnswerHistoryItem }) {
  if (item.evaluation_status === "pending_ai_evaluation") {
    return <Hourglass className="size-4 text-fg-subtle" aria-hidden="true" />;
  }
  return item.is_correct ? (
    <CircleCheck className="size-4 text-fg" aria-hidden="true" />
  ) : (
    <CircleX className="size-4 text-fg-subtle" aria-hidden="true" />
  );
}

export function AnswerHistoryList({
  items,
  showSkill = true,
}: {
  items: AnswerHistoryItem[];
  showSkill?: boolean;
}) {
  return (
    <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {items.map((a) => (
        <li key={a.answer_id}>
          <Link
            href={`/assessments/${a.session_id}/items/${a.item_id}`}
            className="group flex items-center gap-4 px-4 py-3.5 transition-colors duration-150 hover:bg-surface-raised focus-visible:-outline-offset-2 sm:px-5"
          >
            <OutcomeIcon item={a} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-fg">{a.question_title}</p>
              <p className="mt-1 flex flex-wrap gap-x-2 text-xs text-fg-subtle">
                {showSkill ? <span>{a.skill.title}</span> : null}
                {showSkill ? <span aria-hidden="true">·</span> : null}
                <span>{difficultyLabel[a.difficulty]}</span>
                <span aria-hidden="true">·</span>
                <span>{formatLabel[a.format]}</span>
              </p>
            </div>
            <div className="hidden shrink-0 text-right sm:block">
              <p
                className={cn(
                  "text-xs",
                  a.evaluation_status === "graded" && a.is_correct ? "text-fg" : "text-fg-muted",
                )}
              >
                {outcomeLabel(a.evaluation_status, a.is_correct)}
              </p>
              <p className="mt-1 text-xs text-fg-subtle tabular-nums">
                <time dateTime={a.submitted_at}>{formatDateTime(a.submitted_at)}</time>
              </p>
            </div>
            <span className="sr-only sm:hidden">
              {outcomeLabel(a.evaluation_status, a.is_correct)}
            </span>
            <ChevronRight
              className="size-4 shrink-0 text-fg-subtle transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-fg"
              aria-hidden="true"
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}
