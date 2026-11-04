import { cn } from "@/lib/cn";
import type { MasteryState } from "@/lib/types";

export const STATE_LABEL: Record<MasteryState, string> = {
  not_started: "Not started",
  insufficient_evidence: "Not enough evidence",
  learning: "Learning",
  developing: "Developing",
  proficient: "Proficient",
  mastered: "Mastered",
};

export const STATE_RANK: Record<MasteryState, number> = {
  not_started: 0,
  insufficient_evidence: 1,
  learning: 2,
  developing: 3,
  proficient: 4,
  mastered: 5,
};

/** Monochrome state marker: fill encodes progress; text always names it. */
export function StateDot({ state, className }: { state: MasteryState; className?: string }) {
  const rank = STATE_RANK[state];
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-2.5 shrink-0 items-center justify-center rounded-full border",
        rank === 0 && "border-dashed border-fg-subtle",
        rank > 0 && rank < 3 && "border-fg-muted",
        rank === 3 && "border-fg",
        rank >= 4 && "border-fg bg-fg",
        rank === 5 && "ring-2 ring-fg/30",
        className,
      )}
    >
      {rank === 3 ? <span className="size-1 rounded-full bg-fg" /> : null}
    </span>
  );
}

export function StateBadge({ state }: { state: MasteryState }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-0.5 text-xs text-fg-muted">
      <StateDot state={state} />
      {STATE_LABEL[state]}
    </span>
  );
}

export function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}
