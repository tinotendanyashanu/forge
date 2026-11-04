import { Check, SearchX } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { DifficultyBadge } from "@/components/tracks/difficulty-badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getChallenges, getCodeSubmissions } from "@/lib/api";
import { cn } from "@/lib/cn";
import { difficultyLabel } from "@/lib/format";
import { DIFFICULTIES } from "@/lib/types";

export const metadata: Metadata = { title: "Challenges" };

const AREAS: Record<string, string> = {
  foundations: "Foundations",
  algorithms: "Algorithms",
  "python-fastapi": "Python & FastAPI",
  "javascript-typescript": "JavaScript & TypeScript",
  react: "React",
  sql: "SQL & transactions",
  "api-design": "API design",
  auth: "Auth",
  concurrency: "Concurrency",
  "testing-debugging": "Testing & debugging",
  performance: "Performance",
  security: "Security",
  production: "Production",
};
const LANGS = ["python", "javascript", "typescript"];

type Params = PageProps<"/lab/challenges">["searchParams"];

export default function ChallengesPage({ searchParams }: PageProps<"/lab/challenges">) {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Coding lab"
        title="Challenges"
        description="Each challenge is hand-written with public examples and hidden tests, and its reference solution is verified in the sandbox."
      />
      <Suspense fallback={<Skeleton className="h-20 w-full rounded-xl" />}>
        <Filters searchParams={searchParams} />
      </Suspense>
      <Suspense
        fallback={
          <LoadingRegion label="Loading challenges" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-36 rounded-xl" />)}
          </LoadingRegion>
        }
      >
        <List searchParams={searchParams} />
      </Suspense>
    </PageContainer>
  );
}

function href(current: Record<string, string>, key: string, value: string | null) {
  const next = new URLSearchParams(current);
  if (value === null || current[key] === value) next.delete(key);
  else next.set(key, value);
  const q = next.toString();
  return q ? `/lab/challenges?${q}` : "/lab/challenges";
}

async function pick(searchParams: Params): Promise<Record<string, string>> {
  const p = await searchParams;
  return Object.fromEntries(
    ["area", "difficulty", "language", "skill"].flatMap((k) => (typeof p[k] === "string" ? [[k, p[k] as string]] : [])),
  );
}

function Chip({ active, to, children }: { active: boolean; to: string; children: React.ReactNode }) {
  return (
    <Link
      href={to}
      aria-current={active ? "true" : undefined}
      className={cn(
        "rounded-lg border px-2.5 py-1 text-[13px] transition-colors",
        active ? "border-fg bg-fg text-canvas" : "border-line text-fg-muted hover:text-fg",
      )}
    >
      {children}
    </Link>
  );
}

async function Filters({ searchParams }: { searchParams: Params }) {
  const current = await pick(searchParams);
  return (
    <nav aria-label="Filters" className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {Object.entries(AREAS).map(([k, label]) => (
          <Chip key={k} active={current.area === k} to={href(current, "area", k)}>{label}</Chip>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {DIFFICULTIES.map((d) => (
          <Chip key={d} active={current.difficulty === d} to={href(current, "difficulty", d)}>{difficultyLabel[d]}</Chip>
        ))}
        <span className="mx-1 w-px bg-line" aria-hidden="true" />
        {LANGS.map((l) => (
          <Chip key={l} active={current.language === l} to={href(current, "language", l)}>{l}</Chip>
        ))}
        {Object.keys(current).length ? (
          <Link href="/lab/challenges" className="px-2 py-1 text-[13px] text-fg-subtle underline underline-offset-4">Clear</Link>
        ) : null}
      </div>
    </nav>
  );
}

async function List({ searchParams }: { searchParams: Params }) {
  const filters = await pick(searchParams);
  const [challenges, subs] = await Promise.all([getChallenges(filters), getCodeSubmissions(undefined, 100)]);
  const solved = new Set((subs ?? []).filter((s) => s.all_passed && s.verified).map((s) => s.challenge_slug));
  const tried = new Set((subs ?? []).map((s) => s.challenge_slug));
  if (challenges.length === 0) {
    return <EmptyState icon={SearchX} title="No challenges match" description="Try removing a filter." />;
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {challenges.map((c) => (
        <li key={c.slug}>
          <Link href={`/lab/challenges/${c.slug}`} className="group block h-full rounded-xl">
            <Card className="flex h-full flex-col p-5 transition-colors group-hover:border-neutral-600 group-hover:bg-surface-raised">
              <div className="flex items-start justify-between gap-3">
                <p className="text-xs text-fg-subtle">{AREAS[c.area] ?? c.area} · {c.skill.title}</p>
                {solved.has(c.slug) ? (
                  <span className="inline-flex items-center gap-1 text-xs text-fg"><Check className="size-3.5" aria-hidden="true" />Solved</span>
                ) : tried.has(c.slug) ? (
                  <span className="text-xs text-fg-subtle">Attempted</span>
                ) : null}
              </div>
              <h2 className="mt-2 text-[15px] font-medium text-fg">{c.title}</h2>
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-4 text-xs text-fg-subtle">
                <DifficultyBadge level={c.difficulty} />
                <span className="font-mono">{c.languages.join(" · ")}</span>
                <span className="tabular-nums">{c.public_tests} public · {c.hidden_tests} hidden</span>
              </div>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
