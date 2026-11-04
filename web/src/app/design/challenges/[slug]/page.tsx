import { ArrowRight, ChevronLeft, Flame, Network } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { createDesignProject } from "@/app/actions";
import { BriefPanel } from "@/components/design/brief-panel";
import { COMPETENCY_LABEL, LEVEL_LABEL } from "@/components/design/components";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getDesignChallenge } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function DesignChallengePage({ params, searchParams }: PageProps<"/design/challenges/[slug]">) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <Link href="/design/challenges" className="mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        All challenges
      </Link>
      <Suspense fallback={<LoadingRegion label="Loading challenge"><Skeleton className="h-[480px] rounded-xl" /></LoadingRegion>}>
        <Challenge params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Challenge({ params, searchParams }: Pick<PageProps<"/design/challenges/[slug]">, "params" | "searchParams">) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const c = await getDesignChallenge(slug);
  if (!c) notFound();
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
      <article>
        <p className="text-xs text-fg-subtle">{LEVEL_LABEL[c.level]} · version {c.version}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{c.title}</h1>
        <div className="-mx-4 mt-2">
          <BriefPanel challenge={c} compact />
        </div>
      </article>
      <aside className="flex flex-col gap-4">
        <Card className="flex flex-col gap-3 p-5">
          <h2 className="text-sm font-medium text-fg">Start a design</h2>
          <p className="text-xs leading-relaxed text-fg-muted">
            A new project opens a canvas with this brief. It saves automatically and keeps every version.
          </p>
          <form action={createDesignProject}>
            <input type="hidden" name="challenge_slug" value={c.slug} />
            <Button type="submit" size="sm"><Network aria-hidden="true" />New design</Button>
          </form>
          {sp.error ? <p role="alert" className="text-xs text-fg">Couldn&apos;t create the project. Check that the API is running.</p> : null}
        </Card>
        {c.projects?.length ? (
          <Card className="p-5">
            <h2 className="mb-2 text-sm font-medium text-fg">Your designs</h2>
            <ul className="flex flex-col gap-1">
              {c.projects.map((p) => (
                <li key={p.id}>
                  <Link href={`/design/projects/${p.id}`} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-surface-hover">
                    <span className="truncate text-fg">{p.title}</span>
                    <span className="flex shrink-0 items-center gap-1 text-fg-subtle">{formatDateTime(p.updated_at)}<ArrowRight className="size-3" aria-hidden="true" /></span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        <Card className="p-5">
          <h2 className="mb-2 text-sm font-medium text-fg">Competencies</h2>
          <ul className="flex flex-wrap gap-1">
            {c.competencies.map((k) => (
              <li key={k} className="rounded border border-line-subtle px-1.5 py-0.5 text-[11px] text-fg-muted">{COMPETENCY_LABEL[k] ?? k}</li>
            ))}
          </ul>
          {c.prerequisites.length ? (
            <p className="mt-3 text-xs text-fg-subtle">Prerequisite skills: {c.prerequisites.join(", ")}</p>
          ) : null}
        </Card>
        <Card className="p-5">
          <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-fg"><Flame className="size-4" aria-hidden="true" />Failure drills</h2>
          <ul className="flex flex-col gap-1 text-xs text-fg-muted">
            {c.failure_scenarios.map((s) => <li key={s.slug}>{s.title}</li>)}
          </ul>
        </Card>
      </aside>
    </div>
  );
}
