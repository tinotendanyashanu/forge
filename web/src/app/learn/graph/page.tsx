import { ChevronLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { GraphLegend, SkillGraph } from "@/components/mastery/skill-graph";
import { StateBadge } from "@/components/mastery/state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCurriculum, getMastery } from "@/lib/api";
import type { SkillMastery } from "@/lib/types";

export const metadata: Metadata = { title: "Skill graph" };

export default function GraphPage() {
  return (
    <PageContainer className="flex flex-col gap-8">
      <Link href="/learn" className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        Learning path
      </Link>
      <PageHeader
        eyebrow="Curriculum"
        title="Skill graph"
        description="Arrows point from a prerequisite to the skills that build on it. Hover or focus a skill to trace what it depends on."
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading graph">
            <Skeleton className="h-[440px] w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <Graph />
      </Suspense>
    </PageContainer>
  );
}

async function Graph() {
  const [curriculum, overview] = await Promise.all([getCurriculum(), getMastery()]);
  const mastery: Record<string, SkillMastery> = Object.fromEntries(
    (overview?.skills ?? []).map((s) => [s.skill.slug, s]),
  );
  const bySlug = new Map(curriculum.skills.map((s) => [s.slug, s]));
  return (
    <div className="flex flex-col gap-6">
      <SkillGraph skills={curriculum.skills} mastery={mastery} />
      <GraphLegend />
      {/* Equivalent text view of the graph for screen readers and small screens. */}
      <section aria-labelledby="graph-list-heading">
        <h2 id="graph-list-heading" className="mb-3 text-[15px] font-medium text-fg">
          All skills
        </h2>
        <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
          {curriculum.skills.map((s) => (
            <li key={s.slug} className="flex flex-col gap-1 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <Link href={`/tracks/${s.slug}`} className="rounded text-sm font-medium text-fg hover:underline">
                  {s.title}
                </Link>
                <p className="text-xs text-fg-subtle">
                  {s.prerequisites.length
                    ? `Requires ${s.prerequisites.map((p) => bySlug.get(p)?.title).join(", ")}`
                    : "No prerequisites"}
                </p>
              </div>
              {s.assessable ? (
                <StateBadge state={mastery[s.slug]?.state ?? "not_started"} />
              ) : (
                <span className="text-xs text-fg-subtle">No assessments yet</span>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-fg-subtle">Curriculum version {curriculum.version}</p>
      </section>
    </div>
  );
}
