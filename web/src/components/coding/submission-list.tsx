import { ChevronRight, CircleCheck, CircleDashed, CircleX } from "lucide-react";
import Link from "next/link";

import { formatDateTime } from "@/lib/format";
import type { CodeSubmission } from "@/lib/types";

export function SubmissionList({ submissions }: { submissions: CodeSubmission[] }) {
  return (
    <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {submissions.map((s) => {
        const Icon = !s.executed ? CircleDashed : s.all_passed ? CircleCheck : CircleX;
        return (
          <li key={s.id}>
            <Link
              href={`/lab/submissions/${s.id}`}
              className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-surface-raised focus-visible:-outline-offset-2 sm:px-5"
            >
              <Icon className={s.all_passed ? "size-4 text-fg" : "size-4 text-fg-subtle"} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-fg">{s.challenge_title}</p>
                <p className="mt-1 text-xs text-fg-subtle">
                  {s.language} · <time dateTime={s.created_at}>{formatDateTime(s.created_at)}</time>
                  {s.hints_used ? ` · ${s.hints_used} hint${s.hints_used === 1 ? "" : "s"}` : ""}
                  {s.review_status === "completed" ? " · reviewed" : ""}
                </p>
              </div>
              <span className="shrink-0 text-right text-xs tabular-nums">
                {s.executed ? (
                  <span className={s.all_passed ? "text-fg" : "text-fg-muted"}>{s.passed}/{s.total} tests</span>
                ) : (
                  <span className="text-fg-subtle">Not executed</span>
                )}
                <span className="block text-fg-subtle">{s.verified ? "Verified" : "Unverified"}</span>
              </span>
              <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden="true" />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
