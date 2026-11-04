import { ChevronLeft, Clock, Cpu, EyeOff } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { ExecutionBanner } from "@/components/coding/execution-banner";
import { Workspace } from "@/components/coding/workspace";
import { DifficultyBadge } from "@/components/tracks/difficulty-badge";
import { InlineText, CodeBlock } from "@/components/ui/rich-text";
import { MessageText } from "@/components/ui/message-text";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getChallenge, getChallengeState, getExecutionStatus } from "@/lib/api";

export default function ChallengePage({ params }: PageProps<"/lab/challenges/[slug]">) {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <Link href="/lab/challenges" className="mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        All challenges
      </Link>
      <Suspense
        fallback={
          <LoadingRegion label="Loading challenge" className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Skeleton className="h-[520px] rounded-xl" />
            <Skeleton className="h-[520px] rounded-xl" />
          </LoadingRegion>
        }
      >
        <Challenge params={params} />
      </Suspense>
    </div>
  );
}

async function Challenge({ params }: { params: PageProps<"/lab/challenges/[slug]">["params"] }) {
  const { slug } = await params;
  const [challenge, state, status] = await Promise.all([
    getChallenge(slug),
    getChallengeState(slug),
    getExecutionStatus().catch(() => null),
  ]);
  if (!challenge) notFound();

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <article className="flex flex-col gap-6 lg:sticky lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:overflow-y-auto lg:pr-2">
        <header>
          <p className="text-xs text-fg-subtle">{challenge.skill.title} · version {challenge.version}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{challenge.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-fg-subtle">
            <DifficultyBadge level={challenge.difficulty} />
            <span className="inline-flex items-center gap-1"><Clock className="size-3.5" aria-hidden="true" />{challenge.time_limit_ms} ms per test</span>
            <span className="inline-flex items-center gap-1"><Cpu className="size-3.5" aria-hidden="true" />{challenge.memory_limit_mb} MB</span>
          </div>
        </header>
        <div className="text-[15px] leading-relaxed text-fg">
          <MessageText text={reflow(challenge.description)} />
        </div>
        <section aria-labelledby="constraints-heading">
          <h2 id="constraints-heading" className="mb-2 text-[13px] font-medium text-fg-subtle">Constraints</h2>
          <ul className="flex flex-col gap-1 text-sm text-fg-muted">
            {challenge.constraints.map((c) => <li key={c} className="flex gap-2"><span aria-hidden="true">–</span><InlineText text={c} /></li>)}
          </ul>
        </section>
        <section aria-labelledby="examples-heading">
          <h2 id="examples-heading" className="mb-2 text-[13px] font-medium text-fg-subtle">Examples (public tests)</h2>
          <ol className="flex flex-col gap-2">
            {challenge.examples.map((e) => (
              <li key={e.name}>
                <p className="mb-1 text-xs text-fg-muted">{e.name}</p>
                <CodeBlock
                  code={`${e.call.replace(/^driver:/, "")}(${e.args.map((a) => JSON.stringify(a)).join(", ")})\n→ ${e.expected.raises ? `raises ${e.expected.raises}` : JSON.stringify(e.expected.value)}`}
                />
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="hidden-heading">
          <h2 id="hidden-heading" className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-fg-subtle">
            <EyeOff className="size-3.5" aria-hidden="true" />
            Hidden tests ({challenge.hidden_test_names.length})
          </h2>
          <ul className="flex flex-col gap-1 text-sm text-fg-muted">
            {challenge.hidden_test_names.map((n) => <li key={n}>– {n}</li>)}
          </ul>
        </section>
        <section aria-labelledby="rubric-heading">
          <h2 id="rubric-heading" className="mb-2 text-[13px] font-medium text-fg-subtle">What a strong solution does</h2>
          <ul className="flex flex-col gap-1 text-sm text-fg-muted">
            {challenge.rubric.map((r) => <li key={r} className="flex gap-2"><span aria-hidden="true">–</span><InlineText text={r} /></li>)}
          </ul>
        </section>
      </article>
      <div className="flex min-w-0 flex-col gap-4">
        <ExecutionBanner status={status} compact />
        <Workspace challenge={challenge} initial={state} status={status} />
      </div>
    </div>
  );
}

/** Joins hard-wrapped lines inside paragraphs; keeps lists, code fences and blank lines. */
function reflow(text: string): string {
  const out: string[] = [];
  let inFence = false;
  for (const line of text.split("\n")) {
    const fence = line.trimStart().startsWith("```");
    const structural = fence || inFence || line.trim() === "" || /^\s*([*-]|\d+\.)\s/.test(line);
    const prev = out[out.length - 1];
    if (!structural && prev !== undefined && prev.trim() !== "" && !/^\s*([*-]|\d+\.)\s/.test(prev) && !prev.trimStart().startsWith("```")) {
      out[out.length - 1] = `${prev} ${line.trim()}`;
    } else {
      out.push(line);
    }
    if (fence) inFence = !inFence;
  }
  return out.join("\n");
}
