import { ArrowRight, History, SquareCode } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { ExecutionBanner } from "@/components/coding/execution-banner";
import { SubmissionList } from "@/components/coding/submission-list";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCodeSubmissions, getExecutionStatus, getPracticalProgress } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";
import { DIFFICULTIES } from "@/lib/types";

export const metadata: Metadata = { title: "Coding lab" };

export default function LabPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Coding lab"
        title="Write code. Let the tests decide."
        description="Solve real engineering challenges. Hidden tests run in an isolated sandbox, and passing them is verified practical evidence for your skills."
        actions={
          <ButtonLink href="/lab/challenges">
            <SquareCode aria-hidden="true" />
            Browse challenges
          </ButtonLink>
        }
      />
      <Suspense fallback={<Skeleton className="h-14 w-full rounded-lg" />}>
        <Status />
      </Suspense>
      <section aria-labelledby="practical-heading">
        <SectionHeader
          id="practical-heading"
          title="Practical skill progress"
          description="Verified only: challenges whose hidden tests all passed in the sandbox."
        />
        <Suspense fallback={<LoadingRegion label="Loading progress"><Skeleton className="h-64 w-full rounded-xl" /></LoadingRegion>}>
          <Progress />
        </Suspense>
      </section>
      <section aria-labelledby="recent-heading">
        <SectionHeader
          id="recent-heading"
          title="Recent submissions"
          action={<ButtonLink href="/lab/submissions" variant="ghost" size="sm">All<ArrowRight aria-hidden="true" /></ButtonLink>}
        />
        <Suspense fallback={<Skeleton className="h-40 w-full rounded-xl" />}>
          <Recent />
        </Suspense>
      </section>
    </PageContainer>
  );
}

async function Status() {
  const status = await getExecutionStatus().catch(() => null);
  return <ExecutionBanner status={status} />;
}

async function Progress() {
  const progress = await getPracticalProgress();
  if (!progress) {
    return (
      <EmptyState
        icon={SquareCode}
        title="No practical evidence yet"
        description="Submit a solution to any challenge. Progress appears here once hidden tests have run in the verified sandbox."
        action={<ButtonLink href="/lab/challenges" size="sm">Pick a challenge</ButtonLink>}
      />
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[620px] text-sm">
        <caption className="sr-only">Coding challenges solved per skill</caption>
        <thead>
          <tr className="border-b border-line-subtle text-left text-xs text-fg-subtle">
            <th scope="col" className="px-5 py-3 font-medium">Skill</th>
            {DIFFICULTIES.map((d) => (
              <th key={d} scope="col" className="px-3 py-3 text-right font-medium">{difficultyLabel[d]}</th>
            ))}
            <th scope="col" className="px-3 py-3 text-right font-medium">Solved</th>
            <th scope="col" className="px-5 py-3 text-right font-medium">Practical score</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line-subtle">
          {progress.skills.map((s) => (
            <tr key={s.skill.slug} className={s.attempted ? "text-fg" : "text-fg-subtle"}>
              <th scope="row" className="px-5 py-3 text-left font-normal">
                <Link href={`/lab/challenges?skill=${s.skill.slug}`} className="rounded hover:underline">{s.skill.title}</Link>
              </th>
              {DIFFICULTIES.map((d) => {
                const c = s.by_difficulty[d];
                return (
                  <td key={d} className="px-3 py-3 text-right text-xs tabular-nums">
                    {c ? `${c.solved}/${c.total}` : "—"}
                  </td>
                );
              })}
              <td className="px-3 py-3 text-right tabular-nums">{s.solved}/{s.total}</td>
              <td className="px-5 py-3 text-right tabular-nums">
                {s.practical_score === null ? "—" : `${Math.round(s.practical_score * 100)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line-subtle px-5 py-2.5 text-xs text-fg-subtle">
        {progress.verified_submissions} verified of {progress.submissions} submissions. Practical score is the
        recency-weighted share of hidden tests passed; “—” means no verified submission yet.
      </p>
    </div>
  );
}

async function Recent() {
  const subs = await getCodeSubmissions(undefined, 5);
  if (!subs || subs.length === 0) {
    return <EmptyState icon={History} title="No submissions yet" description="Your submissions and their test results will appear here." />;
  }
  return <SubmissionList submissions={subs} />;
}
