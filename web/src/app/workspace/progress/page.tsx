import { ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { LevelBadge } from "@/components/workspace/badges";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getWorkspaceProgress } from "@/lib/workspace-api";
import { TASK_TYPE_LABEL } from "@/lib/workspace-types";

export const metadata: Metadata = { title: "Engineering competencies" };

const pct = (x: number | null) => (x === null ? "—" : `${Math.round(x * 100)}%`);

export default function ProgressPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow={<Link href="/workspace" className="hover:text-fg">FORGE Workspace</Link>}
        title="Engineering competencies"
        description="What your project work demonstrates. Verified figures come only from tests executed in the verified sandbox; AI review figures are subjective and shown separately."
        actions={<ButtonLink href="/career" variant="secondary">Career readiness</ButtonLink>}
      />
      <Suspense fallback={<LoadingRegion label="Loading progress"><Skeleton className="h-80 w-full rounded-xl" /></LoadingRegion>}>
        <Progress />
      </Suspense>
    </PageContainer>
  );
}

async function Progress() {
  const progress = await getWorkspaceProgress();
  return (
    <>
      {!progress || progress.totals.projects_started === 0 ? (
        <EmptyState icon={ShieldCheck} title="No project work yet" description="Open a project and submit an attempt. Results appear here once tests have run."
          action={<ButtonLink href="/workspace/projects" size="sm">Browse projects</ButtonLink>} />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Projects started", progress.totals.projects_started],
              ["Approved pull requests", progress.totals.projects_approved],
              ["Verified submissions", progress.totals.verified_submissions],
              ["Exercises reviewed", progress.totals.exercises_reviewed],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-line bg-surface px-4 py-3">
                <dt className="text-xs text-fg-subtle">{label}</dt>
                <dd className="mt-1 text-xl font-semibold text-fg tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>

          <section aria-labelledby="comp-h">
            <SectionHeader id="comp-h" title="By competency" description="Latest verified submission per project. Tests are tagged with the competency they exercise." />
            <div className="overflow-x-auto rounded-xl border border-line bg-surface">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="border-b border-line-subtle text-left text-xs text-fg-subtle">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-medium">Competency</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Verified tests passed</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">AI review (advisory)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-subtle">
                  {progress.competencies.map((c) => (
                    <tr key={c.key}>
                      <th scope="row" className="px-4 py-2.5 text-left font-normal text-fg">{c.label}</th>
                      <td className="px-4 py-2.5 text-fg-muted tabular-nums">
                        {c.verified.total ? `${c.verified.passed} / ${c.verified.total} (${pct(c.verified.rate)})` : <span className="text-fg-subtle">No verified evidence</span>}
                      </td>
                      <td className="px-4 py-2.5 text-fg-muted tabular-nums">
                        {c.ai_review.count ? `${pct(c.ai_review.mean)} across ${c.ai_review.count}` : <span className="text-fg-subtle">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="rec-h">
            <SectionHeader id="rec-h" title="Recommended follow-ups" />
            {progress.recommendations.length ? (
              <ul className="grid gap-3 sm:grid-cols-2">
                {progress.recommendations.map((r, i) => (
                  <li key={i} className="rounded-xl border border-line bg-surface p-4">
                    <p className="text-xs text-fg-subtle">{r.label}</p>
                    <p className="mt-1 text-sm text-fg-muted">{r.reason}</p>
                    {r.project ? <ButtonLink href={`/workspace/projects/${r.project}`} size="sm" variant="secondary" className="mt-3">Open project</ButtonLink> : null}
                    {r.skills?.length ? <ButtonLink href="/learn" size="sm" variant="ghost" className="mt-3">Learning path</ButtonLink> : null}
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-fg-muted">Nothing specific: keep going with the next project.</p>}
          </section>

          <section aria-labelledby="hist-h">
            <SectionHeader id="hist-h" title="Project history" />
            <div className="overflow-x-auto rounded-xl border border-line bg-surface">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b border-line-subtle text-left text-xs text-fg-subtle">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-medium">Project</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Level</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Attempts</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Best hidden</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">PR revisions</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-subtle">
                  {progress.projects.map((p) => (
                    <tr key={p.slug}>
                      <th scope="row" className="px-4 py-2.5 text-left font-normal">
                        {p.workspace_id ? <Link href={`/workspace/w/${p.workspace_id}`} className="text-fg hover:underline">{p.title}</Link>
                          : <Link href={`/workspace/projects/${p.slug}`} className="text-fg-muted hover:text-fg">{p.title}</Link>}
                        <span className="block text-xs text-fg-subtle">{TASK_TYPE_LABEL[p.task_type] ?? p.task_type}</span>
                      </th>
                      <td className="px-4 py-2.5"><LevelBadge level={p.level} /></td>
                      <td className="px-4 py-2.5 text-fg-muted tabular-nums">{p.submissions} ({p.verified_submissions} verified)</td>
                      <td className="px-4 py-2.5 text-fg-muted tabular-nums">{p.best_hidden ? `${p.best_hidden[0]} / ${p.best_hidden[1]}` : "—"}</td>
                      <td className="px-4 py-2.5 text-fg-muted tabular-nums">{p.revisions || "—"}</td>
                      <td className="px-4 py-2.5 text-fg-muted">{p.approved ? "Approved" : p.status === "not_started" ? "Not started" : "In progress"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <p className="text-xs leading-relaxed text-fg-subtle">{progress.note}</p>
        </>
      )}
    </>
  );
}
