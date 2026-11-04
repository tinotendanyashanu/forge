"use client";

import { ArrowLeftRight, Copy, Plus, Trash2, X } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Protocol } from "@/lib/types";

import { COMPONENTS, LIMITS, PROTOCOL_LABEL, PROTOCOLS } from "./components";
import type { ComponentData, EdgeData, FlowEdge, FlowNode } from "./flow";

const field = "forge-field min-h-9 px-3 py-1.5 text-[13px]";
const labelCls = "mb-1.5 block text-xs font-medium text-fg-muted";

export function Inspector({
  nodes,
  selectedNodes,
  selectedEdges,
  onNodeChange,
  onEdgeChange,
  onConnect,
  onBeginEdit,
  onDelete,
  onDuplicate,
}: {
  nodes: FlowNode[];
  selectedNodes: FlowNode[];
  selectedEdges: FlowEdge[];
  onNodeChange: (id: string, patch: Partial<ComponentData>) => void;
  onEdgeChange: (id: string, patch: Partial<EdgeData> & { reverse?: boolean }) => void;
  onConnect: (source: string, target: string, protocol: Protocol) => void;
  onBeginEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const total = selectedNodes.length + selectedEdges.length;
  if (total === 0) return null;
  return (
    <div
      aria-label="Inspector"
      role="region"
      className="max-h-[45%] shrink-0 overflow-y-auto border-t border-line-subtle bg-surface px-4 py-3"
    >
      {total > 1 ? (
        <div className="flex items-center justify-between gap-3 text-sm text-fg-muted">
          <span>{total} items selected</span>
          <span className="flex gap-2">
            {selectedNodes.length ? (
              <Button size="sm" variant="secondary" onClick={onDuplicate}><Copy aria-hidden="true" />Duplicate</Button>
            ) : null}
            <Button size="sm" variant="secondary" onClick={onDelete}><Trash2 aria-hidden="true" />Delete</Button>
          </span>
        </div>
      ) : selectedNodes[0] ? (
        <NodeForm
          key={selectedNodes[0].id}
          node={selectedNodes[0]}
          nodes={nodes}
          onChange={(p) => onNodeChange(selectedNodes[0].id, p)}
          onConnect={onConnect}
          onBeginEdit={onBeginEdit}
          onDelete={onDelete}
          onDuplicate={onDuplicate}
        />
      ) : (
        <EdgeForm
          key={selectedEdges[0].id}
          edge={selectedEdges[0]}
          nodes={nodes}
          onChange={(p) => onEdgeChange(selectedEdges[0].id, p)}
          onBeginEdit={onBeginEdit}
          onDelete={onDelete}
        />
      )}
    </div>
  );
}

function NodeForm({
  node,
  nodes,
  onChange,
  onConnect,
  onBeginEdit,
  onDelete,
  onDuplicate,
}: {
  node: FlowNode;
  nodes: FlowNode[];
  onChange: (p: Partial<ComponentData>) => void;
  onConnect: (s: string, t: string, p: Protocol) => void;
  onBeginEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const id = useId();
  const d = node.data;
  const [target, setTarget] = useState("");
  const [protocol, setProtocol] = useState<Protocol>("http");
  const [propKey, setPropKey] = useState("");
  const [propValue, setPropValue] = useState("");
  const others = nodes.filter((n) => n.id !== node.id);
  const keyValid = /^[a-z][a-z0-9_]{0,31}$/.test(propKey);

  return (
    <form onSubmit={(e) => e.preventDefault()} className="flex flex-col gap-3" aria-label={`Edit ${d.name}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[13px] font-medium text-fg">Component</h2>
        <span className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={onDuplicate}><Copy aria-hidden="true" />Duplicate</Button>
          <Button size="sm" variant="ghost" onClick={onDelete}><Trash2 aria-hidden="true" />Delete</Button>
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-name`} className={labelCls}>Name</label>
          <input
            id={`${id}-name`}
            className={field}
            value={d.name}
            maxLength={LIMITS.name}
            onFocus={onBeginEdit}
            onChange={(e) => onChange({ name: e.target.value })}
            onBlur={(e) => { if (!e.target.value.trim()) onChange({ name: COMPONENTS[d.kind]?.label ?? "Component" }); }}
          />
        </div>
        <div>
          <label htmlFor={`${id}-type`} className={labelCls}>Type</label>
          <select id={`${id}-type`} className={field} value={d.kind} onFocus={onBeginEdit} onChange={(e) => onChange({ kind: e.target.value })}>
            {Object.entries(COMPONENTS).map(([k, m]) => (
              <option key={k} value={k}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label htmlFor={`${id}-desc`} className={labelCls}>Responsibility</label>
        <textarea
          id={`${id}-desc`}
          className={`${field} min-h-14 resize-y`}
          value={d.description}
          maxLength={LIMITS.description}
          placeholder="What this component owns and does"
          onFocus={onBeginEdit}
          onChange={(e) => onChange({ description: e.target.value })}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-cap`} className={labelCls}>Capacity assumption (optional)</label>
          <input
            id={`${id}-cap`}
            className={field}
            value={d.capacity ?? ""}
            maxLength={LIMITS.description}
            placeholder="e.g. 3 instances, autoscaled on CPU"
            onFocus={onBeginEdit}
            onChange={(e) => onChange({ capacity: e.target.value || null })}
          />
        </div>
        <div>
          <label htmlFor={`${id}-rel`} className={labelCls}>Reliability assumption (optional)</label>
          <input
            id={`${id}-rel`}
            className={field}
            value={d.reliability ?? ""}
            maxLength={LIMITS.description}
            placeholder="e.g. multi-AZ, automatic failover"
            onFocus={onBeginEdit}
            onChange={(e) => onChange({ reliability: e.target.value || null })}
          />
        </div>
      </div>

      <fieldset>
        <legend className={labelCls}>Properties</legend>
        {Object.keys(d.properties).length ? (
          <ul className="mb-2 flex flex-wrap gap-1.5">
            {Object.entries(d.properties).map(([k, v]) => (
              <li key={k} className="flex items-center gap-1 rounded-md border border-line bg-canvas py-0.5 pr-1 pl-2 font-mono text-[11px] text-fg">
                {k}={String(v)}
                <button
                  type="button"
                  aria-label={`Remove property ${k}`}
                  className="rounded p-0.5 text-fg-subtle hover:text-fg"
                  onClick={() => {
                    onBeginEdit();
                    const next = { ...d.properties };
                    delete next[k];
                    onChange({ properties: next });
                  }}
                >
                  <X className="size-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {Object.keys(d.properties).length < LIMITS.properties ? (
          <div className="flex gap-2">
            <input aria-label="Property name" className={`${field} font-mono`} placeholder="replicas" value={propKey} onChange={(e) => setPropKey(e.target.value.toLowerCase())} maxLength={32} />
            <input aria-label="Property value" className={field} placeholder="3" value={propValue} onChange={(e) => setPropValue(e.target.value)} maxLength={200} />
            <Button
              size="sm"
              variant="secondary"
              disabled={!keyValid || !propValue.trim()}
              onClick={() => {
                onBeginEdit();
                onChange({ properties: { ...d.properties, [propKey]: propValue.trim() } });
                setPropKey("");
                setPropValue("");
              }}
              aria-label="Add property"
            >
              <Plus aria-hidden="true" />
            </Button>
          </div>
        ) : null}
        {propKey && !keyValid ? <p className="mt-1 text-[11px] text-fg-muted">Lowercase letters, digits and underscores; start with a letter.</p> : null}
      </fieldset>

      {others.length ? (
        <fieldset>
          <legend className={labelCls}>Connect to (keyboard alternative to dragging)</legend>
          <div className="flex gap-2">
            <select aria-label="Target component" className={field} value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose a component</option>
              {others.map((n) => (
                <option key={n.id} value={n.id}>{n.data.name}</option>
              ))}
            </select>
            <select aria-label="Connection type" className={`${field} w-36`} value={protocol} onChange={(e) => setProtocol(e.target.value as Protocol)}>
              {PROTOCOLS.map((p) => (
                <option key={p} value={p}>{PROTOCOL_LABEL[p]}</option>
              ))}
            </select>
            <Button size="sm" variant="secondary" disabled={!target} onClick={() => { onConnect(node.id, target, protocol); setTarget(""); }}>
              Connect
            </Button>
          </div>
        </fieldset>
      ) : null}
    </form>
  );
}

function EdgeForm({
  edge,
  nodes,
  onChange,
  onBeginEdit,
  onDelete,
}: {
  edge: FlowEdge;
  nodes: FlowNode[];
  onChange: (p: Partial<EdgeData> & { reverse?: boolean }) => void;
  onBeginEdit: () => void;
  onDelete: () => void;
}) {
  const id = useId();
  const name = (nid: string) => nodes.find((n) => n.id === nid)?.data.name ?? nid;
  return (
    <form onSubmit={(e) => e.preventDefault()} className="flex flex-col gap-3" aria-label="Edit connection">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[13px] font-medium text-fg">
          Connection <span className="font-normal text-fg-muted">{name(edge.source)} → {name(edge.target)}</span>
        </h2>
        <span className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => { onBeginEdit(); onChange({ reverse: true }); }}>
            <ArrowLeftRight aria-hidden="true" />Reverse
          </Button>
          <Button size="sm" variant="ghost" onClick={onDelete}><Trash2 aria-hidden="true" />Delete</Button>
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-proto`} className={labelCls}>Type</label>
          <select
            id={`${id}-proto`}
            className={field}
            value={edge.data?.protocol ?? "http"}
            onFocus={onBeginEdit}
            onChange={(e) => onChange({ protocol: e.target.value as Protocol })}
          >
            {PROTOCOLS.map((p) => (
              <option key={p} value={p}>{PROTOCOL_LABEL[p]}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-label`} className={labelCls}>Label (optional)</label>
          <input
            id={`${id}-label`}
            className={field}
            value={edge.data?.label ?? ""}
            maxLength={LIMITS.name}
            placeholder="e.g. POST /links"
            onFocus={onBeginEdit}
            onChange={(e) => onChange({ label: e.target.value })}
          />
        </div>
      </div>
    </form>
  );
}
