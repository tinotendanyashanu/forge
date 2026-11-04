import { ChevronLeft, Play, Siren } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { startIncident } from "@/app/actions";
import { COMPONENTS } from "@/components/design/components";
import { COMPETENCY_LABEL, LEVEL_LABEL, MODE_INFO } from "@/components/ops/format";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getOpsScenario } from "@/lib/api";
import { OPS_MODES } from "@/lib/types";

export default function IncidentBriefPage({ params, searchParams }: PageProps<"/ops/incidents/[slug]">) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <Link href="/ops" className="mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        FORGE OPS
      </Link>
      <Suspense fallback={<LoadingRegion label="Loading incident"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Brief params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Brief({ params, searchParams }: Pick<PageProps<"/ops/incidents/[slug]">, "params" | "searchParams">) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const s = await getOpsScenario(slug);
  if (!s) notFound();
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
      <article className="flex flex-col gap-5">
        <header>
          <p className="text-xs text-fg-subtle">{LEVEL_LABEL[s.level]} · scenario v{s.version}</p>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-fg">
            <Siren className="size-5 shrink-0" aria-hidden="true" />{s.title}
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">{s.summary}</p>
        </header>
        <section>
          <h2 className="mb-1 text-xs font-medium text-fg-subtle">Business context</h2>
          <p className="text-[13px] leading-relaxed text-fg">{s.business_context}</p>
        </section>
        <section>
          <h2 className="mb-1 text-xs font-medium text-fg-subtle">What you&apos;ll see first</h2>
          <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{s.initial_symptoms.map((x) => <li key={x}>{x}</li>)}</ul>
        </section>
        <section>
          <h2 className="mb-1 text-xs font-medium text-fg-subtle">Customer impact</h2>
          <p className="text-[13px] text-fg">{s.customer_impact}</p>
        </section>
        <section>
          <h2 className="mb-2 text-xs font-medium text-fg-subtle">Services</h2>
          <ul className="grid gap-1.5 sm:grid-cols-2">
            {s.services.map((svc) => {
              const Icon = COMPONENTS[svc.kind]?.icon;
              return (
                <li key={svc.id} className="flex items-start gap-2 rounded-lg border border-line px-3 py-2 text-[13px]">
                  {Icon ? <Icon className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" /> : null}
                  <span>
                    <span className="text-fg">{svc.name}</span>
                    {svc.depends_on.length ? <span className="block text-[11px] text-fg-subtle">depends on {svc.depends_on.join(", ")}</span> : null}
                    {svc.description ? <span className="block text-[11px] text-fg-subtle">{svc.description}</span> : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
        <section>
          <h2 className="mb-1 text-xs font-medium text-fg-subtle">You&apos;ll practise</h2>
          <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{s.learning_outcomes.map((x) => <li key={x}>{x}</li>)}</ul>
        </section>
      </article>
      <aside className="flex flex-col gap-4">
        <Card className="p-5">
          <h2 className="mb-1 text-sm font-medium text-fg">Take the incident</h2>
          <p className="mb-3 text-xs leading-relaxed text-fg-muted">
            A simulation: nothing touches real systems. Everything you do is recorded and replayable. An open attempt resumes where you left it.
          </p>
          <form action={startIncident} className="flex flex-col gap-3">
            <input type="hidden" name="scenario" value={s.slug} />
            <fieldset>
              <legend className="mb-1.5 text-xs text-fg-subtle">AI commander mode (changeable later)</legend>
              <div className="flex flex-col gap-1">
                {OPS_MODES.filter((m) => m !== "postmortem").map((m, i) => (
                  <label key={m} className="flex cursor-pointer gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-surface-hover">
                    <input type="radio" name="mode" value={m} defaultChecked={i === 2} className="mt-0.5 accent-white" />
                    <span><span className="block text-fg">{MODE_INFO[m].label}</span><span className="text-fg-subtle">{MODE_INFO[m].description}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
            <Button type="submit" size="sm"><Play aria-hidden="true" />Open incident</Button>
          </form>
          {sp.error ? <p role="alert" className="mt-2 text-xs text-fg">Couldn&apos;t start the incident. Check that the API is running.</p> : null}
        </Card>
        <Card className="p-5">
          <h2 className="mb-2 text-sm font-medium text-fg">Competencies</h2>
          <ul className="flex flex-wrap gap-1">
            {s.competencies.map((c) => <li key={c} className="rounded border border-line-subtle px-1.5 py-0.5 text-[11px] text-fg-muted">{COMPETENCY_LABEL[c] ?? c}</li>)}
          </ul>
          <p className="mt-3 text-xs text-fg-subtle">Skills: {s.skills.join(", ")}</p>
        </Card>
      </aside>
    </div>
  );
}
