import { Clock, EyeOff, FlaskConical } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { LevelBadge, TaskTypeBadge } from "@/components/workspace/badges";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getEngProjects, getWorkspaceProgress } from "@/lib/workspace-api";
import { LEVEL_LABEL, type EngLevel } from "@/lib/workspace-types";

export const metadata: Metadata = { title: "Project library" };

const LEVELS: EngLevel[] = ["beginner", "junior", "mid", "senior"];

export default function ProjectLibrary() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow={<Link href="/workspace" className="hover:text-fg">FORGE Workspace</Link>}
        title="Project library"
        description="Each project is a versioned codebase with a ticket, acceptance criteria, public tests you can run and hidden tests that decide whether you're done."
      />
      <Suspense fallback={<LoadingRegion label="Loading projects" className="grid gap-4 md:grid-cols-2"><Skeleton className="h-56 rounded-xl" /><Skeleton className="h-56 rounded-xl" /></LoadingRegion>}>
        <Library />
      </Suspense>
      <p className="text-xs text-fg-subtle">More projects are planned for every level. The library starts small on purpose: each project is verified end to end in the sandbox.</p>
    </PageContainer>
  );
}

async function Library() {
  const [projects, progress] = await Promise.all([getEngProjects(), getWorkspaceProgress().catch(() => null)]);
  const state = new Map(progress?.projects.map((p) => [p.slug, p]) ?? []);
  return (
    <>
      {LEVELS.map((level) => {
        const items = projects.filter((p) => p.level === level);
        if (!items.length) return null;
        return (
          <section key={level} aria-labelledby={`lvl-${level}`}>
            <h2 id={`lvl-${level}`} className="mb-4 text-[15px] font-medium text-fg">{LEVEL_LABEL[level]}</h2>
            <ul className="grid gap-4 md:grid-cols-2">
              {items.map((p) => {
                const s = state.get(p.slug);
                return (
                  <li key={p.slug}>
                    <Link href={`/workspace/projects/${p.slug}`} className="flex h-full flex-col gap-3 rounded-xl border border-line bg-surface p-5 transition-colors hover:border-neutral-600 hover:bg-surface-hover">
                      <div className="flex flex-wrap items-center gap-2">
                        <LevelBadge level={p.level} />
                        <TaskTypeBadge type={p.task_type} />
                        {s?.approved ? <span className="ml-auto text-xs text-fg">Completed</span> : s?.workspace_id ? <span className="ml-auto text-xs text-fg-muted">In progress</span> : null}
                      </div>
                      <h3 className="text-[15px] font-medium text-fg">{p.title}</h3>
                      <p className="flex-1 text-sm leading-relaxed text-fg-muted">{p.summary}</p>
                      <p className="font-mono text-[11.5px] text-fg-subtle">{p.stack.join(" · ")}</p>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-subtle">
                        <span className="inline-flex items-center gap-1"><Clock className="size-3.5" aria-hidden="true" />~{p.estimated_minutes} min</span>
                        <span className="inline-flex items-center gap-1"><FlaskConical className="size-3.5" aria-hidden="true" />{p.public_tests} public</span>
                        <span className="inline-flex items-center gap-1"><EyeOff className="size-3.5" aria-hidden="true" />{p.hidden_tests} hidden</span>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </>
  );
}
