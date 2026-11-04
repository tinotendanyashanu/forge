import { ChevronLeft, Clock, Cpu, EyeOff, FileCode, FolderGit2 } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { openWorkspace } from "@/app/workspace/actions";
import { LevelBadge, TaskTypeBadge } from "@/components/workspace/badges";
import { Markdown } from "@/components/workspace/markdown";
import { Button } from "@/components/ui/button";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getEngProject, getMyWorkspaces } from "@/lib/workspace-api";

export async function generateMetadata({ params }: PageProps<"/workspace/projects/[slug]">): Promise<Metadata> {
  const p = await getEngProject((await params).slug).catch(() => null);
  return { title: p?.title ?? "Project" };
}

export default function ProjectPage(props: PageProps<"/workspace/projects/[slug]">) {
  return (
    <Suspense fallback={<LoadingRegion label="Loading project" className="mx-auto w-full max-w-6xl px-4 pt-8 sm:px-6 lg:px-10"><Skeleton className="h-[480px] rounded-xl" /></LoadingRegion>}>
      <Project {...props} />
    </Suspense>
  );
}

async function Project({ params, searchParams }: PageProps<"/workspace/projects/[slug]">) {
  const { slug } = await params;
  const { error } = (await searchParams) as { error?: string };
  const [p, mine] = await Promise.all([getEngProject(slug), getMyWorkspaces().catch(() => null)]);
  if (!p) notFound();
  const existing = mine?.find((w) => w.project_slug === slug);

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pt-8 pb-16 sm:px-6 lg:px-10">
      <Link href="/workspace/projects" className="mb-5 inline-flex items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />Project library
      </Link>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <article className="flex flex-col gap-8">
          <header>
            <div className="flex flex-wrap items-center gap-2">
              <LevelBadge level={p.level} />
              <TaskTypeBadge type={p.task_type} />
              <span className="text-xs text-fg-subtle">{p.skill.title} · version {p.version}</span>
            </div>
            <h1 className="mt-3 text-[28px] font-semibold tracking-tight text-fg">{p.title}</h1>
            <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-fg-muted">{p.summary}</p>
          </header>
          <section aria-labelledby="ticket-h" className="rounded-xl border border-line bg-surface p-5">
            <p className="font-mono text-xs text-fg-subtle">{p.ticket.key} · {p.ticket.type} · {p.ticket.priority} · from {p.ticket.reporter}</p>
            <h2 id="ticket-h" className="mt-1 text-[17px] font-medium text-fg">{p.ticket.title}</h2>
            <div className="mt-3"><Markdown text={p.ticket.body} /></div>
            <h3 className="mt-5 mb-2 text-[13px] font-medium text-fg">Acceptance criteria</h3>
            <ol className="ml-5 list-decimal space-y-1.5 text-sm leading-relaxed text-fg-muted">
              {p.ticket.acceptance_criteria.map((c) => <li key={c}><Markdown text={c} className="inline" /></li>)}
            </ol>
          </section>
          <section aria-labelledby="bg-h"><h2 id="bg-h" className="mb-2 text-[15px] font-medium text-fg">Background</h2><Markdown text={p.description} /></section>
          <section aria-labelledby="arch-h"><h2 id="arch-h" className="mb-2 text-[15px] font-medium text-fg">Architecture</h2><Markdown text={p.architecture} /></section>
          <section aria-labelledby="setup-h"><h2 id="setup-h" className="mb-2 text-[15px] font-medium text-fg">Setup</h2><Markdown text={p.setup} /></section>
          <section aria-labelledby="tests-h">
            <h2 id="tests-h" className="mb-3 text-[15px] font-medium text-fg">Tests</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-line p-4">
                <p className="mb-2 text-[13px] text-fg">Public ({p.public_tests})</p>
                <ul className="space-y-1 text-[13px] text-fg-muted">{p.public_tests_detail.map((t) => <li key={t.name}>{t.name}</li>)}</ul>
              </div>
              <div className="rounded-xl border border-line p-4">
                <p className="mb-2 flex items-center gap-1.5 text-[13px] text-fg"><EyeOff className="size-3.5" aria-hidden="true" />Hidden ({p.hidden_tests})</p>
                <ul className="space-y-1 text-[13px] text-fg-muted">{p.hidden_test_names.map((n) => <li key={n}>{n}</li>)}</ul>
              </div>
            </div>
          </section>
          <section aria-labelledby="rubric-h">
            <h2 id="rubric-h" className="mb-2 text-[15px] font-medium text-fg">How reviews judge it <span className="text-xs font-normal text-fg-subtle">({p.rubric_version})</span></h2>
            <ol className="ml-5 list-decimal space-y-1 text-sm text-fg-muted">{p.rubric.map((r) => <li key={r}>{r}</li>)}</ol>
          </section>
          {p.exercises.length ? (
            <section aria-labelledby="ex-h">
              <h2 id="ex-h" className="mb-2 text-[15px] font-medium text-fg">Collaboration exercises</h2>
              <ul className="space-y-1 text-sm text-fg-muted">{p.exercises.map((e) => <li key={e.slug}>{e.title}</li>)}</ul>
            </section>
          ) : null}
        </article>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-8 lg:self-start">
          <form action={openWorkspace} className="rounded-xl border border-line bg-surface p-4">
            <input type="hidden" name="slug" value={p.slug} />
            <Button type="submit" className="w-full"><FolderGit2 aria-hidden="true" />{existing ? "Resume workspace" : "Open workspace"}</Button>
            <p className="mt-2 text-xs text-fg-subtle">{existing ? "Your saved work is waiting." : "You get your own isolated copy of the codebase."}</p>
            {error ? <p role="alert" className="mt-2 text-[13px] text-fg">{error}</p> : null}
          </form>
          <dl className="grid gap-3 rounded-xl border border-line p-4 text-[13px]">
            <div><dt className="text-fg-subtle">Stack</dt><dd className="text-fg">{p.stack.join(", ")}</dd></div>
            <div><dt className="text-fg-subtle">Competencies</dt><dd className="text-fg">{p.competencies.map((c) => c.replaceAll("_", " ")).join(", ")}</dd></div>
            <div className="flex gap-6">
              <div><dt className="text-fg-subtle">Time guide</dt><dd className="inline-flex items-center gap-1 text-fg"><Clock className="size-3.5" aria-hidden="true" />~{p.estimated_minutes} min</dd></div>
              <div><dt className="text-fg-subtle">Limits</dt><dd className="inline-flex items-center gap-1 text-fg"><Cpu className="size-3.5" aria-hidden="true" />{p.memory_limit_mb} MB</dd></div>
            </div>
            {p.prerequisites.length ? <div><dt className="text-fg-subtle">Prerequisites</dt><dd className="text-fg">{p.prerequisites.join(", ")}</dd></div> : null}
          </dl>
          <div className="rounded-xl border border-line p-4">
            <p className="mb-2 text-[13px] text-fg-subtle">Files ({p.starter_files.length})</p>
            <ul className="space-y-1 font-mono text-[12px] text-fg-muted">
              {p.starter_files.map((f) => <li key={f} className="flex items-center gap-1.5"><FileCode className="size-3" aria-hidden="true" />{f}</li>)}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
