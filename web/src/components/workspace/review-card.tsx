import { CircleAlert, CircleHelp, FlaskConical, Lightbulb, Scale, ShieldAlert, ThumbsUp } from "lucide-react";

import { cn } from "@/lib/cn";
import type { EngReview, ReviewFinding } from "@/lib/workspace-types";

import { Inline } from "./markdown";

const GROUPS: { key: ReviewFinding["category"]; title: string; note: string; icon: typeof CircleAlert }[] = [
  { key: "proven_failure", title: "Proven failures", note: "Backed by a failing test.", icon: FlaskConical },
  { key: "potential_concern", title: "Potential concerns", note: "Plausible risks no test has demonstrated.", icon: CircleAlert },
  { key: "suggestion", title: "Suggestions", note: "Subjective improvements.", icon: Lightbulb },
];

const RATING: Record<string, string> = { meets: "Meets", partial: "Partial", missing: "Missing", not_assessable: "Not assessable" };

export function ReviewCard({ review, onJump }: { review: EngReview; onJump?: (path: string, line: number | null) => void }) {
  if (review.status === "ungraded" || !review.review) {
    return (
      <div role="status" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-fg-muted">
        The AI review couldn&apos;t be completed ({review.error_code?.replaceAll("_", " ") ?? "unknown error"}). Nothing was
        scored. You can retry it.
      </div>
    );
  }
  const r = review.review;
  return (
    <article className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-4" aria-label={`${r.mode_title} review`}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium text-fg">{r.mode_title}</p>
          <p className="text-[11px] text-fg-subtle">
            {review.model} · rubric {review.rubric_version} · confidence {Math.round(r.confidence * 100)}%
          </p>
        </div>
        <span className={cn("rounded-md px-2 py-0.5 text-xs", r.recommendation === "approve" ? "bg-fg text-canvas" : "border border-line text-fg")}>
          {r.recommendation === "approve" ? "Recommends approval" : r.recommendation === "request_changes" ? "Requests changes" : "Comments"}
        </span>
      </header>
      <p className="rounded-lg border border-line-subtle bg-canvas px-3 py-2 text-[12px] text-fg-muted">{r.grounding}</p>
      {r.recommendation_overridden ? (
        <p className="text-[12px] text-fg-muted">The model recommended approval while tests were failing; FORGE changed it to &quot;requests changes&quot;.</p>
      ) : null}
      {r.injection_suspected ? (
        <p className="flex items-center gap-2 text-[12px] text-fg"><ShieldAlert className="size-4" aria-hidden="true" />Text in the submission looked like instructions to the reviewer. It was treated as data.</p>
      ) : null}
      {review.leak_blocked ? <p className="text-[12px] text-fg-muted">Parts of this review were too close to the reference solution and were removed.</p> : null}
      <p className="text-sm leading-relaxed text-fg"><Inline text={r.summary} /></p>

      {GROUPS.map((g) => {
        const items = r.findings.filter((f) => f.category === g.key);
        if (!items.length) return null;
        const Icon = g.icon;
        return (
          <section key={g.key} aria-label={g.title}>
            <h4 className="flex items-center gap-2 text-[13px] font-medium text-fg"><Icon className="size-4" aria-hidden="true" />{g.title}</h4>
            <p className="mb-2 text-[11px] text-fg-subtle">{g.note}</p>
            <ul className="flex flex-col gap-2">
              {items.map((f, i) => (
                <li key={i} className="rounded-lg border border-line-subtle bg-canvas px-3 py-2 text-[13px]">
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-fg-subtle">
                    <span className="uppercase tracking-wide">{f.severity}</span>
                    <span>{f.dimension}</span>
                    {f.path ? (
                      onJump ? (
                        <button type="button" onClick={() => onJump(f.path!, f.line)} className="font-mono underline-offset-2 hover:text-fg hover:underline">
                          {f.path}{f.line ? `:${f.line}` : ""}
                        </button>
                      ) : <span className="font-mono">{f.path}{f.line ? `:${f.line}` : ""}</span>
                    ) : null}
                  </div>
                  <p className="text-fg"><Inline text={f.message} /></p>
                  {f.suggestion ? <p className="mt-1 text-fg-muted"><Inline text={f.suggestion} /></p> : null}
                  {f.test_name ? <p className="mt-1 text-[11px] text-fg-subtle">Failing test: {f.test_name}</p> : null}
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {r.requested_changes.length ? (
        <List title="Requested changes" icon={CircleAlert} items={r.requested_changes} />
      ) : null}
      {r.questions.length ? <List title="Questions for you" icon={CircleHelp} items={r.questions} /> : null}
      {r.tradeoffs.length ? <List title="Trade-offs" icon={Scale} items={r.tradeoffs} /> : null}
      {r.strengths.length ? <List title="Strengths" icon={ThumbsUp} items={r.strengths} /> : null}
      {r.rubric.length ? (
        <section aria-label="Rubric">
          <h4 className="mb-2 text-[13px] font-medium text-fg">Rubric</h4>
          <ul className="divide-y divide-line-subtle rounded-lg border border-line-subtle">
            {r.rubric.map((x) => (
              <li key={x.criterion} className="flex gap-3 px-3 py-2 text-[12.5px]">
                <span className="w-24 shrink-0 text-fg">{RATING[x.rating]}</span>
                <span className="text-fg-muted"><span className="text-fg">{x.text}</span> {x.note}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}

function List({ title, icon: Icon, items }: { title: string; icon: typeof CircleAlert; items: string[] }) {
  return (
    <section aria-label={title}>
      <h4 className="mb-1.5 flex items-center gap-2 text-[13px] font-medium text-fg"><Icon className="size-4" aria-hidden="true" />{title}</h4>
      <ul className="ml-6 list-disc space-y-1 text-[13px] text-fg-muted">
        {items.map((x, i) => <li key={i}><Inline text={x} /></li>)}
      </ul>
    </section>
  );
}
