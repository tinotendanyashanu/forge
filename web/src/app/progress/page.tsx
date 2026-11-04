import { ChartLine, History } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AnswerHistoryList } from "@/components/history/answer-history-list";
import { TrackIcon } from "@/components/tracks/track-icon";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { STATE_LABEL, StateDot, pct } from "@/components/mastery/state";
import { getAnswerHistory, getMastery, getProgress } from "@/lib/api";
import { difficultyLabel, formatDateTime } from "@/lib/format";
import type { SkillMastery, SkillProgress } from "@/lib/types";

export const metadata: Metadata = { title: "Progress" };

export default function ProgressPage() {
  return (
    <PageContainer className="flex flex-col gap-12">
      <PageHeader
        eyebrow="Progress"
        title="Your progress"
        description="Mastery is computed from recorded evidence only: objectively graded answers count fully, AI evaluations count as unverified, and no single answer moves a level."
        actions={
          <ButtonLink href="/progress/history" variant="secondary">
            History
          </ButtonLink>
        }
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading progress" className="flex flex-col gap-12">
            <Skeleton className="h-72 w-full rounded-xl" />
            <Skeleton className="h-56 w-full rounded-xl" />
          </LoadingRegion>
        }
      >
        <ProgressContent />
      </Suspense>
    </PageContainer>
  );
}

async function ProgressContent() {
  const [progress, history, mastery] = await Promise.all([
    getProgress(),
    getAnswerHistory({ limit: 50 }),
    getMastery(),
  ]);
  const practised = progress?.skills.filter((s) => s.answers_submitted > 0) ?? [];

  const hasEvidence = mastery?.skills.some((s) => s.evidence_count > 0) ?? false;
  if (!progress || (practised.length === 0 && !hasEvidence)) {
    return (
      <EmptyState
        icon={ChartLine}
        title="Nothing recorded yet"
        description="Answer a question in any skill track and your activity will show up here. Progress is saved on the server, so it survives refreshes."
        action={
          <ButtonLink href="/tracks" size="sm">
            Start practising
          </ButtonLink>
        }
      />
    );
  }

  return (
    <>
      {mastery ? <MasteryTable skills={mastery.skills} version={mastery.algorithm_version} /> : null}
      <section aria-labelledby="by-skill-heading">
        <SectionHeader
          id="by-skill-heading"
          title="Activity by skill"
          description="Graded counts include multiple-choice answers only."
        />
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[640px] text-sm">
            <caption className="sr-only">Activity per skill</caption>
            <thead>
              <tr className="border-b border-line-subtle text-left text-xs text-fg-subtle">
                <th scope="col" className="px-5 py-3 font-medium">Skill</th>
                <th scope="col" className="px-3 py-3 text-right font-medium">Sessions</th>
                <th scope="col" className="px-3 py-3 text-right font-medium">Answers</th>
                <th scope="col" className="px-3 py-3 text-right font-medium">Correct / graded</th>
                <th scope="col" className="px-3 py-3 text-right font-medium">Written (not scored)</th>
                <th scope="col" className="px-5 py-3 text-right font-medium">Last activity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle">
              {progress.skills.map((s) => (
                <SkillRow key={s.skill.slug} p={s} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="history-heading">
        <SectionHeader
          id="history-heading"
          title="Answer history"
          description="Most recent first. Open any answer to review its feedback."
        />
        {history && history.length > 0 ? (
          <AnswerHistoryList items={history} />
        ) : (
          <EmptyState icon={History} title="No answers yet" description="Submitted answers appear here." />
        )}
      </section>
    </>
  );
}

function SkillRow({ p }: { p: SkillProgress }) {
  const idle = p.answers_submitted === 0 && p.sessions_started === 0;
  return (
    <tr className={idle ? "text-fg-subtle" : "text-fg"}>
      <th scope="row" className="px-5 py-3 text-left font-normal">
        <Link
          href={`/tracks/${p.skill.slug}`}
          className="inline-flex items-center gap-3 rounded transition-colors hover:text-fg"
        >
          <TrackIcon slug={p.skill.slug} className="size-7 [&_svg]:size-3.5" />
          {p.skill.title}
        </Link>
      </th>
      <td className="px-3 py-3 text-right tabular-nums">
        {p.sessions_completed}/{p.sessions_started}
        <span className="sr-only"> completed</span>
      </td>
      <td className="px-3 py-3 text-right tabular-nums">{p.answers_submitted}</td>
      <td className="px-3 py-3 text-right tabular-nums">
        {p.objective_graded > 0 ? `${p.objective_correct} / ${p.objective_graded}` : "—"}
      </td>
      <td className="px-3 py-3 text-right tabular-nums">{p.pending_ai_evaluation}</td>
      <td className="px-5 py-3 text-right text-xs text-fg-subtle tabular-nums">
        {p.last_activity_at ? (
          <time dateTime={p.last_activity_at}>{formatDateTime(p.last_activity_at)}</time>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}

function MasteryTable({ skills, version }: { skills: SkillMastery[]; version: string }) {
  const rows = skills.filter((s) => s.assessable);
  return (
    <section aria-labelledby="mastery-heading">
      <SectionHeader
        id="mastery-heading"
        title="Mastery"
        description={`“—” means there is no evidence of that kind yet. Algorithm ${version}.`}
      />
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">Mastery by skill</caption>
          <thead>
            <tr className="border-b border-line-subtle text-left text-xs text-fg-subtle">
              <th scope="col" className="px-5 py-3 font-medium">Skill</th>
              <th scope="col" className="px-3 py-3 font-medium">State</th>
              <th scope="col" className="px-3 py-3 font-medium">Demonstrated</th>
              <th scope="col" className="px-3 py-3 text-right font-medium" title="Objectively graded answers">Accuracy (verified)</th>
              <th scope="col" className="px-3 py-3 text-right font-medium" title="AI evaluations; unverified">Reasoning (AI)</th>
              <th scope="col" className="px-3 py-3 text-right font-medium">Retention</th>
              <th scope="col" className="px-5 py-3 text-right font-medium">Evidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-subtle">
            {rows.map((s) => (
              <tr key={s.skill.slug} className={s.evidence_count ? "text-fg" : "text-fg-subtle"}>
                <th scope="row" className="px-5 py-3 text-left font-normal">
                  <Link href={`/tracks/${s.skill.slug}`} className="rounded hover:underline">
                    {s.skill.title}
                  </Link>
                </th>
                <td className="px-3 py-3">
                  <span className="inline-flex items-center gap-2 text-xs">
                    <StateDot state={s.state} />
                    {STATE_LABEL[s.state]}
                  </span>
                </td>
                <td className="px-3 py-3 text-xs">
                  {s.demonstrated_level ? difficultyLabel[s.demonstrated_level] : "—"}
                  {s.unverified_only ? <span className="text-fg-subtle"> (AI only)</span> : null}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">{pct(s.knowledge_accuracy)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{pct(s.reasoning_score)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{pct(s.retention_score)}</td>
                <td className="px-5 py-3 text-right text-xs tabular-nums">
                  {s.evidence_count ? `${s.verified_count} verified / ${s.evidence_count}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-fg-subtle">
        Practical implementation isn&apos;t scored: it needs verified practical tests, which FORGE doesn&apos;t run yet.
      </p>
    </section>
  );
}
