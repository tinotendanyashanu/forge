import { Info, Lock } from "lucide-react";

import type { DesignChallengeDetail } from "@/lib/types";

import { CRITERION_LABEL, LEVEL_LABEL } from "./components";

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-medium text-fg-subtle">{title}</h3>
      <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] leading-relaxed text-fg marker:text-fg-subtle">
        {items.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </section>
  );
}

/** Challenge brief. Server-safe: renders text only. */
export function BriefPanel({ challenge: c, outdated = false, compact = false }: { challenge: DesignChallengeDetail; outdated?: boolean; compact?: boolean }) {
  return (
    <div className="flex flex-col gap-5 p-4">
      {!compact ? (
        <header>
          <p className="text-xs text-fg-subtle">
            {LEVEL_LABEL[c.level]} · version {c.version} · rubric {c.rubric_version}
          </p>
          <h2 className="mt-1 text-base font-semibold text-fg">{c.title}</h2>
        </header>
      ) : null}
      {outdated ? (
        <p className="flex gap-2 rounded-lg border border-line bg-surface-elevated p-3 text-xs text-fg-muted">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          This project uses an earlier version of the challenge. Reviews grade against the version shown here.
        </p>
      ) : null}
      <p className="text-[13px] leading-relaxed text-fg">{c.business_context}</p>
      <List title="Functional requirements" items={c.functional} />
      <List title="Non-functional requirements" items={c.non_functional} />
      <section>
        <List title="Traffic and scale assumptions" items={c.scale} />
        <p className="mt-1.5 text-[11px] text-fg-subtle">All figures are hypothetical, for design reasoning only.</p>
      </section>
      <List title="Reliability targets" items={c.reliability} />
      <List title="Security requirements" items={c.security} />
      <List title="Constraints" items={c.constraints} />
      {c.revealed && c.reviewer_notes ? (
        <section className="rounded-lg border border-line p-3">
          <h3 className="mb-2 text-xs font-medium text-fg">Reviewer notes (unlocked after your evaluation)</h3>
          <div className="flex flex-col gap-3">
            <List title="Expected concepts" items={c.reviewer_notes.expected_concepts} />
            <List title="Common mistakes" items={c.reviewer_notes.common_mistakes} />
            <List title="Follow-up scenarios" items={c.reviewer_notes.follow_ups} />
            <List
              title="Rubric focus"
              items={Object.entries(c.reviewer_notes.rubric_focus).map(([k, v]) => `${CRITERION_LABEL[k] ?? k}: ${v}`)}
            />
          </div>
        </section>
      ) : (
        <p className="flex gap-2 text-xs text-fg-subtle">
          <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          Reviewer notes and common mistakes unlock after your first completed evaluation.
        </p>
      )}
    </div>
  );
}
