import { ChevronLeft, History } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { STATE_LABEL, StateDot } from "@/components/mastery/state";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getMasteryHistory } from "@/lib/api";
import { difficultyLabel, formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Progress history" };

export default function HistoryPage() {
  return (
    <PageContainer width="narrow" className="flex flex-col gap-8">
      <Link href="/progress" className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        Progress
      </Link>
      <PageHeader
        eyebrow="Progress"
        title="Progress history"
        description="Every change in demonstrated level or mastery state, with the evidence-based reason. Recorded once per change."
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading history">
            <Skeleton className="h-64 w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <Timeline />
      </Suspense>
    </PageContainer>
  );
}

async function Timeline() {
  const events = await getMasteryHistory(100);
  if (!events || events.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No history yet"
        description="Changes appear here as your evidence builds up, for example when you first demonstrate a level."
      />
    );
  }
  return (
    <ol className="relative flex flex-col gap-5 border-l border-line pl-6">
      {events.map((e, i) => (
        <li key={`${e.skill.slug}-${e.occurred_at}-${i}`} className="relative">
          <span className="absolute top-1.5 -left-[29px] flex size-2.5 items-center justify-center bg-canvas">
            <StateDot state={e.to_state} />
          </span>
          <p className="text-xs text-fg-subtle tabular-nums">
            <time dateTime={e.occurred_at}>{formatDateTime(e.occurred_at)}</time>
          </p>
          <p className="mt-1 text-sm text-fg">
            <Link href={`/tracks/${e.skill.slug}`} className="font-medium hover:underline">
              {e.skill.title}
            </Link>
            {": "}
            {e.from_state ? `${STATE_LABEL[e.from_state]} → ` : ""}
            {STATE_LABEL[e.to_state]}
            {e.to_level && e.to_level !== e.from_level ? ` (${difficultyLabel[e.to_level]} demonstrated)` : ""}
          </p>
          <p className="mt-0.5 text-sm text-fg-muted">{e.reason}</p>
        </li>
      ))}
    </ol>
  );
}
