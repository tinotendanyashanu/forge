"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { difficultyLabel } from "@/lib/format";
import type { CurriculumSkill, SkillMastery } from "@/lib/types";

import { STATE_LABEL, STATE_RANK } from "./state";

const NODE_W = 184;
const NODE_H = 60;
const COL_GAP = 72;
const ROW_GAP = 20;
const PAD = 16;

function ancestorsOf(slug: string, bySlug: Map<string, CurriculumSkill>): Set<string> {
  const seen = new Set<string>();
  const stack = [...(bySlug.get(slug)?.prerequisites ?? [])];
  while (stack.length) {
    const s = stack.pop()!;
    if (!seen.has(s)) {
      seen.add(s);
      stack.push(...(bySlug.get(s)?.prerequisites ?? []));
    }
  }
  return seen;
}

/**
 * Layered prerequisite graph (left → right). Every node is a link; focusing or
 * hovering one highlights the prerequisites it depends on.
 */
export function SkillGraph({
  skills,
  mastery,
}: {
  skills: CurriculumSkill[];
  mastery: Record<string, SkillMastery>;
}) {
  const [active, setActive] = useState<string | null>(null);
  const bySlug = useMemo(() => new Map(skills.map((s) => [s.slug, s])), [skills]);

  const layout = useMemo(() => {
    const columns = new Map<number, CurriculumSkill[]>();
    for (const s of [...skills].sort((a, b) => a.position - b.position)) {
      columns.set(s.depth, [...(columns.get(s.depth) ?? []), s]);
    }
    const maxRows = Math.max(...[...columns.values()].map((c) => c.length));
    const height = PAD * 2 + maxRows * NODE_H + (maxRows - 1) * ROW_GAP;
    const pos = new Map<string, { x: number; y: number }>();
    for (const [depth, col] of columns) {
      const colHeight = col.length * NODE_H + (col.length - 1) * ROW_GAP;
      const top = (height - colHeight) / 2;
      col.forEach((s, i) => pos.set(s.slug, { x: PAD + depth * (NODE_W + COL_GAP), y: top + i * (NODE_H + ROW_GAP) }));
    }
    const width = PAD * 2 + columns.size * NODE_W + (columns.size - 1) * COL_GAP;
    return { pos, width, height };
  }, [skills]);

  const highlighted = active ? new Set([active, ...ancestorsOf(active, bySlug)]) : null;

  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <svg
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="group"
        aria-label="Skill prerequisite graph"
        className="block"
      >
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--color-fg-subtle)" />
          </marker>
        </defs>
        {skills.flatMap((s) =>
          s.prerequisites.map((p) => {
            const from = layout.pos.get(p)!;
            const to = layout.pos.get(s.slug)!;
            const x1 = from.x + NODE_W;
            const y1 = from.y + NODE_H / 2;
            const x2 = to.x - 4;
            const y2 = to.y + NODE_H / 2;
            const mid = (x1 + x2) / 2;
            const on = highlighted ? highlighted.has(s.slug) && highlighted.has(p) : false;
            return (
              <path
                key={`${p}->${s.slug}`}
                d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
                fill="none"
                stroke={on ? "var(--color-fg)" : "var(--color-line)"}
                strokeWidth={on ? 1.75 : 1.25}
                markerEnd="url(#arrow)"
                className="transition-[stroke] duration-150"
              />
            );
          }),
        )}
        {skills.map((s) => {
          const { x, y } = layout.pos.get(s.slug)!;
          const m = mastery[s.slug];
          const state = m?.state ?? "not_started";
          const rank = STATE_RANK[state];
          const locked = s.assessable && m ? !m.prerequisites_met && rank === 0 : false;
          const dim = highlighted && !highlighted.has(s.slug);
          const label = `${s.title}: ${s.assessable ? STATE_LABEL[state] : "no assessments yet"}${
            m?.demonstrated_level ? `, ${difficultyLabel[m.demonstrated_level]} demonstrated` : ""
          }${locked ? ", prerequisites not yet met" : ""}`;
          return (
            <Link
              key={s.slug}
              href={`/tracks/${s.slug}`}
              aria-label={label}
              onMouseEnter={() => setActive(s.slug)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(s.slug)}
              onBlur={() => setActive(null)}
              className="group outline-none"
            >
              <g className={cn("transition-opacity duration-150", dim && "opacity-35")}>
                <rect
                  x={x}
                  y={y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  fill={rank >= 4 ? "var(--color-fg)" : rank === 3 ? "var(--color-surface-hover)" : "var(--color-canvas)"}
                  stroke={rank >= 3 ? "var(--color-fg)" : "var(--color-line)"}
                  strokeWidth={rank === 5 ? 2.5 : 1}
                  strokeDasharray={!s.assessable ? "2 3" : rank === 0 ? "5 4" : undefined}
                  className="group-focus-visible:stroke-[var(--color-fg)] group-focus-visible:[stroke-width:2.5]"
                />
                <text
                  x={x + 14}
                  y={y + 25}
                  className="text-[13px] font-medium"
                  fill={rank >= 4 ? "var(--color-canvas)" : "var(--color-fg)"}
                >
                  {s.title.length > 22 ? `${s.title.slice(0, 21)}…` : s.title}
                </text>
                <text
                  x={x + 14}
                  y={y + 44}
                  className="text-[11px]"
                  fill={rank >= 4 ? "var(--color-canvas)" : "var(--color-fg-subtle)"}
                >
                  {!s.assessable
                    ? "No assessments yet"
                    : locked
                      ? "Locked"
                      : m?.demonstrated_level
                        ? `${STATE_LABEL[state]} · ${difficultyLabel[m.demonstrated_level]}`
                        : STATE_LABEL[state]}
                </text>
                {locked ? (
                  <foreignObject x={x + NODE_W - 28} y={y + 10} width={16} height={16}>
                    <Lock className="size-3.5 text-fg-subtle" aria-hidden="true" />
                  </foreignObject>
                ) : null}
              </g>
            </Link>
          );
        })}
      </svg>
    </div>
  );
}

export function GraphLegend() {
  const items: Array<[string, string]> = [
    ["border border-dashed border-line", "Not started"],
    ["border border-line bg-canvas", "Learning"],
    ["border border-fg bg-surface-hover", "Developing"],
    ["border border-fg bg-fg", "Proficient"],
    ["border-2 border-fg bg-fg", "Mastered"],
    ["border border-dotted border-line", "No assessments yet"],
  ];
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-fg-subtle" aria-label="Legend">
      {items.map(([cls, label]) => (
        <li key={label} className="flex items-center gap-2">
          <span className={cn("h-3 w-5 rounded-[4px]", cls)} aria-hidden="true" />
          {label}
        </li>
      ))}
    </ul>
  );
}
