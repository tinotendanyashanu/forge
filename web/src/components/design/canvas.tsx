"use client";

import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  MiniMap,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState, type DragEvent } from "react";

import { cn } from "@/lib/cn";

import { DRAG_MIME } from "./components";
import { nodeTypes, type FlowEdge, type FlowNode } from "./flow";

const SIZE = { w: 184, h: 54 };

/** Picks the facing sides of two nodes so edges route cleanly as nodes move. */
function route(nodes: FlowNode[], edges: FlowEdge[]): FlowEdge[] {
  const pos = new Map(nodes.map((n) => [n.id, n.position]));
  return edges.map((e) => {
    const a = pos.get(e.source);
    const b = pos.get(e.target);
    if (!a || !b) return e;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const horizontal = Math.abs(dx) / SIZE.w >= Math.abs(dy) / SIZE.h;
    const [s, t] = horizontal ? (dx >= 0 ? ["r", "l"] : ["l", "r"]) : dy >= 0 ? ["b", "t"] : ["t", "b"];
    return { ...e, sourceHandle: s, targetHandle: t };
  });
}

export function DesignCanvas({
  nodes,
  edges,
  readOnly = false,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onSelectionChange,
  onNodeDragStart,
  onDropComponent,
  className,
  minimap = true,
}: {
  nodes: FlowNode[];
  edges: FlowEdge[];
  readOnly?: boolean;
  onNodesChange?: (changes: NodeChange<FlowNode>[]) => void;
  onEdgesChange?: (changes: EdgeChange<FlowEdge>[]) => void;
  onConnect?: (c: Connection) => void;
  onSelectionChange?: (p: OnSelectionChangeParams<FlowNode, FlowEdge>) => void;
  onNodeDragStart?: () => void;
  onDropComponent?: (type: string, screen: { x: number; y: number }) => void;
  className?: string;
  minimap?: boolean;
}) {
  const routed = useMemo(() => route(nodes, edges), [nodes, edges]);
  const [connecting, setConnecting] = useState(false);

  function onDragOver(e: DragEvent) {
    if (readOnly || !e.dataTransfer.types.includes(DRAG_MIME)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }
  function onDrop(e: DragEvent) {
    const type = e.dataTransfer.getData(DRAG_MIME);
    if (readOnly || !type) return;
    e.preventDefault();
    onDropComponent?.(type, { x: e.clientX, y: e.clientY });
  }

  return (
    <ReactFlow<FlowNode, FlowEdge>
      className={cn("forge-flow", connecting && "connecting", className)}
      colorMode="dark"
      nodes={nodes}
      edges={routed}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onConnectStart={() => setConnecting(true)}
      onConnectEnd={(event, state) => {
        setConnecting(false);
        // Dropping anywhere on a node (not only on its handle) connects to it.
        if (state.isValid || !state.fromNode || !onConnect) return;
        const point = "changedTouches" in event ? event.changedTouches[0] : event;
        const el = document.elementFromPoint(point.clientX, point.clientY)?.closest<HTMLElement>(".react-flow__node");
        const target = el?.dataset.id;
        if (target && target !== state.fromNode.id) {
          onConnect({ source: state.fromNode.id, target, sourceHandle: null, targetHandle: null });
        }
      }}
      connectionRadius={36}
      onSelectionChange={onSelectionChange}
      onNodeDragStart={onNodeDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      connectionMode={ConnectionMode.Loose}
      nodesDraggable={!readOnly}
      nodesConnectable={!readOnly}
      elementsSelectable={!readOnly}
      edgesFocusable={!readOnly}
      deleteKeyCode={null}
      selectionKeyCode="Shift"
      multiSelectionKeyCode={["Meta", "Control"]}
      fitView
      fitViewOptions={{ padding: 0.25, maxZoom: 1.2 }}
      minZoom={0.2}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
      ariaLabelConfig={{
        "node.a11yDescription.default": "Press Enter or Space to select. Use arrow keys to move the selected component.",
      }}
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
      {minimap ? (
        <MiniMap pannable zoomable className="!hidden !h-24 !w-36 !rounded-lg !border !border-line 2xl:!block" style={{ width: 144, height: 96 }} ariaLabel="Diagram overview" />
      ) : null}
    </ReactFlow>
  );
}
