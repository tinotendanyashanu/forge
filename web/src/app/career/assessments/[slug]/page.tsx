import { ChevronLeft, Clock, Play, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { startCareerAssessment } from "@/app/actions";
import { KIND_LABEL, LEVEL_LABEL, TRACK_LABEL } from "@/components/career/format";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCareerTemplate } from "@/lib/api";

export default function AssessmentIntro({ params, searchParams }: PageProps<"/career/assessments/[slug]">) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <Link href="/career/assessments" className="mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />All assessments
      </Link>
      <Suspense fallback={<LoadingRegion label="Loading assessment"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Intro params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Intro({ params, searchParams }: Pick<PageProps<"/career/assessments/[slug]">, "params" | "searchParams">) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const t = await getCareerTemplate(slug);
  if (!t) notFound();
  const total = t.sections.reduce((n, s) => n + s.minutes, 0);
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
      <article className="flex flex-col gap-6">
        <header>
          <p className="text-xs text-fg-subtle">{TRACK_LABEL[t.track]} · {LEVEL_LABEL[t.level]} · version {t.version} · {t.purpose}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{t.title}</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">{t.description}</p>
        </header>
        <section><h2 className="mb-1 text-xs font-medium text-fg-subtle">Objectives</h2>
          <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{t.objectives.map((o) => <li key={o}>{o}</li>)}</ul></section>
        <section>
          <h2 className="mb-2 text-xs font-medium text-fg-subtle">Sections</h2>
          <ol className="flex flex-col gap-2">
            {t.sections.map((s, i) => (
              <li key={s.key} className="rounded-lg border border-line p-3 text-[13px]">
                <p className="flex flex-wrap items-center justify-between gap-2 text-fg">
                  <span>{i + 1}. {s.title} <span className="text-xs text-fg-subtle">({KIND_LABEL[s.kind]})</span></span>
                  <span className="text-xs text-fg-subtle">~{s.minutes} min · weight {s.weight}{s.critical ? " · critical" : ""}</span>
                </p>
                <p className="mt-1 text-xs text-fg-muted">{s.objectives.map((o) => o.replace(/[.\s]*$/, ".")).join(" ")} Competencies: {s.dimensions.join(", ")}.</p>
              </li>
            ))}
          </ol>
        </section>
        <section><h2 className="mb-1 text-xs font-medium text-fg-subtle">Passing criteria</h2><p className="text-[13px] text-fg">{t.passing_criteria}</p></section>
        {t.critical_failures.length ? (
          <section><h2 className="mb-1 text-xs font-medium text-fg-subtle">Critical failure conditions</h2>
            <ul className="list-disc pl-4 text-[13px] text-fg marker:text-fg-subtle">{t.critical_failures.map((c) => <li key={c}>{c}</li>)}</ul></section>
        ) : null}
        <section><h2 className="mb-1 text-xs font-medium text-fg-subtle">Evidence requirements</h2><p className="text-[13px] text-fg">{t.evidence_requirements}</p></section>
      </article>
      <aside className="flex flex-col gap-4">
        <Card className="flex flex-col gap-3 p-5">
          <p className="flex items-center gap-2 text-sm text-fg"><Clock className="size-4" aria-hidden="true" />
            {t.time_limit_minutes ? `${t.time_limit_minutes} minutes, server-timed` : "Untimed"}</p>
          <p className="text-xs leading-relaxed text-fg-muted">
            {t.time_limit_minutes ? `The clock starts when you press Start on the next page and runs on the server; refreshing never resets it. Section estimates total ${total} minutes. ` : ""}
            Each section opens the real FORGE lab in a new tab; come back and mark it complete. Only work done inside the section window counts.
          </p>
          <form action={startCareerAssessment}>
            <input type="hidden" name="template" value={t.slug} />
            <Button type="submit" size="sm"><Play aria-hidden="true" />Prepare attempt</Button>
          </form>
          {sp.error ? <p role="alert" className="text-xs text-fg">Couldn&apos;t create the attempt. Check that the API is running.</p> : null}
        </Card>
        <Card className="p-5 text-xs leading-relaxed text-fg-muted">
          <p className="mb-1 flex items-center gap-1.5 text-fg"><ShieldAlert className="size-3.5" aria-hidden="true" />Informational, not certification</p>
          Results are not independently proctored. AI evaluations are advisory; verified coding tests and simulation outcomes carry more weight. Executable coding requires the verified sandbox; without it the coding section is marked unavailable rather than run unsafely.
        </Card>
      </aside>
    </div>
  );
}
