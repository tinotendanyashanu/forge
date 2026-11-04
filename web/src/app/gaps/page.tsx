import { ArrowRight, SearchCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getGaps } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { KnowledgeGap } from "@/lib/types";

export const metadata: Metadata = { title: "Knowledge gaps" };

const KIND: Record<KnowledgeGap["kind"], { label: string; note: string }> = {
  recurring_misconception: { label: "Recurring misconception", note: "Seen in more than one evaluation." },
  missing_prerequisite: { label: "Missing prerequisite", note: "Recent misses with a prerequisite not yet demonstrated." },
  repeated_failure: { label: "Repeatedly missed question", note: "The same question missed more than once." },
  inconsistent: { label: "Inconsistent performance", note: "Recent attempts split between successes and misses." },
  missing_concept: { label: "Concept repeatedly missing", note: "From AI evaluations (unverified)." },
};

export default function GapsPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Diagnostics"
        title="Knowledge gaps"
        description="Patterns found in your recorded answers and evaluations. Each gap needs at least two pieces of evidence, so one bad answer never shows up here."
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading gaps" className="flex flex-col gap-3">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <Gaps />
      </Suspense>
    </PageContainer>
  );
}

async function Gaps() {
  const gaps = await getGaps();
  if (!gaps || gaps.length === 0) {
    return (
      <EmptyState
        icon={SearchCheck}
        title={gaps ? "No gaps detected" : "Nothing to analyse yet"}
        description={
          gaps
            ? "No recurring errors, missing prerequisites or inconsistent results in your evidence so far."
            : "Gaps are found from your answers. Complete a few assessments or interviews first."
        }
      />
    );
  }
  return (
    <ol className="flex flex-col gap-3">
      {gaps.map((g, i) => (
        <li key={`${g.kind}-${g.skill.slug}-${g.title}-${i}`}>
          <Card className="p-5">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-medium text-fg-subtle">
                  {KIND[g.kind].label} · {g.skill.title}
                </p>
                <h3 className="mt-1 text-[15px] font-medium text-fg first-letter:uppercase">{g.title}</h3>
              </div>
              <p className="shrink-0 text-xs text-fg-subtle tabular-nums">
                {g.occurrences}× {g.last_seen ? <>· <time dateTime={g.last_seen}>{formatDateTime(g.last_seen)}</time></> : null}
              </p>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-fg-muted">{g.detail}</p>
            {g.evidence.length ? (
              <ul className="mt-3 flex flex-col gap-1 border-l border-line pl-3 text-[13px] text-fg-muted">
                {g.evidence.map((q) => (
                  <li key={q}>“{q}”</li>
                ))}
              </ul>
            ) : null}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-fg-subtle">
              <span>{KIND[g.kind].note}</span>
              <Link
                href={`/tracks/${(g.related_skill ?? g.skill).slug}`}
                className="inline-flex items-center gap-1 rounded text-sm text-fg hover:underline"
              >
                {g.related_skill ? `Go to ${g.related_skill.title}` : `Open ${g.skill.title}`}
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            </div>
          </Card>
        </li>
      ))}
    </ol>
  );
}
