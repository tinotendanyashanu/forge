import { ArrowRight, BriefcaseBusiness, ClipboardList, Compass, FileSearch, History, Map as MapIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { saveCareerProfile } from "@/app/actions";
import { LEVEL_LABEL, STATUS_LABEL, TRACK_LABEL, date, levelLabel, pct } from "@/components/career/format";
import { BenchmarkList, CompetencyMatrix, ReadinessHeadline } from "@/components/career/readiness";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCareerDashboard } from "@/lib/api";
import { CAREER_LEVELS, CAREER_TRACKS } from "@/lib/types";

export const metadata: Metadata = { title: "Career" };

const field = "w-full rounded-md border border-line bg-canvas px-2.5 py-1.5 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none";

export default function CareerPage({ searchParams }: PageProps<"/career">) {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="FORGE Career"
        title="Evidence-backed engineering readiness"
        description="What you have demonstrated in FORGE, measured against an explicit, versioned competency framework. Gaps are named; missing evidence is reported as missing, never guessed."
        actions={
          <>
            <ButtonLink href="/career/assessments" variant="secondary"><ClipboardList aria-hidden="true" />Assessments</ButtonLink>
            <ButtonLink href="/career/roadmap"><MapIcon aria-hidden="true" />Roadmap</ButtonLink>
          </>
        }
      />
      <Suspense fallback={<LoadingRegion label="Loading readiness"><Skeleton className="h-96 w-full rounded-xl" /></LoadingRegion>}>
        <Dashboard searchParams={searchParams} />
      </Suspense>
    </PageContainer>
  );
}

async function Dashboard({ searchParams }: Pick<PageProps<"/career">, "searchParams">) {
  const sp = await searchParams;
  const track = typeof sp.track === "string" ? sp.track : undefined;
  const level = typeof sp.level === "string" ? sp.level : undefined;
  const d = await getCareerDashboard(track, level);
  if (!d) {
    return <EmptyState icon={BriefcaseBusiness} title="Choose a target to begin" description="Set your target role and level below." action={<ProfileForm />} />;
  }
  const r = d.readiness;
  const bench = new Set([...r.target.gates, ...r.target.required].map((g) => g.dimension));
  return (
    <div className="flex flex-col gap-10">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <ReadinessHeadline r={r} />
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-medium text-fg">Target</h2>
          <ProfileForm track={d.profile.track} level={d.profile.target_level} goal={d.profile.goal} exp={d.profile.self_reported} />
        </Card>
      </div>

      {d.next_assessment || d.active_attempts.length ? (
        <section aria-labelledby="next-h" className="grid gap-4 lg:grid-cols-2">
          {d.active_attempts.length ? (
            <div>
              <SectionHeader id="next-h" title="In progress" />
              <ul className="flex flex-col gap-2">
                {d.active_attempts.map((a) => (
                  <li key={a.id}>
                    <Link href={`/career/attempts/${a.id}`} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 hover:bg-surface-hover">
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm text-fg">{a.title}</span>
                        <span className="text-xs text-fg-subtle">{a.status === "created" ? "Not started" : `Deadline ${a.deadline_at ? new Date(a.deadline_at).toLocaleString() : "none"}`}</span></span>
                      <ArrowRight className="size-4 text-fg-subtle" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {d.next_assessment ? (
            <div>
              <SectionHeader title="Recommended assessment" />
              <Card className="flex flex-col gap-2 p-5">
                <p className="text-sm text-fg">{d.next_assessment.title}</p>
                <p className="text-xs text-fg-muted">{d.next_assessment.reassess_on ? `Your roadmap schedules reassessment on ${date(d.next_assessment.reassess_on)}.` : "Take it to establish formal evidence."}</p>
                <div><ButtonLink size="sm" href={`/career/assessments/${d.next_assessment.template}`}><Compass aria-hidden="true" />Open</ButtonLink></div>
              </Card>
            </div>
          ) : null}
        </section>
      ) : null}

      <section aria-labelledby="gates-h" className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-5">
          <h2 id="gates-h" className="sr-only">Benchmark</h2>
          <BenchmarkList title={`Mandatory gates for ${LEVEL_LABEL[r.target_level]}`} rows={r.target.gates} />
          <BenchmarkList title="Critical gaps" rows={r.critical_gaps} empty="No critical gaps found in the evidence so far." />
        </div>
        <div className="flex flex-col gap-5">
          <BenchmarkList title="Also expected at this level" rows={r.target.required} />
          <BenchmarkList title="Missing evidence" rows={r.missing_evidence} empty="Every benchmark competency has evidence." />
        </div>
      </section>

      <section aria-labelledby="matrix-h">
        <SectionHeader id="matrix-h" title="Competency matrix" description="All 18 competencies. Faded rows are outside the selected target's benchmark." action={<ButtonLink href="/career/framework" variant="ghost" size="sm">Criteria<ArrowRight aria-hidden="true" /></ButtonLink>} />
        <CompetencyMatrix dims={r.dimensions} highlight={bench} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="hist-h">
          <SectionHeader id="hist-h" title="Assessment history and progress" description="Stored reports never change when criteria are updated." />
          {d.reports.length ? (
            <ul className="divide-y divide-line-subtle rounded-xl border border-line bg-surface">
              {d.reports.map((x) => (
                <li key={x.id}>
                  <Link href={`/career/reports/${x.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover">
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm text-fg">{x.title}</span>
                      <span className="text-xs text-fg-subtle">{date(x.created_at)} · {TRACK_LABEL[x.track]} {LEVEL_LABEL[x.target_level]} · {STATUS_LABEL[x.target_status]}</span></span>
                    <span className="text-xs text-fg-muted">{levelLabel(x.demonstrated_level)} · {pct(x.coverage)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon={History} title="No reports yet" description="Finalize an assessment or open your roadmap to record a readiness snapshot." />}
        </section>
        <section aria-labelledby="more-h">
          <SectionHeader id="more-h" title="Prepare for a specific role" />
          <Card className="flex flex-col gap-3 p-5">
            <p className="text-sm text-fg-muted">Paste a job description to map its requirements to the framework and see matches, gaps and untested requirements.</p>
            <div><ButtonLink href="/career/jobs" variant="secondary" size="sm"><FileSearch aria-hidden="true" />Job description matcher</ButtonLink></div>
            <p className="border-t border-line-subtle pt-3 text-xs leading-relaxed text-fg-subtle">{d.seniority_note}</p>
            <p className="text-xs leading-relaxed text-fg-subtle">{d.profile.note}</p>
          </Card>
        </section>
      </div>
    </div>
  );
}

function ProfileForm({ track = "fullstack", level = "mid", goal = "", exp = {} }: { track?: string; level?: string; goal?: string; exp?: Record<string, string> }) {
  return (
    <form action={saveCareerProfile} className="flex flex-col gap-3 text-left">
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-fg-subtle">Role
          <select name="track" defaultValue={track} className={`${field} mt-1`}>
            {CAREER_TRACKS.map((t) => <option key={t} value={t}>{TRACK_LABEL[t]}</option>)}
          </select>
        </label>
        <label className="text-xs text-fg-subtle">Level
          <select name="target_level" defaultValue={level} className={`${field} mt-1`}>
            {CAREER_LEVELS.map((l) => <option key={l} value={l}>{LEVEL_LABEL[l]}</option>)}
          </select>
        </label>
      </div>
      <label className="text-xs text-fg-subtle">Goal
        <input name="goal" defaultValue={goal} maxLength={500} className={`${field} mt-1`} placeholder="e.g. Prepare for mid-level Python/React roles" />
      </label>
      <details className="text-xs text-fg-subtle">
        <summary className="cursor-pointer">Self-reported experience (context only, never evidence)</summary>
        <div className="mt-2 flex flex-col gap-2">
          <input name="years" defaultValue={exp.years ?? ""} maxLength={20} className={field} placeholder="Years of experience" />
          <input name="roles" defaultValue={exp.roles ?? ""} maxLength={500} className={field} placeholder="Roles held" />
          <textarea name="responsibilities" defaultValue={exp.responsibilities ?? ""} maxLength={500} className={`${field} min-h-14`} placeholder="Responsibilities" />
        </div>
      </details>
      <Button type="submit" size="sm" variant="secondary">Save target</Button>
    </form>
  );
}
