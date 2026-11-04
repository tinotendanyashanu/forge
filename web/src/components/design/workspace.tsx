"use client";

import {
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import {
  AlertTriangle,
  Check,
  CloudOff,
  Copy,
  Keyboard,
  Loader2,
  Maximize,
  Redo2,
  Save,
  Trash2,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchDesignProject, saveDesign } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type {
  Adr,
  ArchitectureVersion,
  DesignLabStatus,
  DesignProject,
  DesignReview,
  FailureAttempt,
  FailureScenario,
  GraphDocument,
  Protocol,
} from "@/lib/types";

import { BriefPanel } from "./brief-panel";
import { DesignCanvas } from "./canvas";
import { COMPONENTS, LIMITS, newId } from "./components";
import { FailurePanel } from "./failure-panel";
import { edgeView, toFlow, toGraph, type FlowEdge, type FlowNode } from "./flow";
import { Inspector } from "./inspector";
import { NotesPanel } from "./notes-panel";
import { ReviewPanel } from "./review-panel";
import { VersionsPanel } from "./versions-panel";

type SaveState = "saved" | "unsaved" | "saving" | "conflict" | "error";
type Snapshot = { nodes: FlowNode[]; edges: FlowEdge[] };
interface LocalDraft {
  graph: GraphDocument;
  explanation: string;
  baseRevision: number;
  at: number;
}

const AUTOSAVE_MS = 1200;
const HISTORY_LIMIT = 100;
const storageKey = (id: string) => `forge:design:${id}`;

function readDraft(id: string): LocalDraft | null {
  try {
    const raw = window.localStorage.getItem(storageKey(id));
    return raw ? (JSON.parse(raw) as LocalDraft) : null;
  } catch {
    return null;
  }
}
function writeDraft(id: string, d: LocalDraft) {
  try {
    window.localStorage.setItem(storageKey(id), JSON.stringify(d));
  } catch {
    // Storage full or disabled: server autosave still runs.
  }
}
function clearDraft(id: string) {
  try {
    window.localStorage.removeItem(storageKey(id));
  } catch {}
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export interface WorkspaceProps {
  project: DesignProject;
  versions: ArchitectureVersion[];
  adrs: Adr[];
  reviews: DesignReview[];
  latestReview: DesignReview | null;
  failures: FailureAttempt[];
  scenarios: FailureScenario[];
  status: DesignLabStatus | null;
}

export function Workspace(props: WorkspaceProps) {
  return (
    <ReactFlowProvider>
      <WorkspaceInner {...props} />
    </ReactFlowProvider>
  );
}

type MobileTab = "brief" | "canvas" | "review";
type LeftTab = "brief" | "components" | "notes";
type RightTab = "review" | "failure" | "versions";

function WorkspaceInner({ project, versions, adrs, reviews, latestReview, failures, scenarios, status }: WorkspaceProps) {
  const flow = useReactFlow<FlowNode, FlowEdge>();
  // Unsaved local work from a crashed or closed tab is offered back, never applied silently.
  const [recovery, setRecovery] = useState<LocalDraft | null>(() => {
    const d = readDraft(project.id);
    if (!d) return null;
    if (same(d.graph, project.graph) && d.explanation === project.explanation) {
      clearDraft(project.id);
      return null;
    }
    return d;
  });
  const initial = useMemo(() => toFlow(project.graph), [project.graph]);
  const [nodes, setNodes] = useState<FlowNode[]>(initial.nodes);
  const [edges, setEdges] = useState<FlowEdge[]>(initial.edges);
  const [explanation, setExplanation] = useState(project.explanation);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [revision, setRevision] = useState(project.revision);
  const [history, setHistory] = useState<{ past: Snapshot[]; future: Snapshot[] }>({ past: [], future: [] });
  const [mobileTab, setMobileTab] = useState<MobileTab>("canvas");
  const [leftTab, setLeftTab] = useState<LeftTab>("brief");
  const [rightTab, setRightTab] = useState<RightTab>("review");
  const [showKeys, setShowKeys] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const latest = useRef({ nodes, edges, explanation, revision });
  const changeSeq = useRef(0);
  const savedSeq = useRef(0);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    latest.current = { nodes, edges, explanation, revision };
  }, [nodes, edges, explanation, revision]);

  const selectedNodes = nodes.filter((n) => n.selected);
  const selectedEdges = edges.filter((e) => e.selected);

  // ------------------------------------------------------------ saving

  const save = useCallback(async (): Promise<boolean> => {
    if (inFlight.current) {
      await inFlight.current;
      if (changeSeq.current === savedSeq.current) return true;
    }
    const run = (async () => {
      const seq = changeSeq.current;
      const { nodes: n, edges: e, explanation: ex, revision: rev } = latest.current;
      const graph = toGraph(n, e);
      writeDraft(project.id, { graph, explanation: ex, baseRevision: rev, at: Date.now() });
      setSaveState("saving");
      const res = await saveDesign({ projectId: project.id, baseRevision: rev, graph, explanation: ex });
      if (res.ok) {
        latest.current.revision = res.data.revision;
        setRevision(res.data.revision);
        savedSeq.current = seq;
        if (changeSeq.current === seq) {
          setSaveState("saved");
          setSaveError(null);
          clearDraft(project.id);
        } else {
          setSaveState("unsaved");
        }
        return true;
      }
      setSaveError(res.error);
      setSaveState(/changed elsewhere/i.test(res.error) ? "conflict" : "error");
      return false;
    })();
    inFlight.current = run;
    try {
      return await run;
    } finally {
      inFlight.current = null;
    }
  }, [project.id]);

  const markDirty = useCallback(() => {
    changeSeq.current += 1;
    setSaveState((s) => (s === "conflict" ? s : "unsaved"));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      void save();
    }, AUTOSAVE_MS);
  }, [save]);

  /** Saves pending changes now. Used before snapshots, reviews and drills. */
  const flush = useCallback(async (): Promise<boolean> => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (changeSeq.current === savedSeq.current && !inFlight.current) return true;
    return save();
  }, [save]);

  useEffect(() => {
    function beforeUnload(e: BeforeUnloadEvent) {
      if (changeSeq.current !== savedSeq.current) {
        const { nodes: n, edges: ed, explanation: ex, revision: rev } = latest.current;
        writeDraft(project.id, { graph: toGraph(n, ed), explanation: ex, baseRevision: rev, at: Date.now() });
        e.preventDefault();
      }
    }
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [project.id]);

  async function reloadLatest() {
    const res = await fetchDesignProject(project.id);
    if (!res.ok) {
      setSaveError(res.error);
      return;
    }
    const f = toFlow(res.data.graph);
    setNodes(f.nodes);
    setEdges(f.edges);
    setExplanation(res.data.explanation);
    setRevision(res.data.revision);
    latest.current = { nodes: f.nodes, edges: f.edges, explanation: res.data.explanation, revision: res.data.revision };
    savedSeq.current = changeSeq.current;
    setHistory({ past: [], future: [] });
    setSaveState("saved");
    setSaveError(null);
    clearDraft(project.id);
  }

  async function keepMine() {
    // Rebase this tab's work onto the latest revision, keeping history server-side.
    const res = await fetchDesignProject(project.id);
    if (!res.ok) {
      setSaveError(res.error);
      return;
    }
    latest.current.revision = res.data.revision;
    setRevision(res.data.revision);
    setSaveState("unsaved");
    await save();
  }

  function applyRecovery() {
    if (!recovery) return;
    pushHistory();
    const f = toFlow(recovery.graph);
    setNodes(f.nodes);
    setEdges(f.edges);
    setExplanation(recovery.explanation);
    setRecovery(null);
    markDirty();
  }

  // ------------------------------------------------------------ history

  const pushHistory = useCallback(() => {
    const { nodes: n, edges: e } = latest.current;
    setHistory((h) => ({ past: [...h.past.slice(-HISTORY_LIMIT + 1), { nodes: n, edges: e }], future: [] }));
  }, []);

  const undo = useCallback(() => {
    setHistory((h) => {
      const prev = h.past.at(-1);
      if (!prev) return h;
      const cur = { nodes: latest.current.nodes, edges: latest.current.edges };
      setNodes(prev.nodes);
      setEdges(prev.edges);
      return { past: h.past.slice(0, -1), future: [cur, ...h.future] };
    });
    markDirty();
  }, [markDirty]);

  const redo = useCallback(() => {
    setHistory((h) => {
      const next = h.future[0];
      if (!next) return h;
      const cur = { nodes: latest.current.nodes, edges: latest.current.edges };
      setNodes(next.nodes);
      setEdges(next.edges);
      return { past: [...h.past, cur], future: h.future.slice(1) };
    });
    markDirty();
  }, [markDirty]);

  // ------------------------------------------------------------ graph edits

  const onNodesChange = useCallback(
    (changes: NodeChange<FlowNode>[]) => {
      setNodes((ns) => applyNodeChanges(changes, ns));
      if (changes.some((c) => c.type === "position" && c.position)) markDirty();
    },
    [markDirty],
  );

  const onEdgesChange = useCallback((changes: EdgeChange<FlowEdge>[]) => {
    setEdges((es) => applyEdgeChanges(changes.filter((c) => c.type === "select"), es));
  }, []);

  const connect = useCallback(
    (source: string, target: string, protocol: Protocol = "http") => {
      if (source === target) return setNotice("A component can't connect to itself.");
      const es = latest.current.edges;
      if (es.length >= LIMITS.edges) return setNotice(`Diagrams are limited to ${LIMITS.edges} connections.`);
      if (es.some((e) => e.source === source && e.target === target && e.data?.protocol === protocol)) {
        return setNotice("That connection already exists.");
      }
      pushHistory();
      setEdges((cur) => [...cur.map((e) => ({ ...e, selected: false })), { ...edgeView(newId("e"), source, target, { protocol, label: "" }), selected: true }]);
      setNodes((cur) => cur.map((n) => (n.selected ? { ...n, selected: false } : n)));
      markDirty();
    },
    [markDirty, pushHistory],
  );

  const onConnect = useCallback((c: Connection) => connect(c.source, c.target), [connect]);

  const addComponent = useCallback(
    (type: string, at?: { x: number; y: number }) => {
      if (latest.current.nodes.length >= LIMITS.nodes) return setNotice(`Diagrams are limited to ${LIMITS.nodes} components.`);
      const meta = COMPONENTS[type];
      if (!meta) return;
      let position = at;
      if (!position) {
        const el = document.querySelector(".forge-flow")?.getBoundingClientRect();
        const center = el ? { x: el.left + el.width / 2, y: el.top + el.height / 2 } : { x: 400, y: 300 };
        const p = flow.screenToFlowPosition(center);
        const offset = (latest.current.nodes.length % 6) * 24;
        position = { x: p.x - 92 + offset, y: p.y - 27 + offset };
      }
      const count = latest.current.nodes.filter((n) => n.data.kind === type).length;
      const name = count ? `${meta.label} ${count + 1}` : meta.label;
      pushHistory();
      const node: FlowNode = {
        id: newId(type),
        type: "component",
        position,
        selected: true,
        ariaLabel: `${name}, ${meta.label}`,
        data: { kind: type, name, description: "", properties: {}, capacity: null, reliability: null },
      };
      setNodes((cur) => [...cur.map((n) => (n.selected ? { ...n, selected: false } : n)), node]);
      setEdges((cur) => cur.map((e) => (e.selected ? { ...e, selected: false } : e)));
      setMobileTab("canvas");
      markDirty();
    },
    [flow, markDirty, pushHistory],
  );

  const onDropComponent = useCallback(
    (type: string, screen: { x: number; y: number }) => {
      const p = flow.screenToFlowPosition(screen);
      addComponent(type, { x: p.x - 92, y: p.y - 27 });
    },
    [addComponent, flow],
  );

  const deleteSelection = useCallback(() => {
    const { nodes: ns, edges: es } = latest.current;
    const dropNodes = new Set(ns.filter((n) => n.selected).map((n) => n.id));
    const dropEdges = new Set(es.filter((e) => e.selected || dropNodes.has(e.source) || dropNodes.has(e.target)).map((e) => e.id));
    if (!dropNodes.size && !dropEdges.size) return;
    pushHistory();
    setNodes(ns.filter((n) => !dropNodes.has(n.id)));
    setEdges(es.filter((e) => !dropEdges.has(e.id)));
    markDirty();
  }, [markDirty, pushHistory]);

  const duplicateSelection = useCallback(() => {
    const { nodes: ns, edges: es } = latest.current;
    const picked = ns.filter((n) => n.selected);
    if (!picked.length) return;
    if (ns.length + picked.length > LIMITS.nodes) return setNotice(`Diagrams are limited to ${LIMITS.nodes} components.`);
    pushHistory();
    const map = new Map(picked.map((n) => [n.id, newId(n.data.kind)]));
    const copies: FlowNode[] = picked.map((n) => ({
      ...n,
      id: map.get(n.id)!,
      selected: true,
      position: { x: n.position.x + 32, y: n.position.y + 32 },
      data: { ...n.data, name: `${n.data.name} copy`.slice(0, LIMITS.name), properties: { ...n.data.properties } },
    }));
    const inner = es
      .filter((e) => map.has(e.source) && map.has(e.target))
      .map((e) => edgeView(newId("e"), map.get(e.source)!, map.get(e.target)!, { ...e.data! }));
    setNodes([...ns.map((n) => ({ ...n, selected: false })), ...copies]);
    setEdges([...es.map((e) => ({ ...e, selected: false })), ...inner]);
    markDirty();
  }, [markDirty, pushHistory]);

  const updateNode = useCallback(
    (id: string, patch: Partial<FlowNode["data"]>) => {
      setNodes((cur) =>
        cur.map((n) => {
          if (n.id !== id) return n;
          const data = { ...n.data, ...patch };
          return { ...n, data, ariaLabel: `${data.name}, ${COMPONENTS[data.kind]?.label ?? data.kind}` };
        }),
      );
      markDirty();
    },
    [markDirty],
  );

  const updateEdge = useCallback(
    (id: string, patch: Partial<NonNullable<FlowEdge["data"]>> & { reverse?: boolean }) => {
      setEdges((cur) =>
        cur.map((e) => {
          if (e.id !== id) return e;
          const { reverse, ...rest } = patch;
          const data = { ...e.data!, ...rest };
          const next = edgeView(e.id, reverse ? e.target : e.source, reverse ? e.source : e.target, data);
          return { ...next, selected: e.selected };
        }),
      );
      markDirty();
    },
    [markDirty],
  );

  const onExplanation = useCallback(
    (value: string) => {
      setExplanation(value);
      markDirty();
    },
    [markDirty],
  );

  const onRestored = useCallback((graph: GraphDocument, ex: string, rev: number) => {
    const f = toFlow(graph);
    setNodes(f.nodes);
    setEdges(f.edges);
    setExplanation(ex);
    setRevision(rev);
    latest.current = { nodes: f.nodes, edges: f.edges, explanation: ex, revision: rev };
    savedSeq.current = changeSeq.current;
    setHistory({ past: [], future: [] });
    setSaveState("saved");
    clearDraft(project.id);
  }, [project.id]);

  const highlight = useCallback((ids: string[]) => {
    const set = new Set(ids);
    setNodes((cur) => cur.map((n) => ({ ...n, data: { ...n.data, highlighted: set.has(n.id) } })));
  }, []);

  // ------------------------------------------------------------ keyboard

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();
      if (mod && key === "s") {
        e.preventDefault();
        void flush();
        return;
      }
      if (isTyping(e.target)) return;
      if (mod && key === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if (mod && key === "y") {
        e.preventDefault();
        redo();
      } else if (mod && key === "d") {
        e.preventDefault();
        duplicateSelection();
      } else if (!mod && (e.key === "Delete" || e.key === "Backspace")) {
        e.preventDefault();
        deleteSelection();
      } else if (!mod && key === "f") {
        void flow.fitView({ padding: 0.25, duration: 200, maxZoom: 1.2 });
      } else if (e.key === "Escape") {
        setNodes((cur) => cur.map((n) => (n.selected ? { ...n, selected: false } : n)));
        setEdges((cur) => cur.map((ed) => (ed.selected ? { ...ed, selected: false } : ed)));
        setShowKeys(false);
      } else if (e.key === "?") {
        setShowKeys((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [deleteSelection, duplicateSelection, flow, flush, redo, undo]);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 3500);
    return () => clearTimeout(t);
  }, [notice]);

  // ------------------------------------------------------------ render

  const graphForPanels = useMemo(() => toGraph(nodes, edges), [nodes, edges]);
  // Evidence chips show names, not ids: nodes by name, edges as "A → B".
  const nodeNames = useMemo(() => {
    const names: Record<string, string> = Object.fromEntries(nodes.map((n) => [n.id, n.data.name]));
    for (const e of edges) names[e.id] = `${names[e.source] ?? e.source} → ${names[e.target] ?? e.target}`;
    return names;
  }, [nodes, edges]);

  const left = (
    <PanelTabs
      label="Challenge panel"
      tabs={[["brief", "Brief"], ["components", "Components"], ["notes", "Explain"]]}
      value={leftTab}
      onChange={(v) => setLeftTab(v as LeftTab)}
    >
      {leftTab === "brief" ? <BriefPanel challenge={project.challenge_detail} outdated={project.challenge_outdated} /> : null}
      {leftTab === "components" ? <ComponentLibrary onAdd={addComponent} count={nodes.length} /> : null}
      {leftTab === "notes" ? (
        <NotesPanel projectId={project.id} explanation={explanation} onExplanation={onExplanation} initialAdrs={adrs} />
      ) : null}
    </PanelTabs>
  );

  const right = (
    <PanelTabs
      label="Review panel"
      tabs={[["review", "AI review"], ["failure", "Failure drills"], ["versions", "Versions"]]}
      value={rightTab}
      onChange={(v) => setRightTab(v as RightTab)}
    >
      <div className={rightTab === "review" ? "contents" : "hidden"}>
        <ReviewPanel
          projectId={project.id}
          reviews={reviews}
          initialReview={latestReview}
          status={status}
          flush={flush}
          hasNodes={nodes.length > 0}
          nodeNames={nodeNames}
          onHighlight={highlight}
        />
      </div>
      {rightTab === "failure" ? (
        <FailurePanel
          projectId={project.id}
          suggested={project.challenge_detail.failure_scenarios}
          all={scenarios}
          initial={failures}
          flush={flush}
          hasNodes={nodes.length > 0}
        />
      ) : null}
      {rightTab === "versions" ? (
        <VersionsPanel
          projectId={project.id}
          initial={versions}
          flush={flush}
          revision={revision}
          onRestored={onRestored}
          current={graphForPanels}
        />
      ) : null}
    </PanelTabs>
  );

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col md:h-dvh">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line-subtle px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-fg-subtle">
            <a href="/design" className="hover:text-fg">Design lab</a> / {project.challenge.title}
          </p>
          <h1 className="truncate text-[15px] font-medium text-fg">{project.title}</h1>
        </div>
        <SaveIndicator state={saveState} onRetry={() => void save()} />
      </header>

      {recovery ? (
        <Banner tone="warn">
          <span>Unsaved changes from {new Date(recovery.at).toLocaleString()} were found in this browser.</span>
          <span className="flex gap-2">
            <Button size="sm" onClick={applyRecovery}>Restore them</Button>
            <Button size="sm" variant="ghost" onClick={() => { clearDraft(project.id); setRecovery(null); }}>Discard</Button>
          </span>
        </Banner>
      ) : null}
      {saveState === "conflict" ? (
        <Banner tone="warn">
          <span>This design was changed in another tab or window. Your edits are kept here and in this browser.</span>
          <span className="flex gap-2">
            <Button size="sm" onClick={() => void keepMine()}>Keep my version</Button>
            <Button size="sm" variant="ghost" onClick={() => void reloadLatest()}>Load latest</Button>
          </span>
        </Banner>
      ) : null}
      {saveState === "error" && saveError ? (
        <Banner tone="warn">
          <span>Not saved: {saveError}</span>
          <Button size="sm" variant="secondary" onClick={() => void save()}>Retry</Button>
        </Banner>
      ) : null}

      {/* Mobile panel switcher */}
      <div role="tablist" aria-label="Workspace panels" className="flex border-b border-line-subtle lg:hidden">
        {([["brief", "Challenge"], ["canvas", "Canvas"], ["review", "Review"]] as const).map(([k, label]) => (
          <button
            key={k}
            role="tab"
            type="button"
            aria-selected={mobileTab === k}
            onClick={() => setMobileTab(k)}
            className={cn(
              "flex-1 border-b-2 py-2.5 text-sm",
              mobileTab === k ? "border-fg text-fg" : "border-transparent text-fg-muted",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[264px_minmax(0,1fr)_320px] xl:grid-cols-[300px_minmax(0,1fr)_380px]">
        <aside aria-label="Challenge" className={cn("min-h-0 border-line-subtle lg:flex lg:border-r", mobileTab === "brief" ? "flex" : "hidden")}>
          {left}
        </aside>

        <section aria-label="Design canvas" className={cn("relative min-h-0 flex-col lg:flex", mobileTab === "canvas" ? "flex" : "hidden")}>
          <Toolbar
            canUndo={history.past.length > 0}
            canRedo={history.future.length > 0}
            hasSelection={selectedNodes.length + selectedEdges.length > 0}
            hasNodeSelection={selectedNodes.length > 0}
            onUndo={undo}
            onRedo={redo}
            onDuplicate={duplicateSelection}
            onDelete={deleteSelection}
            onZoomIn={() => void flow.zoomIn({ duration: 150 })}
            onZoomOut={() => void flow.zoomOut({ duration: 150 })}
            onFit={() => void flow.fitView({ padding: 0.25, duration: 200, maxZoom: 1.2 })}
            onSave={() => void flush()}
            onKeys={() => setShowKeys((v) => !v)}
            counts={{ nodes: nodes.length, edges: edges.length }}
          />
          <div className="relative min-h-0 flex-1">
            <DesignCanvas
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStart={pushHistory}
              onDropComponent={onDropComponent}
            />
            {nodes.length === 0 ? (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
                <div className="max-w-xs rounded-xl border border-dashed border-line bg-canvas/80 p-5 text-center text-sm text-fg-muted">
                  Drag components from the library onto the canvas, or select one to add it. Connect components by dragging
                  between their edges.
                  <div className="pointer-events-auto mt-3">
                    <Button size="sm" variant="secondary" onClick={() => { setLeftTab("components"); setMobileTab("brief"); }}>
                      Open component library
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
            {notice ? (
              <p role="status" className="absolute top-3 left-1/2 -translate-x-1/2 rounded-lg border border-line bg-surface-elevated px-3 py-1.5 text-xs text-fg">
                {notice}
              </p>
            ) : null}
            {showKeys ? <ShortcutHelp onClose={() => setShowKeys(false)} /> : null}
          </div>
          <Inspector
            nodes={nodes}
            selectedNodes={selectedNodes}
            selectedEdges={selectedEdges}
            onNodeChange={updateNode}
            onEdgeChange={updateEdge}
            onConnect={connect}
            onBeginEdit={pushHistory}
            onDelete={deleteSelection}
            onDuplicate={duplicateSelection}
          />
        </section>

        <aside aria-label="Review" className={cn("min-h-0 border-line-subtle lg:flex lg:border-l", mobileTab === "review" ? "flex" : "hidden")}>
          {right}
        </aside>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ pieces

function PanelTabs({
  label,
  tabs,
  value,
  onChange,
  children,
}: {
  label: string;
  tabs: [string, string][];
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-0 w-full flex-col">
      <div role="tablist" aria-label={label} className="flex shrink-0 gap-1 border-b border-line-subtle px-2 pt-2">
        {tabs.map(([k, l]) => (
          <button
            key={k}
            role="tab"
            type="button"
            aria-selected={value === k}
            onClick={() => onChange(k)}
            className={cn(
              "rounded-t-md border-b-2 px-3 py-2 text-[13px]",
              value === k ? "border-fg text-fg" : "border-transparent text-fg-muted hover:text-fg",
            )}
          >
            {l}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="min-h-0 flex-1 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}

function ComponentLibrary({ onAdd, count }: { onAdd: (type: string) => void; count: number }) {
  const groups = Object.entries(COMPONENTS).reduce<Record<string, [string, (typeof COMPONENTS)[string]][]>>((acc, entry) => {
    (acc[entry[1].category] ??= []).push(entry);
    return acc;
  }, {});
  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs leading-relaxed text-fg-subtle">
        Drag onto the canvas, or press a component to add it at the centre. {count}/{LIMITS.nodes} used.
      </p>
      {Object.entries(groups).map(([cat, items]) => (
        <div key={cat}>
          <h3 className="mb-2 text-xs font-medium text-fg-subtle">{cat}</h3>
          <ul className="grid grid-cols-2 gap-1.5">
            {items.map(([type, meta]) => (
              <li key={type}>
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/x-forge-component", type);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() => onAdd(type)}
                  className="flex w-full cursor-grab items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-2 text-left text-xs text-fg hover:border-neutral-500 hover:bg-surface-hover active:cursor-grabbing"
                  aria-label={`Add ${meta.label}`}
                >
                  <meta.icon className="size-3.5 shrink-0 text-fg-muted" aria-hidden="true" />
                  <span className="truncate">{meta.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ToolButton({ label, keys, onClick, disabled, children }: { label: string; keys?: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-keyshortcuts={keys}
      title={keys ? `${label} (${keys.replace("Meta+", "⌘").replace("Control+", "Ctrl+")})` : label}
      className="flex size-8 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg disabled:opacity-30 [&_svg]:size-4"
    >
      {children}
    </button>
  );
}

function Toolbar(p: {
  canUndo: boolean;
  canRedo: boolean;
  hasSelection: boolean;
  hasNodeSelection: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onSave: () => void;
  onKeys: () => void;
  counts: { nodes: number; edges: number };
}) {
  return (
    <div role="toolbar" aria-label="Canvas tools" className="flex shrink-0 flex-wrap items-center gap-0.5 border-b border-line-subtle px-2 py-1">
      <ToolButton label="Undo" keys="Meta+Z" onClick={p.onUndo} disabled={!p.canUndo}><Undo2 /></ToolButton>
      <ToolButton label="Redo" keys="Meta+Shift+Z" onClick={p.onRedo} disabled={!p.canRedo}><Redo2 /></ToolButton>
      <span className="mx-1 h-5 w-px bg-line" aria-hidden="true" />
      <ToolButton label="Duplicate selection" keys="Meta+D" onClick={p.onDuplicate} disabled={!p.hasNodeSelection}><Copy /></ToolButton>
      <ToolButton label="Delete selection" keys="Delete" onClick={p.onDelete} disabled={!p.hasSelection}><Trash2 /></ToolButton>
      <span className="mx-1 h-5 w-px bg-line" aria-hidden="true" />
      <ToolButton label="Zoom in" onClick={p.onZoomIn}><ZoomIn /></ToolButton>
      <ToolButton label="Zoom out" onClick={p.onZoomOut}><ZoomOut /></ToolButton>
      <ToolButton label="Fit to view" keys="F" onClick={p.onFit}><Maximize /></ToolButton>
      <span className="mx-1 h-5 w-px bg-line" aria-hidden="true" />
      <ToolButton label="Save now" keys="Meta+S" onClick={p.onSave}><Save /></ToolButton>
      <ToolButton label="Keyboard shortcuts" keys="?" onClick={p.onKeys}><Keyboard /></ToolButton>
      <span className="ml-auto pr-2 font-mono text-[11px] text-fg-subtle tabular-nums">
        {p.counts.nodes} components · {p.counts.edges} connections
      </span>
    </div>
  );
}

function SaveIndicator({ state, onRetry }: { state: SaveState; onRetry: () => void }) {
  const map = {
    saved: { icon: Check, text: "All changes saved" },
    unsaved: { icon: null, text: "Unsaved changes" },
    saving: { icon: Loader2, text: "Saving…" },
    conflict: { icon: AlertTriangle, text: "Edit conflict" },
    error: { icon: CloudOff, text: "Not saved" },
  }[state];
  const Icon = map.icon;
  return (
    <p role="status" aria-live="polite" className="flex items-center gap-1.5 text-xs text-fg-muted">
      {Icon ? <Icon className={cn("size-3.5", state === "saving" && "animate-spin")} aria-hidden="true" /> : <span className="size-1.5 rounded-full bg-fg-muted" aria-hidden="true" />}
      {map.text}
      {state === "error" ? (
        <button type="button" onClick={onRetry} className="ml-1 underline hover:text-fg">Retry</button>
      ) : null}
    </p>
  );
}

function Banner({ tone, children }: { tone: "warn"; children: React.ReactNode }) {
  return (
    <div role="alert" className={cn("flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2 text-sm", tone === "warn" && "border-line bg-surface-elevated text-fg")}>
      {children}
    </div>
  );
}

const SHORTCUTS: [string, string][] = [
  ["⌘/Ctrl + Z", "Undo"],
  ["⌘/Ctrl + Shift + Z, Ctrl + Y", "Redo"],
  ["⌘/Ctrl + D", "Duplicate selection"],
  ["Delete / Backspace", "Delete selection"],
  ["⌘/Ctrl + S", "Save now"],
  ["F", "Fit diagram to view"],
  ["Tab, then Enter", "Focus and select a component"],
  ["Arrow keys", "Move the selected component"],
  ["Shift + drag", "Box-select"],
  ["Esc", "Clear selection"],
  ["?", "Toggle this list"],
];

function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <div role="dialog" aria-label="Keyboard shortcuts" className="absolute top-3 right-3 z-10 w-72 rounded-xl border border-line bg-surface-elevated p-4 shadow-xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-fg">Keyboard shortcuts</h2>
        <button type="button" onClick={onClose} className="text-xs text-fg-muted hover:text-fg">Close</button>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
        {SHORTCUTS.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-mono text-fg">{k}</dt>
            <dd className="text-fg-muted">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
