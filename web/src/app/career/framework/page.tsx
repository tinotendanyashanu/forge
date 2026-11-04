import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { LEVEL_LABEL, TRACK_LABEL } from "@/components/career/format";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCareerFramework } from "@/lib/api";

export const metadata: Metadata = { title: "Competency framework" };

export default function FrameworkPage() {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader eyebrow={<Link href="/career" className="hover:text-fg">FORGE Career</Link>} title="Competency framework"
        description="The explicit, versioned criteria behind every readiness result: what each competency means at each level, where FORGE gathers evidence, and the gates for each role." />
      <Suspense fallback={<LoadingRegion label="Loading framework"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Framework />
      </Suspense>
    </PageContainer>
  );
}

async function Framework() {
  const fw = await getCareerFramework();
  const levels = ["junior", "mid", "senior"] as const;
  return (
    <div className="flex flex-col gap-8">
      <p className="text-sm text-fg-muted">Version {fw.version} (v{fw.version_number}). A level is demonstrated when fresh evidence at that difficulty reaches a reliability-weighted {Math.round(fw.rules.score_threshold * 100)}% with enough weight and independent sessions; verified evidence counts 1.0 and AI judgments 0.5. {fw.seniority_note}</p>
      <section>
        <h2 className="mb-3 text-sm font-medium text-fg">Role gates</h2>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[720px] text-xs">
            <thead><tr className="border-b border-line-subtle text-left text-fg-subtle"><th className="px-3 py-2 font-medium">Competency</th>
              {fw.tracks.flatMap((t) => levels.map((l) => <th key={t.key + l} className="px-2 py-2 text-center font-medium">{TRACK_LABEL[t.key].split(" ")[0]} {LEVEL_LABEL[l]}</th>))}</tr></thead>
            <tbody className="divide-y divide-line-subtle">
              {fw.dimensions.map((d) => (
                <tr key={d.key}><th scope="row" className="px-3 py-1.5 text-left font-normal text-fg">{d.title}</th>
                  {fw.tracks.flatMap((t) => levels.map((l) => {
                    const g = t.levels[l].gates[d.key];
                    const r = t.levels[l].required[d.key];
                    return <td key={t.key + l} className="px-2 py-1.5 text-center text-fg-muted">{g ? <strong className="text-fg">{LEVEL_LABEL[g]}</strong> : r ? LEVEL_LABEL[r] : ""}</td>;
                  }))}</tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-line-subtle px-3 py-2 text-[11px] text-fg-subtle">Bold: mandatory gate. Plain: expected (a weakness if missed, not a blocker).</p>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        {fw.dimensions.map((d) => (
          <article key={d.key} className="rounded-xl border border-line bg-surface p-4 text-[13px]">
            <h3 className="font-medium text-fg">{d.title}</h3>
            <p className="mt-1 text-fg-muted">{d.why}</p>
            <dl className="mt-2 grid gap-1 text-xs">
              <div><dt className="inline text-fg-subtle">Knowledge: </dt><dd className="inline text-fg">{d.knowledge}</dd></div>
              <div><dt className="inline text-fg-subtle">Implementation: </dt><dd className="inline text-fg">{d.implementation}</dd></div>
              <div><dt className="inline text-fg-subtle">Debugging: </dt><dd className="inline text-fg">{d.debugging}</dd></div>
              <div><dt className="inline text-fg-subtle">Architecture: </dt><dd className="inline text-fg">{d.architecture}</dd></div>
              <div><dt className="inline text-fg-subtle">Critical gap: </dt><dd className="inline text-fg">{d.critical_gap}</dd></div>
              {levels.map((l) => <div key={l}><dt className="inline text-fg-subtle">{LEVEL_LABEL[l]}: </dt><dd className="inline text-fg">{d.levels[l]}</dd></div>)}
              <div><dt className="inline text-fg-subtle">Assessed in: </dt><dd className="inline text-fg-muted">{d.assessment_coverage.length ? d.assessment_coverage.join(", ") : "practice labs only"}</dd></div>
              <div><dt className="inline text-fg-subtle">Freshness: </dt><dd className="inline text-fg-muted">{d.freshness_days ?? fw.rules.default_freshness_days} days{d.verifiable ? " · verifiable in FORGE" : " · AI-judged only in FORGE"}</dd></div>
            </dl>
          </article>
        ))}
      </section>
    </div>
  );
}
