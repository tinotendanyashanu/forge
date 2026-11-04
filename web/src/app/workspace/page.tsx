import { ArrowRight, FolderGit2, GitPullRequest, LibraryBig } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { LevelBadge, PrStatusBadge } from "@/components/workspace/badges";
import { WorkspaceStatusBanner } from "@/components/workspace/status-banner";
import { formatDistanceShort } from "@/components/workspace/time";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getMyWorkspaces, getPulls, getWorkspaceProgress, getWorkspaceStatus } from "@/lib/workspace-api";

export const metadata: Metadata = { title: "Workspace" };

export default function WorkspaceHome() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="FORGE Workspace"
        title="Work on real codebases, not puzzles."
        description="Pick up a ticket in an unfamiliar multi-file project, fix it, prove it with tests in an isolated sandbox, and take it through a pull request review."
        actions={
          <>
            <ButtonLink href="/workspace/progress" variant="secondary">Competencies</ButtonLink>
            <ButtonLink href="/workspace/projects"><LibraryBig aria-hidden="true" />Project library</ButtonLink>
          </>
        }
      />
      <Suspense fallback={<Skeleton className="h-12 w-full rounded-lg" />}>
        <Status />
      </Suspense>
      <section aria-labelledby="active-heading">
        <SectionHeader id="active-heading" title="Your workspaces" description="Your work is saved on the server. Pick up where you left off." />
        <Suspense fallback={<LoadingRegion label="Loading workspaces"><Skeleton className="h-40 w-full rounded-xl" /></LoadingRegion>}>
          <Workspaces />
        </Suspense>
      </section>
      <section aria-labelledby="pr-heading">
        <SectionHeader id="pr-heading" title="Pull requests" />
        <Suspense fallback={<Skeleton className="h-24 w-full rounded-xl" />}>
          <Pulls />
        </Suspense>
      </section>
      <section aria-labelledby="next-heading">
        <SectionHeader id="next-heading" title="Recommended next" action={<ButtonLink href="/workspace/progress" variant="ghost" size="sm">All progress<ArrowRight aria-hidden="true" /></ButtonLink>} />
        <Suspense fallback={<Skeleton className="h-24 w-full rounded-xl" />}>
          <Next />
        </Suspense>
      </section>
    </PageContainer>
  );
}

async function Status() {
  return <WorkspaceStatusBanner status={await getWorkspaceStatus().catch(() => null)} />;
}

async function Workspaces() {
  const list = await getMyWorkspaces();
  if (!list?.length) {
    return (
      <EmptyState
        icon={FolderGit2}
        title="No workspaces yet"
        description="Open a project from the library. You get your own isolated copy of its codebase."
        action={<ButtonLink href="/workspace/projects" size="sm">Browse projects</ButtonLink>}
      />
    );
  }
  return (
    <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {list.map((w) => (
        <li key={w.id}>
          <Link href={`/workspace/w/${w.id}`} className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-surface-hover">
            <FolderGit2 className="size-4 shrink-0 text-fg-muted" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-fg">{w.project_title}</span>
              <span className="text-xs text-fg-subtle">v{w.version} · edited {formatDistanceShort(w.updated_at)}</span>
            </span>
            <LevelBadge level={w.level} />
            <span className="text-xs text-fg-muted">{w.status === "completed" ? "Completed" : "In progress"}</span>
            <ArrowRight className="size-4 text-fg-subtle" aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

async function Pulls() {
  const list = await getPulls();
  if (!list?.length) {
    return <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-fg-muted">Open a pull request from a workspace when your change is ready for review.</p>;
  }
  return (
    <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
      {list.map((p) => (
        <li key={p.id}>
          <Link href={`/workspace/pulls/${p.id}`} className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-surface-hover">
            <GitPullRequest className="size-4 shrink-0 text-fg-muted" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-fg">{p.title}</span>
              <span className="text-xs text-fg-subtle">{p.project_title} · {p.revisions} revision{p.revisions === 1 ? "" : "s"} · updated {formatDistanceShort(p.updated_at)}</span>
            </span>
            <PrStatusBadge status={p.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

async function Next() {
  const progress = await getWorkspaceProgress();
  const recs = progress?.recommendations ?? [];
  if (!recs.length) {
    return <p className="text-sm text-fg-muted">Start with the beginner project in the <Link href="/workspace/projects" className="underline underline-offset-4">library</Link>.</p>;
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {recs.slice(0, 4).map((r, i) => (
        <li key={i} className="rounded-xl border border-line bg-surface p-4">
          <p className="text-xs text-fg-subtle">{r.label}</p>
          <p className="mt-1 text-sm text-fg-muted">{r.reason}</p>
          {r.project ? <ButtonLink href={`/workspace/projects/${r.project}`} size="sm" variant="secondary" className="mt-3">Open project</ButtonLink> : null}
        </li>
      ))}
    </ul>
  );
}
