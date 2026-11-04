import { ChevronLeft, ClipboardList } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { jobAssessment } from "@/app/actions";
import { LEVEL_LABEL, levelLabel } from "@/components/career/format";
import { Button } from "@/components/ui/button";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { getCareerJob } from "@/lib/api";

export const metadata: Metadata = { title: "Job match" };

const STATUS = { match: "Demonstrated", gap: "Gap", untested: "Untested" } as const;

export default function JobPage({ params, searchParams }: PageProps<"/career/jobs/[id]">) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <Link href="/career/jobs" className="mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />Job matcher
      </Link>
      <Suspense fallback={<LoadingRegion label="Loading"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Job params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Job({ params, searchParams }: Pick<PageProps<"/career/jobs/[id]">, "params" | "searchParams">) {
  const [{ id }, sp] = await Promise.all([params, searchParams]);
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const j = await getCareerJob(id);
  if (!j) notFound();
  const kw = j.extraction.keyword;
  const m = j.mapping;
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-fg-subtle">Expected seniority: {LEVEL_LABEL[m.level]} ({kw.seniority_evidence}) · extraction: {j.method}{j.ai_error ? ` (AI unavailable: ${j.ai_error})` : j.model ? ` · ${j.provider}/${j.model}` : ""}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{j.title}</h1>
          <p className="mt-1 text-sm text-fg-muted">{m.summary.match ?? 0} demonstrated · {m.summary.gap ?? 0} gaps · {m.summary.untested ?? 0} untested</p>
        </div>
        <form action={jobAssessment}>
          <input type="hidden" name="job" value={j.id} />
          <Button type="submit"><ClipboardList aria-hidden="true" />Generate preparation assessment</Button>
        </form>
      </header>
      {sp.error ? <p role="alert" className="text-sm text-fg">Couldn&apos;t generate an assessment for this role.</p> : null}
      {kw.injection_suspected ? <p className="rounded-lg border border-line bg-surface-elevated px-3 py-2 text-xs text-fg-muted">The description contained instruction-like text. It was treated as data and ignored.</p> : null}
      <section>
        <h2 className="mb-2 text-xs font-medium text-fg-subtle">Requirements mapped to the framework</h2>
        <ul className="divide-y divide-line-subtle rounded-xl border border-line bg-surface">
          {m.rows.map((r) => (
            <li key={r.dimension} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3 text-[13px]">
              <span className="min-w-0 flex-1">
                <span className="text-fg">{r.title}</span>
                <span className="block text-xs text-fg-muted">From the description: {r.requirements.join("; ")}</span>
                {r.status !== "match" ? <span className="block text-xs text-fg-subtle">needs {LEVEL_LABEL[r.needed]} · shown {levelLabel(r.demonstrated)}{r.reasons.length ? ` · ${r.reasons.join("; ")}` : ""}</span> : null}
                {r.ai_only ? <span className="block text-xs text-fg-subtle">Evidence so far is AI-judged only.</span> : null}
              </span>
              <span className={cn("rounded-full border px-2 py-0.5 text-[11px]", r.status === "match" ? "border-fg text-fg" : "border-line text-fg-muted")}>{STATUS[r.status]}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        {([["Testing expectations", kw.testing], ["Deployment responsibilities", kw.deployment], ["Collaboration", kw.collaboration], ["Architecture", kw.architecture]] as const).map(([t, xs]) => (
          <div key={t}>
            <h3 className="mb-1 text-xs font-medium text-fg-subtle">{t}</h3>
            {xs.length ? <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{xs.map((x) => <li key={x}>{x}</li>)}</ul> : <p className="text-xs text-fg-subtle">Not mentioned.</p>}
          </div>
        ))}
      </section>
      <p className="text-xs text-fg-subtle">{m.note} {kw.years_note}</p>
    </div>
  );
}
