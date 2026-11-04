"use client";

import { Background, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CircleAlert, CircleCheck, CircleX } from "lucide-react";
import { memo, useMemo } from "react";

import { COMPONENTS } from "@/components/design/components";
import { cn } from "@/lib/cn";
import type { Health, OpsService } from "@/lib/types";

type SvcData = { name: string; kind: string; health: Health };
type SvcNode = Node<SvcData, "svc">;

const HEALTH = {
  healthy: { icon: CircleCheck, label: "Healthy" },
  degraded: { icon: CircleAlert, label: "Degraded" },
  down: { icon: CircleX, label: "Down" },
} as const;

function SvcView({ data }: NodeProps<SvcNode>) {
  const Icon = COMPONENTS[data.kind]?.icon;
  const H = HEALTH[data.health];
  return (
    <div
      className={cn(
        "flex w-[170px] items-center gap-2 rounded-lg border bg-surface px-2.5 py-2",
        data.health === "healthy" && "border-line",
        data.health === "degraded" && "border-dashed border-neutral-400",
        data.health === "down" && "border-2 border-fg bg-surface-elevated",
      )}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
      {Icon ? <Icon className="size-4 shrink-0 text-fg-muted" aria-hidden="true" /> : null}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-fg">{data.name}</span>
        <span className="flex items-center gap-1 text-[11px] text-fg-muted">
          <H.icon className="size-3" aria-hidden="true" />
          {H.label}
        </span>
      </span>
    </div>
  );
}

const nodeTypes = { svc: memo(SvcView) };

/** Read-only dependency map, laid out in layers from callers to dependencies. */
export function ServiceMap({ services, health }: { services: OpsService[]; health: Record<string, Health> }) {
  const { nodes, edges } = useMemo(() => {
    const depth = new Map<string, number>();
    const visit = (id: string, d: number, seen: Set<string>) => {
      if (seen.has(id)) return;
      depth.set(id, Math.max(depth.get(id) ?? 0, d));
      const s = services.find((x) => x.id === id);
      s?.depends_on.forEach((dep) => visit(dep, d + 1, new Set([...seen, id])));
    };
    const targets = new Set(services.flatMap((s) => s.depends_on));
    services.filter((s) => !targets.has(s.id)).forEach((s) => visit(s.id, 0, new Set()));
    services.forEach((s) => depth.has(s.id) || depth.set(s.id, 0));
    const rows = new Map<number, string[]>();
    services.forEach((s) => rows.set(depth.get(s.id)!, [...(rows.get(depth.get(s.id)!) ?? []), s.id]));
    const nodes: SvcNode[] = services.map((s) => {
      const row = rows.get(depth.get(s.id)!)!;
      const i = row.indexOf(s.id);
      return {
        id: s.id,
        type: "svc",
        position: { x: (i - (row.length - 1) / 2) * 200, y: depth.get(s.id)! * 90 },
        data: { name: s.name, kind: s.kind, health: health[s.id] ?? "healthy" },
        ariaLabel: `${s.name}: ${health[s.id] ?? "healthy"}`,
      };
    });
    const edges: Edge[] = services.flatMap((s) =>
      s.depends_on.map((d) => ({
        id: `${s.id}-${d}`,
        source: s.id,
        target: d,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#737373" },
        style: { stroke: health[d] !== "healthy" ? "#a3a3a3" : "#525252", strokeDasharray: health[d] === "down" ? "4 3" : undefined },
      })),
    );
    return { nodes, edges };
  }, [services, health]);

  return (
    <div className="h-72 rounded-lg border border-line bg-canvas" aria-label="Service dependency map" role="group">
      <ReactFlowProvider>
        <ReactFlow
          className="forge-flow"
          colorMode="dark"
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          panOnScroll={false}
          zoomOnScroll={false}
        >
          <Background gap={20} size={1} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
