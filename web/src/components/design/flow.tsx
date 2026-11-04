"use client";

import {
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { memo } from "react";

import { cn } from "@/lib/cn";
import type { GraphDocument, Protocol } from "@/lib/types";

import { COMPONENTS, PROTOCOL_LABEL } from "./components";

export interface ComponentData extends Record<string, unknown> {
  kind: string;
  name: string;
  description: string;
  properties: Record<string, string | number | boolean>;
  capacity: string | null;
  reliability: string | null;
  highlighted?: boolean;
}
export interface EdgeData extends Record<string, unknown> {
  protocol: Protocol;
  label: string;
}
export type FlowNode = Node<ComponentData, "component">;
export type FlowEdge = Edge<EdgeData>;

const HANDLES = [
  { pos: Position.Top, id: "t" },
  { pos: Position.Right, id: "r" },
  { pos: Position.Bottom, id: "b" },
  { pos: Position.Left, id: "l" },
];

function ComponentNodeView({ data, selected }: NodeProps<FlowNode>) {
  const meta = COMPONENTS[data.kind];
  const Icon = meta?.icon;
  return (
    <div
      className={cn(
        "flex w-[184px] items-center gap-2.5 rounded-lg border bg-surface px-3 py-2.5 shadow-[0_1px_0_rgba(0,0,0,0.4)] transition-colors",
        selected ? "border-fg" : "border-line hover:border-neutral-500",
        data.highlighted && !selected && "border-neutral-400 bg-surface-elevated",
      )}
    >
      {HANDLES.map((h) => (
        <Handle key={h.id} id={h.id} type="source" position={h.pos} />
      ))}
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-line-subtle bg-surface-elevated text-fg-muted">
        {Icon ? <Icon className="size-4" aria-hidden="true" /> : null}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium text-fg">{data.name}</span>
        <span className="block truncate text-[11px] text-fg-subtle">{meta?.label ?? data.kind}</span>
      </span>
    </div>
  );
}

export const nodeTypes = { component: memo(ComponentNodeView) };

export function edgeView(id: string, source: string, target: string, data: EdgeData, sourceHandle?: string | null, targetHandle?: string | null): FlowEdge {
  return {
    id,
    source,
    target,
    sourceHandle: sourceHandle ?? undefined,
    targetHandle: targetHandle ?? undefined,
    data,
    label: data.label || PROTOCOL_LABEL[data.protocol],
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#a3a3a3" },
    style: data.protocol === "event" ? { strokeDasharray: "5 4" } : undefined,
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 4,
    ariaLabel: `${data.label || PROTOCOL_LABEL[data.protocol]} connection`,
  };
}

export function toFlow(g: GraphDocument): { nodes: FlowNode[]; edges: FlowEdge[] } {
  return {
    nodes: g.nodes.map((n) => ({
      id: n.id,
      type: "component",
      position: n.position,
      ariaLabel: `${n.name}, ${COMPONENTS[n.type]?.label ?? n.type}`,
      data: {
        kind: n.type,
        name: n.name,
        description: n.description ?? "",
        properties: n.properties ?? {},
        capacity: n.capacity ?? null,
        reliability: n.reliability ?? null,
      },
    })),
    edges: g.edges.map((e) => edgeView(e.id, e.source, e.target, { protocol: e.protocol, label: e.label ?? "" })),
  };
}

export function toGraph(nodes: FlowNode[], edges: FlowEdge[]): GraphDocument {
  return {
    version: 1,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data.kind,
      name: n.data.name,
      description: n.data.description,
      properties: n.data.properties,
      capacity: n.data.capacity || null,
      reliability: n.data.reliability || null,
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      protocol: e.data?.protocol ?? "http",
      label: e.data?.label ?? "",
    })),
  };
}
