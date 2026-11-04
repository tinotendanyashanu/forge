"use client";

import { ReactFlowProvider } from "@xyflow/react";
import { Camera, Eye, GitCompare, Loader2, RotateCcw } from "lucide-react";
import { useId, useMemo, useState } from "react";

import {
  compareDesignVersions,
  fetchDesignVersion,
  fetchDesignVersions,
  restoreDesignVersion,
  snapshotDesign,
} from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { ArchitectureVersion, GraphDiff, GraphDocument } from "@/lib/types";

import { DesignCanvas } from "./canvas";
import { PROTOCOL_LABEL } from "./components";
import { toFlow } from "./flow";

const field =
  "w-full rounded-md border border-line bg-canvas px-2.5 py-1.5 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none";

export function VersionsPanel({
  projectId,
  initial,
  flush,
  revision,
  onRestored,
  current,
}: {
  projectId: string;
  initial: ArchitectureVersion[];
  flush: () => Promise<boolean>;
  revision: number;
  onRestored: (g: GraphDocument, explanation: string, revision: number) => void;
  current: GraphDocument;
}) {
  const id = useId();
  const [versions, setVersions] = useState(initial);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState<number | "">(initial[0]?.number ?? "");
  const [to, setTo] = useState<number | "current">("current");
  const [diff, setDiff] = useState<GraphDiff | null>(null);
  const [preview, setPreview] = useState<ArchitectureVersion | null>(null);

  async function snapshot() {
    setBusy("snapshot");
    setError(null);
    if (!(await flush())) {
      setBusy(null);
      return setError("Save your design first: resolve the save problem shown above.");
    }
    const res = await snapshotDesign({ projectId, name: name.trim() || `Version ${(versions[0]?.number ?? 0) + 1}` });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    setVersions((v) => [res.data, ...v]);
    setName("");
    setFrom(res.data.number);
  }

  async function compare() {
    if (from === "") return;
    setBusy("compare");
    setError(null);
    await flush();
    const res = await compareDesignVersions({ projectId, from, to: to === "current" ? null : to });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    setDiff(res.data);
  }

  async function view(n: number) {
    setBusy(`view-${n}`);
    const res = await fetchDesignVersion({ projectId, number: n });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    setPreview(res.data);
  }

  async function restore(n: number) {
    setBusy(`restore-${n}`);
    setError(null);
    if (!(await flush())) {
      setBusy(null);
      return setError("Save your design first: resolve the save problem shown above.");
    }
    const res = await restoreDesignVersion({ projectId, number: n, baseRevision: revision });
    setBusy(null);
    if (!res.ok) return setError(res.error);
    onRestored(res.data.graph, res.data.explanation, res.data.revision);
    setPreview(null);
    // Restoring may have snapshotted the previous design first.
    const list = await fetchDesignVersions(projectId);
    if (list.ok) setVersions(list.data);
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void snapshot();
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor={`${id}-name`} className="text-xs font-medium text-fg">Save a named snapshot</label>
        <div className="flex gap-2">
          <input id={`${id}-name`} className={field} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="e.g. Added read replicas" />
          <Button type="submit" size="sm" disabled={busy !== null}>
            {busy === "snapshot" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Camera aria-hidden="true" />}Snapshot
          </Button>
        </div>
        <p className="text-[11px] text-fg-subtle">
          Snapshots are immutable. Evaluations and failure drills snapshot automatically. Restoring keeps a copy of the current design.
        </p>
      </form>
      {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}

      {versions.length ? (
        <>
          <section>
            <h3 className="mb-2 text-xs font-medium text-fg-subtle">History</h3>
            <ol className="flex flex-col gap-1">
              {versions.map((v) => (
                <li key={v.number} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-surface-hover">
                  <span className="font-mono text-[11px] text-fg-subtle">v{v.number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-fg">{v.name}</span>
                    <span className="text-[11px] text-fg-subtle">
                      {new Date(v.created_at).toLocaleString()} · {v.components} components · {v.connections} connections
                    </span>
                  </span>
                  <Button size="sm" variant="ghost" aria-label={`View version ${v.number}`} onClick={() => void view(v.number)}>
                    {busy === `view-${v.number}` ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </Button>
                  <Button size="sm" variant="ghost" aria-label={`Restore version ${v.number}`} onClick={() => void restore(v.number)} disabled={busy !== null}>
                    <RotateCcw aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ol>
          </section>

          {preview ? <Preview version={preview} onClose={() => setPreview(null)} /> : null}

          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-medium text-fg-subtle">Compare</h3>
            <div className="flex items-center gap-2">
              <select aria-label="Compare from" className={field} value={from} onChange={(e) => setFrom(Number(e.target.value))}>
                {versions.map((v) => <option key={v.number} value={v.number}>v{v.number} {v.name}</option>)}
              </select>
              <span className="text-xs text-fg-subtle">to</span>
              <select aria-label="Compare to" className={field} value={to} onChange={(e) => setTo(e.target.value === "current" ? "current" : Number(e.target.value))}>
                <option value="current">Current design</option>
                {versions.map((v) => <option key={v.number} value={v.number}>v{v.number} {v.name}</option>)}
              </select>
              <Button size="sm" variant="secondary" onClick={() => void compare()} disabled={busy !== null} aria-label="Compare versions">
                <GitCompare aria-hidden="true" />
              </Button>
            </div>
            {diff ? <DiffView diff={diff} /> : null}
          </section>
        </>
      ) : (
        <p className="text-xs text-fg-muted">
          No versions yet. You have {current.nodes.length} components in the working design.
        </p>
      )}
    </div>
  );
}

function Preview({ version, onClose }: { version: ArchitectureVersion; onClose: () => void }) {
  const flow = useMemo(() => toFlow(version.graph!), [version.graph]);
  return (
    <section aria-label={`Version ${version.number} preview`} className="rounded-lg border border-line">
      <div className="flex items-center justify-between border-b border-line-subtle px-3 py-2">
        <p className="text-xs text-fg">v{version.number} · {version.name} (read-only)</p>
        <button type="button" onClick={onClose} className="text-xs text-fg-muted hover:text-fg">Close</button>
      </div>
      <div className="h-64">
        <ReactFlowProvider>
          <DesignCanvas nodes={flow.nodes} edges={flow.edges} readOnly minimap={false} />
        </ReactFlowProvider>
      </div>
      {version.explanation ? (
        <details className="border-t border-line-subtle px-3 py-2">
          <summary className="cursor-pointer text-xs text-fg-muted">Explanation at this version</summary>
          <p className="mt-2 text-xs leading-relaxed whitespace-pre-wrap text-fg">{version.explanation}</p>
        </details>
      ) : null}
    </section>
  );
}

function DiffView({ diff }: { diff: GraphDiff }) {
  const empty =
    !diff.nodes_added.length && !diff.nodes_removed.length && !diff.nodes_changed.length &&
    !diff.edges_added.length && !diff.edges_removed.length && !diff.edges_changed.length && !diff.explanation_changed;
  if (empty) return <p className="text-xs text-fg-muted">No differences between {diff.from} and {diff.to}.</p>;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line p-3">
      <p className="text-xs text-fg-muted">{diff.from} → {diff.to}</p>
      <Group sign="+" title="Components added" items={diff.nodes_added.map((n) => `${n.name} (${n.type})`)} />
      <Group sign="−" title="Components removed" items={diff.nodes_removed.map((n) => `${n.name} (${n.type})`)} />
      <Group sign="~" title="Components changed" items={diff.nodes_changed.map((n) => `${n.name}: ${n.fields.join(", ")}`)} />
      <Group sign="+" title="Connections added" items={diff.edges_added.map((e) => `${e.from} → ${e.to} via ${PROTOCOL_LABEL[e.protocol]}`)} />
      <Group sign="−" title="Connections removed" items={diff.edges_removed.map((e) => `${e.from} → ${e.to} via ${PROTOCOL_LABEL[e.protocol]}`)} />
      <Group sign="~" title="Connections changed" items={diff.edges_changed.map((e) => `${e.from} → ${e.to} via ${PROTOCOL_LABEL[e.protocol]}`)} />
      {diff.explanation_changed ? <p className="text-xs text-fg">~ Explanation changed</p> : null}
    </div>
  );
}

function Group({ sign, title, items }: { sign: string; title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className="text-[11px] text-fg-subtle">{title}</h4>
      <ul className="font-mono text-xs text-fg">
        {items.map((x, i) => <li key={i}><span className="text-fg-subtle">{sign} </span>{x}</li>)}
      </ul>
    </div>
  );
}
