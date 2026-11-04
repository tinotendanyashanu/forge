import { ArrowRight, Map as MapIcon, RefreshCw } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { refreshRoadmap } from "@/app/actions";
import { LEVEL_LABEL, STATUS_LABEL, TRACK_LABEL, date, levelLabel } from "@/components/career/format";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { getCareerRoadmap } from "@/lib/api";

export const metadata: Metadata = { title: "Career roadmap" };

const PRIORITY = { critical: "Critical gap", gate: "Mandatory gate", required: "Expected at this level" } as const;

export default function RoadmapPage() {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader
        eyebrow={<Link href="/career" className="hover:text-fg">FORGE Career</Link>}
        title="Your preparation roadmap"
        description="Built from your current evidence: gaps in priority order, why each matters, the FORGE activities that produce evidence, and what 'done' means."
        actions={<form action={refreshRoadmap}><Button type="submit" variant="secondary"><RefreshCw aria-hidden="true" />Rebuild from latest evidence</Button></form>}
      />
      <Suspense fallback={<LoadingRegion label="Loading roadmap"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Roadmap />
      </Suspense>
    </PageContainer>
  );
}

async function Roadmap() {
  const rm = await getCareerRoadmap();
  if (!rm) {
    return <EmptyState icon={MapIcon} title="No roadmap yet" description="Build one from your current evidence. It records a readiness snapshot for your target so you can compare progress later."
      action={<form action={refreshRoadmap}><Button type="submit" size="sm">Build my roadmap</Button></form>} />;
  }
  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-fg-muted">
        {TRACK_LABEL[rm.track]} · {LEVEL_LABEL[rm.target_level]} · {STATUS_LABEL[rm.status]} · built {date(rm.generated_at)}
        {rm.goal ? ` · goal: ${rm.goal}` : ""} · <Link className="underline hover:text-fg" href={`/career/reports/${rm.report_id}`}>source report</Link>
      </p>
      <p className="text-sm text-fg">Reassess on <span className="font-mono">{date(rm.reassess_on)}</span>, or as soon as the first items are complete.</p>
      {rm.items.length === 0 ? <p className="text-sm text-fg-muted">No gaps for this target in the current evidence. Take the formal assessment to confirm.</p> : null}
      <ol className="flex flex-col gap-4">
        {rm.items.map((it, i) => (
          <li key={it.dimension} className="rounded-xl border border-line bg-surface p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs text-fg-subtle">{i + 1}. {PRIORITY[it.priority]} · needs {LEVEL_LABEL[it.needed]} · shown {levelLabel(it.demonstrated)}</p>
                <h2 className="text-base font-medium text-fg">{it.title}</h2>
              </div>
              <span className={cn("rounded-full border px-2 py-0.5 text-[11px]", it.priority === "critical" ? "border-fg text-fg" : "border-line text-fg-muted")}>reassess in {it.reassess_in_days} days</span>
            </div>
            <p className="mt-2 text-[13px] text-fg-muted">{it.why} At {LEVEL_LABEL[it.needed]}: {it.expectation}</p>
            {it.reasons.length ? <p className="mt-1 text-xs text-fg-subtle">Currently: {it.reasons.join("; ")}.</p> : null}
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="mb-1 text-xs font-medium text-fg-subtle">Do next</h3>
                {it.activities.length ? (
                  <ul className="flex flex-col gap-1">
                    {it.activities.map((a) => (
                      <li key={a.href + a.label}><Link href={a.href} className="inline-flex items-center gap-1 text-[13px] text-fg hover:underline">{a.label}<ArrowRight className="size-3" aria-hidden="true" /></Link></li>
                    ))}
                  </ul>
                ) : <p className="text-xs text-fg-subtle">No matching FORGE activity yet.</p>}
                {it.content_note ? <p className="mt-1 text-xs text-fg-subtle">{it.content_note}</p> : null}
              </div>
              <div>
                <h3 className="mb-1 text-xs font-medium text-fg-subtle">Done when</h3>
                <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{it.completion_criteria.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
