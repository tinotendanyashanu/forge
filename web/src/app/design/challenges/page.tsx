import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { COMPETENCY_LABEL, LEVEL_LABEL } from "@/components/design/components";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getDesignChallenges, getDesignDashboard } from "@/lib/api";
import { DESIGN_LEVELS } from "@/lib/types";

export const metadata: Metadata = { title: "Design challenges" };

export default function DesignChallengesPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow={<Link href="/design" className="hover:text-fg">Design lab</Link>}
        title="Design challenges"
        description="Versioned scenarios from beginner to senior. Every figure in a challenge is hypothetical and exists to drive design reasoning."
      />
      <Suspense fallback={<LoadingRegion label="Loading challenges"><Skeleton className="h-96 w-full rounded-xl" /></LoadingRegion>}>
        <Library />
      </Suspense>
    </PageContainer>
  );
}

async function Library() {
  const [challenges, dash] = await Promise.all([getDesignChallenges(), getDesignDashboard()]);
  const progress = new Map(dash?.challenges.map((c) => [c.slug, c]) ?? []);
  return (
    <div className="flex flex-col gap-10">
      {DESIGN_LEVELS.map((lvl) => (
        <section key={lvl} id={lvl} aria-labelledby={`${lvl}-heading`} className="scroll-mt-6">
          <h2 id={`${lvl}-heading`} className="mb-3 text-[15px] font-medium text-fg">{LEVEL_LABEL[lvl]}</h2>
          <ul className="grid gap-3 md:grid-cols-2">
            {challenges.filter((c) => c.level === lvl).map((c) => {
              const p = progress.get(c.slug);
              return (
                <li key={c.slug}>
                  <Link href={`/design/challenges/${c.slug}`} className="flex h-full flex-col gap-2 rounded-xl border border-line bg-surface p-4 hover:bg-surface-hover">
                    <span className="flex items-start justify-between gap-3">
                      <span className="text-sm font-medium text-fg">{c.title}</span>
                      <span className="shrink-0 text-xs text-fg-subtle tabular-nums">
                        {p?.best_score != null ? `best ${Math.round(p.best_score * 100)}%` : p?.attempted ? "in progress" : `v${c.version}`}
                      </span>
                    </span>
                    <span className="line-clamp-2 text-xs leading-relaxed text-fg-muted">{c.summary}</span>
                    <span className="mt-auto flex flex-wrap gap-1 pt-1">
                      {c.competencies.map((k) => (
                        <span key={k} className="rounded border border-line-subtle px-1.5 py-0.5 text-[11px] text-fg-subtle">{COMPETENCY_LABEL[k] ?? k}</span>
                      ))}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
