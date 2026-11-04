import { ChevronLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { EVIDENCE_KIND_LABEL, KIND_LABEL, LEVEL_LABEL, STATUS_LABEL, TRACK_LABEL, date, levelLabel, pct } from "@/components/career/format";
import { PrintButton } from "@/components/career/print-button";
import { BenchmarkList, CompetencyMatrix, ReadinessHeadline } from "@/components/career/readiness";
import { ButtonLink } from "@/components/ui/button";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { compareCareerReports, getCareerReport, getCareerReports } from "@/lib/api";

export const metadata: Metadata = { title: "Readiness report" };

export default function ReportPage({ params, searchParams }: PageProps<"/career/reports/[id]">) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <Link href="/career" className="no-print mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />FORGE Career
      </Link>
      <Suspense fallback={<LoadingRegion label="Loading report"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Report params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="border-b border-line-subtle pb-1 text-sm font-medium text-fg">{title}</h2>
      {children}
    </section>
  );
}

async function Report({ params, searchParams }: Pick<PageProps<"/career/reports/[id]">, "params" | "searchParams">) {
  const [{ id }, sp] = await Promise.all([params, searchParams]);
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const rep = await getCareerReport(id);
  if (!rep) notFound();
  const withId = typeof sp.with === "string" ? sp.with : null;
  const [cmp, all] = await Promise.all([withId ? compareCareerReports(id, withId) : null, getCareerReports()]);
  const s = rep.snapshot;
  const r = s.readiness;
  const attemptIds = new Set(s.attempt_evidence_ids ?? []);
  const sections = s.sections ?? [];
  const byKind = (k: string) => sections.filter((x) => x.kind === k);
  const sectionLine = (k: string) => byKind(k).map((x) => `${x.title}: ${x.status === "completed" ? pct((x.result as { score?: number })?.score ?? null) : x.status}`).join(" · ") || "Not part of this assessment.";
  return (
    <article className="print-report flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-fg-subtle">{rep.kind === "assessment" ? "Assessment report" : "Readiness snapshot"} · {date(rep.created_at)} · framework {r.framework_version} (v{rep.framework_version_number})</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{rep.title}</h1>
          <p className="mt-1 text-sm text-fg-muted">{TRACK_LABEL[r.track]} · target {LEVEL_LABEL[r.target_level]}</p>
        </div>
        <div className="no-print flex gap-2">
          <PrintButton />
          <ButtonLink href="/career/roadmap" size="sm">Open roadmap</ButtonLink>
        </div>
      </header>

      <Section title="Assessment summary">
        <ReadinessHeadline r={r} />
        {s.attempt ? (
          <dl className="grid gap-2 text-[13px] sm:grid-cols-2">
            <div><dt className="text-xs text-fg-subtle">Assessment</dt><dd className="text-fg">{s.attempt.title} (template v{s.attempt.template_version}, {s.attempt.purpose})</dd></div>
            <div><dt className="text-xs text-fg-subtle">Dates</dt><dd className="text-fg">Started {date(s.attempt.started_at)}, finalized {date(s.attempt.finalized_at)}{s.attempt.expired ? " (time limit reached)" : ""}</dd></div>
            <div><dt className="text-xs text-fg-subtle">Passing criteria</dt><dd className="text-fg">{s.attempt.passing_criteria}</dd></div>
            <div><dt className="text-xs text-fg-subtle">Outcome</dt><dd className="text-fg">{s.passed ? "Passed" : "Not passed"} · weighted section summary {pct(s.section_summary ?? null)} (summary only; readiness uses the gates)</dd></div>
          </dl>
        ) : null}
        {s.critical_failures?.length ? (
          <ul className="list-disc pl-4 text-[13px] text-fg">{s.critical_failures.map((c) => <li key={c}>{c}</li>)}</ul>
        ) : null}
      </Section>

      {sections.length ? (
        <Section title="Sections">
          <ul className="divide-y divide-line-subtle rounded-lg border border-line text-[13px]">
            {sections.map((x) => {
              const res = (x.result ?? {}) as { score?: number | null; evidence?: string; reason?: string; note?: string };
              return (
                <li key={x.key} className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
                  <span><span className="text-fg">{x.title}</span> <span className="text-xs text-fg-subtle">({KIND_LABEL[x.kind]}, weight {x.weight})</span>
                    <span className="block text-xs text-fg-muted">{res.reason ?? res.note ?? res.evidence ?? ""}</span></span>
                  <span className="font-mono text-xs text-fg">{x.status === "completed" ? pct(res.score ?? null) : x.status}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}

      <Section title="Performance by area">
        <dl className="grid gap-2 text-[13px] sm:grid-cols-2">
          <div><dt className="text-xs text-fg-subtle">Coding performance</dt><dd className="text-fg">{sectionLine("coding")}</dd></div>
          <div><dt className="text-xs text-fg-subtle">Technical reasoning (interviews, judgment)</dt><dd className="text-fg">{[sectionLine("interview"), sectionLine("judgment")].join(" · ")}</dd></div>
          <div><dt className="text-xs text-fg-subtle">Architecture</dt><dd className="text-fg">{sectionLine("design")}</dd></div>
          <div><dt className="text-xs text-fg-subtle">Production readiness</dt><dd className="text-fg">{sectionLine("incident")}</dd></div>
        </dl>
      </Section>

      <Section title="Demonstrated competencies and gaps">
        <div className="grid gap-5 md:grid-cols-2">
          <BenchmarkList title="Mandatory gates" rows={r.target.gates} />
          <BenchmarkList title="Also expected" rows={r.target.required} />
          <BenchmarkList title="Critical weaknesses" rows={r.critical_gaps} empty="None found." />
          <BenchmarkList title="Missing evidence" rows={r.missing_evidence} empty="None." />
        </div>
      </Section>

      <Section title="Evidence coverage">
        <CompetencyMatrix dims={r.dimensions} highlight={new Set([...r.target.gates, ...r.target.required].map((g) => g.dimension))} />
        <ul className="flex flex-wrap gap-3 text-xs text-fg-muted">
          {Object.entries(r.evidence_summary.by_kind).filter(([, n]) => n).map(([k, n]) => <li key={k}>{EVIDENCE_KIND_LABEL[k] ?? k}: {n}</li>)}
          <li>Verified share: {pct(r.evidence_summary.verified_share)}</li>
          <li>From this assessment: {attemptIds.size}</li>
        </ul>
        <details className="text-[13px]">
          <summary className="cursor-pointer text-xs text-fg-subtle">Evaluated evidence ({s.evidence.length} items, with dates)</summary>
          <table className="mt-2 w-full text-xs">
            <thead><tr className="text-left text-fg-subtle"><th className="py-1 font-normal">Date</th><th className="font-normal">Evidence</th><th className="font-normal">Kind</th><th className="font-normal">Level</th><th className="text-right font-normal">Score</th></tr></thead>
            <tbody>
              {s.evidence.map((e) => (
                <tr key={e.id} className="border-t border-line-subtle align-top">
                  <td className="py-1 pr-2 whitespace-nowrap text-fg-muted">{date(e.observed_at)}</td>
                  <td className="pr-2 text-fg">{e.title}<span className="block text-fg-subtle">{e.dimensions.join(", ")}{e.context.startsWith("formal") ? " · formal" : " · practice"}</span></td>
                  <td className="pr-2 text-fg-muted">{EVIDENCE_KIND_LABEL[e.kind] ?? e.kind}</td>
                  <td className="pr-2 text-fg-muted">{e.difficulty}</td>
                  <td className="text-right font-mono text-fg">{pct(e.score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </Section>

      <Section title="Historical comparison">
        <form className="no-print flex flex-wrap items-center gap-2 text-xs" action={`/career/reports/${id}`}>
          <label htmlFor="with" className="text-fg-subtle">Compare with</label>
          <select id="with" name="with" defaultValue={withId ?? ""} className="rounded-md border border-line bg-canvas px-2 py-1 text-fg">
            <option value="">Choose an earlier report</option>
            {(all ?? []).filter((x) => x.id !== id).map((x) => <option key={x.id} value={x.id}>{date(x.created_at)} · {x.title}</option>)}
          </select>
          <button type="submit" className="rounded-md border border-line px-2 py-1 text-fg hover:bg-surface-hover">Compare</button>
        </form>
        {cmp ? (
          <div>
            {cmp.note ? <p className="mb-2 text-xs text-fg">{cmp.note}</p> : null}
            <ul className="grid gap-1 text-[13px] sm:grid-cols-2">
              {cmp.dimensions.filter((d) => d.change !== "same").map((d) => (
                <li key={d.dimension} className="flex justify-between gap-2"><span className="text-fg">{d.title}</span>
                  <span className="text-xs text-fg-muted">{d.change}: {levelLabel(d.before as never)} → {levelLabel(d.after as never)}</span></li>
              ))}
            </ul>
            {cmp.dimensions.every((d) => d.change === "same") ? <p className="text-xs text-fg-muted">No change in demonstrated levels.</p> : null}
          </div>
        ) : <p className="text-xs text-fg-subtle">Select an earlier report to see which competencies changed.</p>}
      </Section>

      <Section title="Learning recommendations and reassessment">
        <p className="text-[13px] text-fg-muted">Your roadmap turns every gap above into prioritised FORGE activities with completion criteria and a reassessment date.</p>
        <p className="text-[13px] text-fg">Readiness for target: {STATUS_LABEL[r.target.status]}.</p>
      </Section>

      <Section title="Evaluation limitations">
        <ul className="list-disc pl-4 text-[13px] text-fg-muted">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="text-xs text-fg-subtle">PDF: use your browser&apos;s Print and choose Save as PDF; FORGE does not bundle a separate PDF renderer.</p>
      </Section>
    </article>
  );
}
