import { ArrowRight, Compass, History, LayoutGrid, Network } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { COMPETENCY_LABEL, CRITERION_LABEL, LEVEL_LABEL } from "@/components/design/components";
import { STATE_LABEL, StateDot } from "@/components/mastery/state";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader, SectionHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getDesignChallenges, getDesignDashboard, getDesignStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { DESIGN_LEVELS } from "@/lib/types";

export const metadata: Metadata = { title: "Design lab" };

const pct = (x: number | null) => (x === null ? "—" : `${Math.round(x * 100)}%`);

export default function DesignLabPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="System design lab"
        title="Design systems. Defend every decision."
        description="Build architectures on a canvas, explain them, and face an AI interviewer that probes trade-offs and failure modes. A diagram is not proof that a design works: your reasoning is what gets evaluated."
        actions={
          <ButtonLink href="/design/challenges">
            <LayoutGrid aria-hidden="true" />
            Browse challenges
          </ButtonLink>
        }
      />
      <Suspense fallback={<Skeleton className="h-12 w-full rounded-lg" />}>
        <Status />
      </Suspense>
      <Suspense
        fallback={
          <LoadingRegion label="Loading design lab" className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-48 rounded-xl" />
            <Skeleton className="h-48 rounded-xl" />
          </LoadingRegion>
        }
      >
        <Dashboard />
      </Suspense>
    </PageContainer>
  );
}

async function Status() {
  const status = await getDesignStatus();
  if (status?.llm.configured) {
    return (
      <p className="font-mono text-xs text-fg-subtle">
        AI reviewer: {status.llm.provider}/{status.llm.model} · {status.evaluation_version} · {status.rubric_version}
      </p>
    );
  }
  return (
    <p role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg-muted">
      No AI provider is configured on the API. You can design, snapshot and write decision records; reviews and
      evaluations are recorded as unavailable until FORGE_LLM_* (Ollama Cloud) is set.
    </p>
  );
}

async function Dashboard() {
  const [dash, challenges] = await Promise.all([getDesignDashboard(), getDesignChallenges()]);
  const rec = dash?.recommended ?? (challenges[0] ? { ...challenges[0], reason: "start", detail: "A good first design challenge." } : null);

  return (
    <div className="flex flex-col gap-10">
      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="continue-heading">
          <SectionHeader id="continue-heading" title="Continue designing" />
          {dash?.continue.length ? (
            <ul className="flex flex-col gap-2">
              {dash.continue.map((p) => (
                <li key={p.id}>
                  <Link href={`/design/projects/${p.id}`} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 hover:bg-surface-hover">
                    <Network className="size-4 shrink-0 text-fg-muted" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-fg">{p.title}</span>
                      <span className="text-xs text-fg-subtle">
                        {LEVEL_LABEL[p.challenge.level]} · {p.components} components · {formatDateTime(p.updated_at)}
                      </span>
                    </span>
                    <ArrowRight className="size-4 text-fg-subtle" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Network} title="No designs yet" description="Pick a challenge and start a design. It saves as you work." />
          )}
        </section>
        <section aria-labelledby="next-heading">
          <SectionHeader id="next-heading" title="Recommended next challenge" />
          {rec ? (
            <Card className="flex flex-col gap-3 p-5">
              <p className="text-xs text-fg-subtle">{LEVEL_LABEL[rec.level]}</p>
              <h3 className="text-base font-medium text-fg">{rec.title}</h3>
              <p className="text-sm text-fg-muted">{rec.detail}</p>
              <div>
                <ButtonLink href={`/design/challenges/${rec.slug}`} size="sm">
                  <Compass aria-hidden="true" />Open challenge
                </ButtonLink>
              </div>
            </Card>
          ) : (
            <EmptyState icon={Compass} title="All caught up" description="You've attempted every unlocked challenge. Revisit one to improve your score." />
          )}
        </section>
      </div>

      <section aria-labelledby="challenges-heading">
        <SectionHeader
          id="challenges-heading"
          title="Available challenges"
          action={<ButtonLink href="/design/challenges" variant="ghost" size="sm">All<ArrowRight aria-hidden="true" /></ButtonLink>}
        />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {DESIGN_LEVELS.map((lvl) => {
            const items = challenges.filter((c) => c.level === lvl);
            const done = dash?.challenges.filter((c) => c.level === lvl && c.attempted).length ?? 0;
            return (
              <Link key={lvl} href={`/design/challenges#${lvl}`} className="rounded-xl border border-line bg-surface p-4 hover:bg-surface-hover">
                <p className="text-sm font-medium text-fg">{LEVEL_LABEL[lvl]}</p>
                <p className="mt-1 text-xs text-fg-subtle">{items.length} challenges · {done} attempted</p>
                <ul className="mt-3 flex flex-col gap-1 text-xs text-fg-muted">
                  {items.slice(0, 4).map((c) => <li key={c.slug} className="truncate">{c.title}</li>)}
                </ul>
              </Link>
            );
          })}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="reviews-heading">
          <SectionHeader id="reviews-heading" title="Review history" description="AI evaluations of your designs. Not proof of mastery." />
          {dash?.reviews.length ? (
            <ul className="divide-y divide-line-subtle rounded-xl border border-line bg-surface">
              {dash.reviews.map((r) => (
                <li key={r.id}>
                  <Link href={`/design/evaluations/${r.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-fg">{r.project_title}</span>
                      <span className="text-xs text-fg-subtle">v{r.architecture_version} · {formatDateTime(r.created_at)}</span>
                    </span>
                    <span className="text-sm text-fg tabular-nums">{r.status === "evaluated" ? pct(r.total_score) : r.status}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={History} title="No evaluations yet" description="Request an evaluation from the AI review panel in any design." />
          )}
        </section>

        <section aria-labelledby="attention-heading">
          <SectionHeader id="attention-heading" title="Skills needing attention" description={dash?.evidence_rule} />
          <Card className="flex flex-col gap-4 p-5">
            {dash?.weak_criteria.length ? (
              <ul className="flex flex-col gap-2">
                {dash.weak_criteria.map((w) => (
                  <li key={w.criterion} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-fg">{CRITERION_LABEL[w.criterion] ?? w.criterion}</span>
                    <span className="text-xs text-fg-muted tabular-nums">{pct(w.average)} across {w.evaluations} evaluations</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-fg-muted">Weak criteria appear after your first evaluations.</p>
            )}
            {dash && Object.keys(dash.competencies).length ? (
              <div>
                <h3 className="mb-2 text-xs font-medium text-fg-subtle">Competencies</h3>
                <ul className="grid gap-1.5 sm:grid-cols-2">
                  {Object.entries(dash.competencies).map(([k, c]) => (
                    <li key={k} className="flex items-center justify-between gap-2 text-xs">
                      <span className="text-fg">{COMPETENCY_LABEL[k] ?? k}</span>
                      <span className="text-fg-muted tabular-nums">
                        {c.status === "assessed" ? pct(c.score) : `needs more evidence (${c.distinct_challenges}/2)`}
                      </span>
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
                    <li key={s.slug}>
                      <Link href={`/progress#${s.slug}`} className="flex items-center gap-2 text-xs hover:underline">
                        <StateDot state={s.state} />
                        <span className="text-fg">{s.title}</span>
                        <span className="ml-auto text-fg-muted">{STATE_LABEL[s.state]} · reasoning {pct(s.reasoning_score)}</span>
                      </Link>
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
