"use client";

import { CircleAlert, HelpCircle, Lightbulb, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";

import { requestCodeReview } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { CodeReview } from "@/lib/types";

const SEVERITY_ORDER = { major: 0, minor: 1, info: 2 } as const;

export function ReviewPanel({ submissionId, initial }: { submissionId: string; initial: CodeReview | null }) {
  const [review, setReview] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function request() {
    setBusy(true);
    setError(null);
    const res = await requestCodeReview(submissionId);
    setBusy(false);
    if (res.ok) setReview(res.data.review);
    else setError(res.error);
  }

  if (!review || review.status === "pending") {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-line bg-surface p-5">
        <p className="text-sm text-fg-muted">
          An AI review comments on readability, maintainability, security, efficiency and trade-offs,
          grounded in your test results. It&apos;s advisory: tests decide correctness, and reviews never
          count toward mastery.
        </p>
        <Button size="sm" onClick={request} disabled={busy || review?.status === "pending"}>
          {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
          {busy ? "Reviewing…" : "Request AI review"}
        </Button>
        {error ? <p role="alert" className="text-sm text-fg">{error}</p> : null}
      </div>
    );
  }

  if (review.status === "ungraded" || !review.review) {
    const reason = review.error_code === "provider_not_configured"
      ? "No AI provider is configured on this server."
      : "The AI provider failed or returned an invalid review.";
    return (
      <div role="status" className="flex flex-col items-start gap-3 rounded-xl border border-line bg-surface p-5 text-sm">
        <p className="flex items-start gap-2 text-fg">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          No review available. {reason}
        </p>
        <Button size="sm" variant="secondary" onClick={request} disabled={busy}>
          {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
          Retry review
        </Button>
      </div>
    );
  }

  const r = review.review;
  const findings = [...r.findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  return (
    <section aria-label="AI code review" className="overflow-hidden rounded-xl border border-line bg-surface">
      <p className="border-b border-line-subtle bg-surface-raised px-5 py-2.5 text-xs text-fg-muted">{r.grounding}</p>
      <div className="px-5 py-4">
        <p className="text-sm leading-relaxed text-fg">{r.summary}</p>
      </div>
      {findings.length ? (
        <ul className="divide-y divide-line-subtle border-t border-line-subtle">
          {findings.map((f, i) => (
            <li key={i} className="flex gap-3 px-5 py-3 text-sm">
              <span
                className={cn(
                  "mt-0.5 h-5 shrink-0 rounded-md border px-1.5 text-[11px] leading-[18px] capitalize",
                  f.severity === "major" ? "border-fg text-fg" : "border-line text-fg-subtle",
                )}
              >
                {f.severity}
              </span>
              <div className="min-w-0">
                <p className="text-xs text-fg-subtle capitalize">
                  {f.dimension}
                  {f.line ? <span className="font-mono"> · line {f.line}</span> : null}
                </p>
                <p className="mt-0.5 text-fg">{f.message}</p>
                {f.suggestion ? <p className="mt-1 text-fg-muted">{f.suggestion}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {r.follow_up_questions.length ? (
        <div className="border-t border-line-subtle px-5 py-4">
          <h3 className="mb-2 text-[13px] font-medium text-fg-subtle">Think about</h3>
          <ul className="flex flex-col gap-1.5 text-sm text-fg">
            {r.follow_up_questions.map((q) => (
              <li key={q} className="flex gap-2"><HelpCircle className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-hidden="true" />{q}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {r.hints.length ? (
        <div className="border-t border-line-subtle px-5 py-4">
          <h3 className="mb-2 text-[13px] font-medium text-fg-subtle">Hints</h3>
          <ul className="flex flex-col gap-1.5 text-sm text-fg-muted">
            {r.hints.map((h) => (
              <li key={h} className="flex gap-2"><Lightbulb className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{h}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="border-t border-line-subtle px-5 py-2.5 text-xs text-fg-subtle">
        {review.provider} · {review.model}
        {review.leak_blocked ? " · parts too close to the reference solution were removed" : ""}
        {r.injection_suspected ? " · instructions embedded in your code were ignored" : ""}
      </p>
    </section>
  );
}
