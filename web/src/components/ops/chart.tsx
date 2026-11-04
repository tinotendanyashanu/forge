"use client";

import { useId, useState } from "react";

import { cn } from "@/lib/cn";

import { fmtValue } from "./format";

/**
 * Deterministic time-series chart. Values come from the scenario model via the
 * API; this component never interpolates or invents points.
 */
export function TimeChart({
  title,
  unit,
  points,
  markers = [],
  height = 120,
  className,
}: {
  title: string;
  unit: string;
  points: [number, number | null][];
  markers?: { minute: number; label: string }[];
  height?: number;
  className?: string;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const H = height;
  const pad = { l: 4, r: 4, t: 8, b: 16 };
  const vals = points.map(([, v]) => v).filter((v): v is number => v !== null);
  const max = Math.max(1, ...vals) * 1.12;
  const x0 = points[0]?.[0] ?? 0;
  const x1 = points.at(-1)?.[0] ?? 1;
  const sx = (m: number) => pad.l + ((m - x0) / Math.max(1, x1 - x0)) * (W - pad.l - pad.r);
  const sy = (v: number) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  let d = "";
  let pen = false;
  for (const [m, v] of points) {
    if (v === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${sx(m).toFixed(1)},${sy(v).toFixed(1)}`;
    pen = true;
  }
  const last = [...points].reverse().find(([, v]) => v !== null);
  const hovered = hover === null ? null : points[hover];
  const shown = hovered ?? last ?? null;

  return (
    <figure className={cn("rounded-lg border border-line bg-surface p-3", className)} aria-labelledby={`${id}-t`}>
      <figcaption className="mb-1 flex items-baseline justify-between gap-2">
        <span id={`${id}-t`} className="truncate text-xs text-fg-muted">{title}</span>
        <span className="font-mono text-sm text-fg tabular-nums">
          {shown ? fmtValue(shown[1], unit) : "—"}
          {hovered ? <span className="ml-1 text-[11px] text-fg-subtle">at {hovered[0] >= 0 ? "+" : ""}{hovered[0]}m</span> : null}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full touch-none"
        role="img"
        aria-label={`${title}: ${vals.length ? `min ${fmtValue(Math.min(...vals), unit)}, max ${fmtValue(Math.max(...vals), unit)}, now ${last ? fmtValue(last[1], unit) : "no data"}` : "no data"}`}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const f = (e.clientX - r.left) / r.width;
          setHover(Math.max(0, Math.min(points.length - 1, Math.round(f * (points.length - 1)))));
        }}
        onPointerLeave={() => setHover(null)}
      >
        <line x1={pad.l} x2={W - pad.r} y1={sy(0)} y2={sy(0)} stroke="#303030" strokeWidth="1" />
        <line x1={pad.l} x2={W - pad.r} y1={sy(max / 1.12)} y2={sy(max / 1.12)} stroke="#242424" strokeDasharray="3 4" strokeWidth="1" />
        {markers.filter((m) => m.minute >= x0 && m.minute <= x1).map((m) => (
          <g key={`${m.minute}-${m.label}`}>
            <line x1={sx(m.minute)} x2={sx(m.minute)} y1={pad.t} y2={H - pad.b} stroke="#737373" strokeDasharray="2 3" strokeWidth="1" />
          </g>
        ))}
        <path d={d} fill="none" stroke="#fafafa" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
        {hovered && hovered[1] !== null ? <circle cx={sx(hovered[0])} cy={sy(hovered[1])} r="3" fill="#fafafa" /> : null}
        <text x={pad.l} y={H - 3} fill="#737373" fontSize="10" fontFamily="var(--font-mono)">{x0}m</text>
        <text x={W - pad.r} y={H - 3} fill="#737373" fontSize="10" textAnchor="end" fontFamily="var(--font-mono)">now</text>
        <text x={W - pad.r} y={pad.t + 9} fill="#737373" fontSize="10" textAnchor="end" fontFamily="var(--font-mono)">{fmtValue(Math.round((max / 1.12) * 10) / 10, unit)}</text>
      </svg>
    </figure>
  );
}
