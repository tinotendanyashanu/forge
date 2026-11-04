import { ArrowRight, Compass, History, Siren, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { COMPETENCY_LABEL, LEVEL_LABEL, STATUS_LABEL, pct } from "@/components/ops/format";
import { STATE_LABEL, StateDot } from "@/components/mastery/state";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getOpsDashboard, getOpsScenarios, getOpsStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { OPS_LEVELS } from "@/lib/types";

export const metadata: Metadata = { title: "FORGE OPS" };

export default function OpsPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="FORGE OPS · production engineering simulator"
        title="Investigate. Mitigate. Explain."
        description="Work realistic, deterministic incidents with logs, metrics, traces and deployments. Your decisions are graded by the scenario's rules; an AI incident commander challenges your reasoning. Everything is simulated: nothing touches real infrastructure."
      />
      <Suspense fallback={<Skeleton className="h-12 w-full rounded-lg" />}>
        <Status />
      </Suspense>
      <Suspense fallback={<LoadingRegion label="Loading FORGE OPS"><Skeleton className="h-96 w-full rounded-xl" /></LoadingRegion>}>
        <Dashboard />
      </Suspense>
    </PageContainer>
  );
}

async function Status() {
  const s = await getOpsStatus();
  if (s?.llm.configured) {
    return <p className="font-mono text-xs text-fg-subtle">AI incident commander: {s.llm.provider}/{s.llm.model} · {s.evaluation_version} · {s.rubric_version}</p>;
  }
  return (
    <p role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg-muted">
      No AI provider is configured on the API. Simulations, verified outcomes and postmortems work; AI commander answers and reviews are recorded as unavailable.
    </p>
  );
}

async function Dashboard() {
  const [dash, scenarios] = await Promise.all([getOpsDashboard(), getOpsScenarios()]);
  const progress = new Map(dash?.scenarios.map((s) => [s.slug, s]) ?? []);
  const rec = dash?.recommended ?? (scenarios[0] ? { ...scenarios[0], reason: "start", detail: "A good first incident." } : null);
  return (
    <div className="flex flex-col gap-10">
      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="active-h">
          <SectionHeader id="active-h" title="Active incidents" />
          {dash?.active.length ? (
            <ul className="flex flex-col gap-2">
              {dash.active.map((s) => (
                <li key={s.id}>
                  <Link href={`/ops/sessions/${s.id}`} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 hover:bg-surface-hover">
                    <Siren className="size-4 shrink-0 text-fg-muted" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-fg">{s.scenario.title}</span>
                      <span className="text-xs text-fg-subtle">{STATUS_LABEL[s.status]} · +{s.minute} simulated min · {formatDateTime(s.updated_at)}</span>
                    </span>
                    <ArrowRight className="size-4 text-fg-subtle" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Siren} title="No open incidents" description="Pick an incident from the library below." />
          )}
        </section>
        <section aria-labelledby="rec-h">
          <SectionHeader id="rec-h" title="Recommended next incident" />
          {rec ? (
            <Card className="flex flex-col gap-3 p-5">
              <p className="text-xs text-fg-subtle">{LEVEL_LABEL[rec.level]}</p>
              <h3 className="text-base font-medium text-fg">{rec.title}</h3>
              <p className="text-sm text-fg-muted">{rec.detail}</p>
              <div><ButtonLink href={`/ops/incidents/${rec.slug}`} size="sm"><Compass aria-hidden="true" />Open briefing</ButtonLink></div>
            </Card>
          ) : (
            <EmptyState icon={Compass} title="All caught up" description="You've attempted every unlocked incident. Retry one with a different approach." />
          )}
        </section>
      </div>

      <section aria-labelledby="lib-h">
        <SectionHeader id="lib-h" title="Incident library" description="Authored, versioned scenarios. Difficulty increases from beginner to senior." />
        <div className="grid gap-6 lg:grid-cols-2">
          {OPS_LEVELS.map((lvl) => (
            <div key={lvl}>
              <h3 className="mb-2 text-xs font-medium text-fg-subtle">{LEVEL_LABEL[lvl]}</h3>
              <ul className="flex flex-col gap-2">
                {scenarios.filter((s) => s.level === lvl).map((s) => {
                  const p = progress.get(s.slug);
                  return (
                    <li key={s.slug}>
                      <Link href={`/ops/incidents/${s.slug}`} className="block rounded-xl border border-line bg-surface p-4 hover:bg-surface-hover">
                        <span className="flex items-start justify-between gap-3">
                          <span className="text-sm font-medium text-fg">{s.title}</span>
                          <span className="shrink-0 text-xs text-fg-subtle tabular-nums">{p?.best_score != null ? `best ${pct(p.best_score)}` : p?.attempted ? "attempted" : `v${s.version}`}</span>
                        </span>
                        <span className="mt-1 line-clamp-2 block text-xs leading-relaxed text-fg-muted">{s.summary}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="hist-h">
          <SectionHeader id="hist-h" title="Incident history" description="Reopen any attempt to review the evidence, replay the timeline or finish the postmortem." />
          {dash?.history.length ? (
            <ul className="divide-y divide-line-subtle rounded-xl border border-line bg-surface">
              {dash.history.map((s) => (
                <li key={s.id}>
                  <Link href={`/ops/sessions/${s.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-fg">{s.scenario.title}</span>
                      <span className="text-xs text-fg-subtle">{STATUS_LABEL[s.status]} · {s.ended_at ? formatDateTime(s.ended_at) : ""}</span>
                    </span>
                    <span className="text-sm text-fg tabular-nums">{s.outcome_score !== null ? pct(s.outcome_score) : "—"}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={History} title="No completed incidents" description="Resolved and ended attempts appear here." />
          )}
        </section>
        <section aria-labelledby="att-h">
          <SectionHeader id="att-h" title="Skills needing attention" description={dash?.evidence_rule} />
          <Card className="flex flex-col gap-4 p-5">
            {dash?.mistakes.length ? (
              <div>
                <h3 className="mb-2 text-xs font-medium text-fg-subtle">Recurring mistakes</h3>
                <ul className="flex flex-col gap-2">
                  {dash.mistakes.map((m) => (
                    <li key={m.tag} className="text-[13px]">
                      <p className="flex items-center gap-1.5 text-fg"><TriangleAlert className="size-3.5" aria-hidden="true" />{m.title} <span className="text-xs text-fg-subtle">× {m.count}</span></p>
                      <p className="text-xs text-fg-muted">{m.lesson} <Link className="underline hover:text-fg" href={`/tracks/${m.skill}`}>Review {m.skill}</Link></p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : <p className="text-sm text-fg-muted">Recurring mistakes and remediation lessons appear after your first incidents.</p>}
            {dash && Object.keys(dash.competencies).length ? (
              <div>
                <h3 className="mb-2 text-xs font-medium text-fg-subtle">Competencies (verified outcomes)</h3>
                <ul className="grid gap-1.5 sm:grid-cols-2">
                  {Object.entries(dash.competencies).map(([k, c]) => (
                    <li key={k} className="flex justify-between gap-2 text-xs">
                      <span className="text-fg">{COMPETENCY_LABEL[k] ?? k}</span>
                      <span className="text-fg-muted tabular-nums">{c.status === "assessed" ? pct(c.score) : `needs more evidence (${c.distinct_scenarios}/2)`}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {dash?.skills.length ? (
              <div>
                <h3 className="mb-2 text-xs font-medium text-fg-subtle">Mastery (from all evidence)</h3>
                <ul className="flex flex-col gap-1.5">
                  {dash.skills.map((s) => (
                    <li key={s.slug} className="flex items-center gap-2 text-xs">
                      <StateDot state={s.state} />
                      <span className="text-fg">{s.title}</span>
                      <span className="ml-auto text-fg-muted">{STATE_LABEL[s.state]} · practical {pct(s.practical_score)} · debugging {pct(s.debugging_score)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>
        </section>
      </div>
    </div>
  );
}
