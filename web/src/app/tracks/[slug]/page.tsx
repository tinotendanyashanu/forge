import { Check, ChevronLeft, CircleDashed, Clock, GraduationCap, Lock, MessagesSquare } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { StartAssessmentForm } from "@/components/assessment/start-assessment-form";
import { STATE_LABEL, StateBadge, StateDot, pct } from "@/components/mastery/state";
import { TrackIcon } from "@/components/tracks/track-icon";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCurriculum, getLessons, getSkill, getSkillMastery } from "@/lib/api";
import { cn } from "@/lib/cn";
import { difficultyLabel, formatDateTime, pluralize } from "@/lib/format";
import type { CurriculumSkill, LessonSummary, SkillMasteryDetail } from "@/lib/types";

export default function SkillPage({ params }: PageProps<"/tracks/[slug]">) {
  return (
    <PageContainer className="flex flex-col gap-8">
      <Link
        href="/tracks"
        className="inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted transition-colors hover:text-fg"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        All skills
      </Link>
      <Suspense fallback={<SkillSkeleton />}>
        <Skill params={params} />
      </Suspense>
    </PageContainer>
  );
}

async function Skill({ params }: { params: PageProps<"/tracks/[slug]">["params"] }) {
  const { slug } = await params;
  const [skill, curriculum, detail, lessons] = await Promise.all([
    getSkill(slug), getCurriculum(), getSkillMastery(slug), getLessons(slug),
  ]);
  if (!skill) notFound();
  const spec = curriculum.skills.find((s) => s.slug === slug);
  const titles = new Map(curriculum.skills.map((s) => [s.slug, s.title]));
  const assessable = skill.question_count > 0;

  return (
    <div className="flex flex-col gap-12 animate-fade-in">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <TrackIcon slug={skill.slug} className="size-11" />
          <p className="mt-5 text-[13px] font-medium text-fg-subtle">{spec?.category}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg sm:text-[28px]">{skill.title}</h1>
          <p className="mt-2.5 max-w-2xl text-[15px] leading-relaxed text-pretty text-fg-muted">{skill.description}</p>
        </div>
        {detail ? <StateBadge state={detail.mastery.state} /> : null}
      </header>

      {spec ? <Prerequisites spec={spec} titles={titles} detail={detail} /> : null}

      {lessons.length ? <Lessons lessons={lessons} /> : null}

      {assessable ? (
        <section aria-labelledby="start-heading" className="flex flex-col gap-3">
          <h2 id="start-heading" className="text-[15px] font-medium text-fg">Practise</h2>
          <Card className="p-5 sm:p-6">
            <StartAssessmentForm skill={skill} />
          </Card>
          <div className="flex justify-end">
            <ButtonLink href={`/interview?skill=${skill.slug}`} variant="ghost" size="sm">
              <MessagesSquare aria-hidden="true" />
              Practise with the AI interviewer
            </ButtonLink>
          </div>
        </section>
      ) : (
        <EmptyState
          icon={CircleDashed}
          title="No assessments for this skill yet"
          description="The curriculum defines its objectives and competency criteria below, but there are no questions to practise with yet. It never blocks the skills that depend on it."
        />
      )}

      {spec ? <Curriculum spec={spec} detail={detail} /> : null}
      {detail && detail.mastery.evidence_count > 0 ? <Evidence detail={detail} /> : null}
    </div>
  );
}

function Lessons({ lessons }: { lessons: LessonSummary[] }) {
  return (
    <section aria-labelledby="lessons-heading" className="flex flex-col gap-3">
      <h2 id="lessons-heading" className="flex items-center gap-2 text-[15px] font-medium text-fg">
        <GraduationCap className="size-4" aria-hidden="true" />
        Learn
      </h2>
      <ul className="flex flex-col gap-2">
        {lessons.map((l) => (
          <li key={l.slug}>
            <Link
              href={`/lessons/${l.slug}`}
              className="flex items-center justify-between gap-3 rounded-lg border border-line px-4 py-3 text-sm transition-colors hover:border-neutral-600"
            >
              <span className="text-fg">{l.title}</span>
              <span className="flex shrink-0 items-center gap-1 text-xs text-fg-subtle">
                {difficultyLabel[l.difficulty]} · <Clock className="size-3.5" aria-hidden="true" /> {l.estimated_minutes} min
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Prerequisites({
  spec,
  titles,
  detail,
}: {
  spec: CurriculumSkill;
  titles: Map<string, string>;
  detail: SkillMasteryDetail | null;
}) {
  if (spec.prerequisites.length === 0 && spec.dependants.length === 0) return null;
  return (
    <section aria-labelledby="graph-heading" className="grid gap-4 sm:grid-cols-2">
      <h2 id="graph-heading" className="sr-only">Prerequisites and next skills</h2>
      <div>
        <p className="mb-2 text-xs font-medium text-fg-subtle">Builds on</p>
        {spec.prerequisites.length ? (
          <ul className="flex flex-col gap-1.5">
            {spec.prerequisites.map((p) => {
              const state = detail?.prerequisite_states[p] ?? "not_started";
              return (
                <li key={p}>
                  <Link href={`/tracks/${p}`} className="inline-flex items-center gap-2 rounded text-sm text-fg hover:underline">
                    <StateDot state={state} />
                    {titles.get(p)}
                    <span className="text-xs text-fg-subtle">{STATE_LABEL[state]}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-fg-muted">No prerequisites.</p>
        )}
        {detail && !detail.mastery.prerequisites_met ? (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-fg-subtle">
            <Lock className="size-3.5" aria-hidden="true" />
            Recommended after its prerequisites reach Developing. You can still practise it now.
          </p>
        ) : null}
      </div>
      <div>
        <p className="mb-2 text-xs font-medium text-fg-subtle">Unlocks</p>
        {spec.dependants.length ? (
          <ul className="flex flex-wrap gap-2">
            {spec.dependants.map((d) => (
              <li key={d}>
                <Link href={`/tracks/${d}`} className="rounded-lg border border-line px-2.5 py-1 text-sm text-fg-muted hover:text-fg">
                  {titles.get(d)}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-fg-muted">This is a capstone skill.</p>
        )}
      </div>
    </section>
  );
}

function Curriculum({ spec, detail }: { spec: CurriculumSkill; detail: SkillMasteryDetail | null }) {
  const reports = new Map((detail?.levels ?? []).map((l) => [l.level, l]));
  return (
    <section aria-labelledby="curriculum-heading">
      <SectionHeader
        id="curriculum-heading"
        title="Objectives and competency"
        description="What each level requires, and your evidence against it."
      />
      <ul className="mb-5 flex flex-col gap-1.5 text-sm text-fg-muted">
        {spec.learning_objectives.map((o) => (
          <li key={o} className="flex gap-2">
            <span aria-hidden="true" className="text-fg-subtle">–</span>
            {o}
          </li>
        ))}
      </ul>
      <ol className="grid gap-3 lg:grid-cols-3">
        {spec.levels.map((l) => {
          const r = reports.get(l.difficulty);
          return (
            <li key={l.difficulty}>
              <Card className={cn("flex h-full flex-col p-5", r?.demonstrated && "border-fg")}>
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-medium text-fg">{difficultyLabel[l.difficulty]}</h3>
                  {r?.demonstrated ? (
                    <span className="inline-flex items-center gap-1 text-xs text-fg">
                      <Check className="size-3.5" aria-hidden="true" />
                      Demonstrated{r.unverified_only ? " (AI only)" : ""}
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-fg">{l.objective}</p>
                <p className="mt-2 text-[13px] leading-relaxed text-fg-muted">{l.competency}</p>
                <p className="mt-auto pt-4 text-xs text-fg-subtle tabular-nums">
                  {l.question_count ? pluralize(l.question_count, "question") : "No questions yet"}
                  {l.question_count ? (l.verifiable ? " · objectively gradable" : " · AI-evaluated only") : ""}
                </p>
                {r && !r.demonstrated && r.attempts > 0 ? (
                  <p className="mt-2 border-t border-line-subtle pt-2 text-xs leading-relaxed text-fg-muted">
                    Still needs: {r.missing.join("; ")}.
                  </p>
                ) : null}
              </Card>
            </li>
          );
        })}
      </ol>
      <ul className="mt-5 flex flex-wrap gap-2" aria-label="Subskills">
        {spec.subskills.map((s) => (
          <li key={s.slug} className="rounded-lg border border-line px-3 py-1 text-[13px] text-fg-muted">
            {s.title} <span className="text-fg-subtle tabular-nums">· {s.question_count}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Evidence({ detail }: { detail: SkillMasteryDetail }) {
  const m = detail.mastery;
  return (
    <section aria-labelledby="evidence-heading" className="flex flex-col gap-6">
      <SectionHeader id="evidence-heading" title="Your evidence" description={m.reasons.join(" ")} />
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {[
          ["Accuracy (verified)", pct(m.knowledge_accuracy)],
          ["Reasoning (AI, unverified)", pct(m.reasoning_score)],
          ["Debugging (AI, unverified)", pct(m.debugging_score)],
          ["Retention", pct(m.retention_score)],
          ["Successful attempts", String(m.successful_attempts)],
          ["Distinct questions", String(m.distinct_questions)],
          ["Independent sessions", String(m.distinct_sessions)],
          ["Uncertainty", m.uncertainty === null ? "—" : m.uncertainty < 0.35 ? "Low" : m.uncertainty < 0.6 ? "Medium" : "High"],
          ["Grader confidence (AI)", pct(m.ai_confidence)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-line-subtle bg-surface px-4 py-3">
            <dt className="text-xs text-fg-subtle">{label}</dt>
            <dd className="mt-1 text-lg font-semibold text-fg tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {detail.review ? (
        <p className="text-sm text-fg-muted">
          Next review <time dateTime={detail.review.due_at}>{formatDateTime(detail.review.due_at)}</time>
          {" · "}interval {pluralize(detail.review.interval_days, "day")}
          {detail.review.lapses ? ` · ${pluralize(detail.review.lapses, "lapse")}` : ""}
        </p>
      ) : null}
      <ul className="divide-y divide-line-subtle overflow-hidden rounded-xl border border-line bg-surface">
        {detail.evidence.map((e) => (
          <li key={e.id} className="flex items-center justify-between gap-4 px-5 py-3 text-sm">
            <div className="min-w-0">
              <p className="truncate text-fg">{e.question_title}</p>
              <p className="mt-0.5 text-xs text-fg-subtle">
                {difficultyLabel[e.difficulty]} ·{" "}
                {e.source === "objective_assessment" ? "Graded (verified)" : e.source === "ai_interview" ? "AI interview (unverified)" : "Said “I don't know”"}
                {e.hints_used ? ` · ${pluralize(e.hints_used, "hint")}` : ""}
              </p>
            </div>
            <div className="shrink-0 text-right text-xs tabular-nums">
              <p className={e.success ? "text-fg" : "text-fg-muted"}>
                {e.source === "ai_interview" ? pct(e.score) : e.success ? "Correct" : "Missed"}
              </p>
              <p className="text-fg-subtle">
                <time dateTime={e.observed_at}>{formatDateTime(e.observed_at)}</time>
              </p>
            </div>
          </li>
        ))}
      </ul>
      {detail.misconceptions.length ? (
        <div>
          <h3 className="mb-2 text-sm font-medium text-fg">Misconception history</h3>
          <ul className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4 text-sm text-fg-muted">
            {detail.misconceptions.map((mc, i) => (
              <li key={i}>
                <span className="text-fg">{mc.known_misconception ?? mc.description}</span>
                <span className="block text-xs text-fg-subtle">
                  {mc.question_title} · {formatDateTime(mc.created_at)}
                  {mc.observed ? "" : " · inferred, not quoted"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function SkillSkeleton() {
  return (
    <LoadingRegion label="Loading skill" className="flex flex-col gap-10">
      <div>
        <Skeleton className="size-11 rounded-lg" />
        <Skeleton className="mt-5 h-7 w-48" />
        <Skeleton className="mt-4 h-4 w-full max-w-xl" />
      </div>
      <Skeleton className="h-56 w-full rounded-xl" />
      <Skeleton className="h-48 w-full rounded-xl" />
    </LoadingRegion>
  );
}
