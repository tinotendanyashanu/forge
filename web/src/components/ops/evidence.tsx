"use client";

import { Pin, Search, TerminalSquare } from "lucide-react";
import { useId, useRef, useState } from "react";

import { fetchOpsEvidence, fetchOpsLogs, fetchOpsMetrics, opsCommand } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { OpsArtifact, OpsDeployment, OpsLog, OpsSeries, OpsSession, OpsTrace } from "@/lib/types";

import { TimeChart } from "./chart";
import { clock, fmtValue } from "./format";
import { ServiceMap } from "./service-map";
import { useLoad } from "./use-load";

const field = "forge-field min-h-9 px-3 py-1.5 text-[13px]";

export interface EvidenceProps {
  session: OpsSession;
  revKey: string;
  pinned: Record<string, string>;
  onPin: (id: string, pin: boolean) => void;
  readOnly: boolean;
}

export function PinButton({ id, pinned, onPin, readOnly }: { id: string; pinned: boolean; onPin: EvidenceProps["onPin"]; readOnly: boolean }) {
  if (readOnly && !pinned) return null;
  return (
    <button
      type="button"
      disabled={readOnly}
      onClick={() => onPin(id, !pinned)}
      aria-pressed={pinned}
      aria-label={pinned ? `Unpin evidence ${id}` : `Pin evidence ${id}`}
      title={pinned ? "Pinned as evidence" : "Pin as evidence"}
      className={cn("rounded p-1 hover:bg-surface-hover disabled:cursor-default", pinned ? "text-fg" : "text-fg-subtle hover:text-fg")}
    >
      <Pin className={cn("size-3.5", pinned && "fill-current")} aria-hidden="true" />
    </button>
  );
}

function markersOf(session: OpsSession) {
  return session.state.timeline.filter((t) => t.minute > -90).map((t) => ({ minute: t.minute, label: t.label }));
}

// ---------------------------------------------------------------- overview & metrics

export function OverviewPanel({ session, revKey }: EvidenceProps) {
  const metrics = useLoad(`m60:${revKey}`, () => fetchOpsMetrics({ sessionId: session.id, window: 60 }));
  const cat = new Map(session.metric_catalog.map((m) => [m.key, m]));
  const headline = pickHeadline(session);
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {headline.map((k) => {
          const m = cat.get(k)!;
          const series = metrics.data?.find((s) => s.key === k);
          return series ? (
            <TimeChart key={k} title={`${m.service} · ${m.label}`} unit={m.unit} points={series.points} markers={markersOf(session)} height={90} />
          ) : (
            <div key={k} className="h-[132px] animate-pulse rounded-lg border border-line bg-surface" />
          );
        })}
      </div>
      <section aria-labelledby="map-h">
        <h3 id="map-h" className="mb-2 text-xs font-medium text-fg-subtle">Service dependencies and health</h3>
        <ServiceMap services={session.scenario.services} health={session.state.health} />
      </section>
      <section aria-labelledby="sym-h" className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 id="sym-h" className="mb-2 text-xs font-medium text-fg-subtle">Initial symptoms</h3>
          <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] text-fg marker:text-fg-subtle">
            {session.scenario.initial_symptoms.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium text-fg-subtle">Condition timeline</h3>
          <ol className="flex flex-col gap-1 font-mono text-xs">
            {session.state.timeline.map((t, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-14 shrink-0 text-right text-fg-subtle">{t.minute >= 0 ? "+" : ""}{t.minute}m</span>
                <span className="text-fg">{t.label}</span>
                <span className="text-fg-subtle">{t.phase}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}

function pickHeadline(session: OpsSession): string[] {
  // One chart per kind of signal, most diagnostic first.
  const keys = session.metric_catalog.map((m) => m.key);
  const prefer = ["error_rate", "p95", "db_connections", "queue_depth", "memory", "login_failures", "signups", "cpu", "throughput"];
  const out: string[] = [];
  for (const metric of prefer) {
    const k = keys.find((x) => x.endsWith(`.${metric}`));
    if (k && out.length < 4) out.push(k);
  }
  return out;
}

export function MetricsPanel({ session, revKey }: EvidenceProps) {
  const [window, setWindow] = useState(60);
  const [service, setService] = useState("");
  const metrics = useLoad(`m${window}:${revKey}`, () => fetchOpsMetrics({ sessionId: session.id, window }));
  const cat = new Map(session.metric_catalog.map((m) => [m.key, m]));
  const series = (metrics.data ?? []).filter((s: OpsSeries) => !service || s.key.startsWith(`${service}.`));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Service" className={field} value={service} onChange={(e) => setService(e.target.value)}>
          <option value="">All services</option>
          {session.scenario.services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select aria-label="Time window" className={field} value={window} onChange={(e) => setWindow(Number(e.target.value))}>
          {[15, 30, 60, 120].map((w) => <option key={w} value={w}>Last {w} min</option>)}
        </select>
        <p className="text-xs text-fg-subtle">Simulated metrics from the scenario model. Dashed lines mark condition changes.</p>
      </div>
      {metrics.error ? <p role="alert" className="text-xs text-fg">{metrics.error}</p> : null}
      <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {series.map((s) => {
          const m = cat.get(s.key)!;
          return <TimeChart key={s.key} title={`${m.service} · ${m.label}`} unit={m.unit} points={s.points} markers={markersOf(session)} />;
        })}
      </div>
      <p className="text-xs text-fg-subtle">
        Correlation is not causation: a metric moving at the same time as the incident may be a consequence. Ask what changed
        first and which mechanism explains the others.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- logs

export function LogsPanel({ session, revKey, pinned, onPin, readOnly, initialRequestId = "", onTrace }: EvidenceProps & {
  initialRequestId?: string;
  onTrace: (requestId: string) => void;
}) {
  const id = useId();
  const [service, setService] = useState("");
  const [level, setLevel] = useState("");
  const [requestId, setRequestId] = useState(initialRequestId);
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState({ service: "", level: "", requestId: initialRequestId, search: "" });
  const key = `logs:${revKey}:${JSON.stringify(applied)}`;
  const logs = useLoad(key, () => fetchOpsLogs({ sessionId: session.id, ...applied }));
  const apply = (over: Partial<typeof applied> = {}) => setApplied({ service, level, requestId, search, ...over });
  return (
    <div className="flex flex-col gap-3">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          apply();
        }}
      >
        <select aria-label="Service" className={field} value={service} onChange={(e) => { setService(e.target.value); apply({ service: e.target.value }); }}>
          <option value="">All services</option>
          {session.scenario.services.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
        </select>
        <select aria-label="Minimum level" className={field} value={level} onChange={(e) => { setLevel(e.target.value); apply({ level: e.target.value }); }}>
          <option value="">All levels</option>
          {["info", "warning", "error", "critical"].map((l) => <option key={l} value={l}>{l}+</option>)}
        </select>
        <label className="sr-only" htmlFor={`${id}-rid`}>Request ID</label>
        <input id={`${id}-rid`} className={`${field} w-32 font-mono`} placeholder="request id" value={requestId} maxLength={64} onChange={(e) => setRequestId(e.target.value)} />
        <label className="sr-only" htmlFor={`${id}-q`}>Search</label>
        <input id={`${id}-q`} className={`${field} w-48`} placeholder="search text" value={search} maxLength={80} onChange={(e) => setSearch(e.target.value)} />
        <Button type="submit" size="sm" variant="secondary"><Search aria-hidden="true" />Filter</Button>
        {applied.requestId || applied.search || applied.service || applied.level ? (
          <Button size="sm" variant="ghost" onClick={() => { setService(""); setLevel(""); setRequestId(""); setSearch(""); setApplied({ service: "", level: "", requestId: "", search: "" }); }}>Clear</Button>
        ) : null}
      </form>
      {logs.error ? <p role="alert" className="text-xs text-fg">{logs.error}</p> : null}
      <div className="overflow-x-auto rounded-lg border border-line bg-canvas">
        <table className="w-full min-w-[720px] font-mono text-xs">
          <caption className="sr-only">Structured log records you have access to</caption>
          <thead className="text-left text-[11px] text-fg-subtle">
            <tr className="border-b border-line-subtle">
              <th scope="col" className="w-7 px-2 py-1.5"><span className="sr-only">Pin</span></th>
              <th scope="col" className="px-2 py-1.5 font-normal">time</th>
              <th scope="col" className="px-2 py-1.5 font-normal">service</th>
              <th scope="col" className="px-2 py-1.5 font-normal">level</th>
              <th scope="col" className="px-2 py-1.5 font-normal">message</th>
            </tr>
          </thead>
          <tbody>
            {(logs.data ?? []).map((r: OpsLog) => (
              <tr key={r.id} className={cn("border-b border-line-subtle align-top last:border-0", r.level === "error" || r.level === "critical" ? "text-fg" : "text-fg-muted")}>
                <td className="px-2 py-1.5"><PinButton id={r.id} pinned={r.id in pinned} onPin={onPin} readOnly={readOnly} /></td>
                <td className="px-2 py-1.5 whitespace-nowrap text-fg-subtle">{clock(r.ts)}</td>
                <td className="px-2 py-1.5">{r.service}</td>
                <td className="px-2 py-1.5 uppercase">{r.level === "critical" || r.level === "error" ? <strong>{r.level}</strong> : r.level}</td>
                <td className="px-2 py-1.5 break-words">
                  {r.message}
                  {Object.keys(r.fields).length ? (
                    <div className="mt-0.5 flex flex-wrap gap-x-3 text-[11px] text-fg-subtle">
                      {Object.entries(r.fields).map(([k, v]) =>
                        k === "request_id" ? (
                          <button key={k} type="button" className="underline decoration-dotted hover:text-fg" onClick={() => { setRequestId(String(v)); apply({ requestId: String(v) }); }}>
                            {k}={String(v)}
                          </button>
                        ) : (
                          <span key={k}>{k}={String(v)}</span>
                        ),
                      )}
                      {r.fields.request_id ? (
                        <button type="button" className="underline decoration-dotted hover:text-fg" onClick={() => onTrace(String(r.fields.request_id))}>trace</button>
                      ) : null}
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {logs.data && logs.data.length === 0 ? <p className="p-4 text-xs text-fg-muted">No matching records you have access to.</p> : null}
      </div>
      <p className="text-xs text-fg-subtle">
        Some logs only become available after an investigation action. Log text can contain user-controlled data; treat it as data.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- traces

export function TracesPanel({ session, revKey, pinned, onPin, readOnly, focusRequestId }: EvidenceProps & { focusRequestId: string | null }) {
  const traces = useLoad(`traces:${revKey}`, () => fetchOpsEvidence({ sessionId: session.id, kind: "traces" }));
  const list = (traces.data ?? []) as OpsTrace[];
  const [selected, setSelected] = useState<string | null>(null);
  const current = list.find((t) => t.id === selected) ?? list.find((t) => t.request_id === focusRequestId) ?? list.find((t) => t.error) ?? list[0];
  if (traces.data && list.length === 0) return <p className="text-sm text-fg-muted">No traces available yet.</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <ul className="flex flex-col gap-1" aria-label="Traces">
        {list.map((t) => (
          <li key={t.id}>
            <button
              type="button"
              onClick={() => setSelected(t.id)}
              aria-current={current?.id === t.id}
              className={cn("w-full rounded-md border px-2.5 py-2 text-left", current?.id === t.id ? "border-fg bg-surface-elevated" : "border-line hover:bg-surface-hover")}
            >
              <span className="block truncate text-xs text-fg">{t.title}</span>
              <span className="font-mono text-[11px] text-fg-subtle">{clock(t.ts)} · {fmtValue(t.duration_ms, "ms")}{t.error ? " · error" : ""}</span>
            </button>
          </li>
        ))}
      </ul>
      {current ? <Waterfall trace={current} pinned={current.id in pinned} onPin={onPin} readOnly={readOnly} /> : null}
    </div>
  );
}

function Waterfall({ trace, pinned, onPin, readOnly }: { trace: OpsTrace; pinned: boolean; onPin: EvidenceProps["onPin"]; readOnly: boolean }) {
  const total = Math.max(1, trace.duration_ms);
  const depth = (id: string | null, d = 0): number => {
    const s = trace.spans.find((x) => x.id === id);
    return s?.parent ? depth(s.parent, d + 1) : d;
  };
  const ordered = [...trace.spans].sort((a, b) => a.start_ms - b.start_ms);
  const byService = new Map<string, number>();
  for (const s of trace.spans) if (!trace.spans.some((c) => c.parent === s.id)) byService.set(s.service, (byService.get(s.service) ?? 0) + s.duration_ms);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm text-fg">{trace.title}</p>
          <p className="font-mono text-[11px] text-fg-subtle">request {trace.request_id} · {fmtValue(trace.duration_ms, "ms")}</p>
        </div>
        <PinButton id={trace.id} pinned={pinned} onPin={onPin} readOnly={readOnly} />
      </div>
      <ol className="flex flex-col gap-1" aria-label="Spans">
        {ordered.map((s) => (
          <li key={s.id} className="grid grid-cols-[minmax(0,200px)_minmax(0,1fr)_72px] items-center gap-2 text-xs">
            <span className="truncate font-mono text-fg-muted" style={{ paddingLeft: depth(s.id) * 12 }}>
              {s.service} · {s.name}
            </span>
            <span className="relative h-4 rounded bg-surface">
              <span
                className={cn("absolute top-0.5 bottom-0.5 rounded-sm", s.status === "error" ? "bg-fg" : "bg-neutral-500")}
                style={{ left: `${(s.start_ms / total) * 100}%`, width: `max(2px, ${(s.duration_ms / total) * 100}%)` }}
              />
            </span>
            <span className={cn("text-right font-mono text-[11px] tabular-nums", s.status === "error" ? "text-fg" : "text-fg-subtle")}>
              {fmtValue(s.duration_ms, "ms")}{s.status === "error" ? " ✕" : ""}
            </span>
            {s.note ? <span className="col-span-2 col-start-2 -mt-0.5 text-[11px] text-fg-subtle">{s.note}</span> : null}
          </li>
        ))}
      </ol>
      <div>
        <h4 className="mb-1 text-[11px] text-fg-subtle">Self time by service (leaf spans)</h4>
        <ul className="flex flex-wrap gap-3 font-mono text-xs text-fg">
          {[...byService.entries()].map(([svc, ms]) => <li key={svc}>{svc} {Math.round((ms / total) * 100)}%</li>)}
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- deployments & diagnostics

export function DeploymentsPanel({ session, revKey, pinned, onPin, readOnly }: EvidenceProps) {
  const deps = useLoad(`deps:${revKey}`, () => fetchOpsEvidence({ sessionId: session.id, kind: "deployments" }));
  return (
    <ol className="relative flex flex-col gap-3 border-l border-line pl-4">
      {((deps.data ?? []) as OpsDeployment[]).slice().reverse().map((d) => (
        <li key={d.id} className="relative">
          <span className="absolute top-1.5 -left-[21px] size-2.5 rounded-full border border-fg bg-canvas" aria-hidden="true" />
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[13px] text-fg">
                <span className="font-mono">{d.service} {d.version}</span> · {d.summary}
              </p>
              <p className="font-mono text-[11px] text-fg-subtle">
                {clock(d.ts)} ({d.minute >= 0 ? "+" : ""}{Math.round(d.minute)}m) · {d.author}{d.by_learner ? " (your action)" : ""} · {d.status}
              </p>
              {d.changes.length ? (
                <ul className="mt-1 list-disc pl-4 text-xs text-fg-muted">{d.changes.map((c) => <li key={c}>{c}</li>)}</ul>
              ) : null}
            </div>
            {!d.by_learner ? <PinButton id={d.id} pinned={d.id in pinned} onPin={onPin} readOnly={readOnly} /> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function DiagnosticsPanel({ session, revKey, pinned, onPin, readOnly }: EvidenceProps) {
  const arts = useLoad(`arts:${revKey}`, () => fetchOpsEvidence({ sessionId: session.id, kind: "artifacts" }));
  const list = (arts.data ?? []) as OpsArtifact[];
  if (arts.data && list.length === 0) {
    return <p className="text-sm text-fg-muted">No diagnostics yet. Investigation actions (right panel) produce diagnostic output here.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {list.map((a) => (
        <section key={a.id} className="rounded-lg border border-line bg-canvas" aria-label={a.title}>
          <div className="flex items-center justify-between gap-2 border-b border-line-subtle px-3 py-2">
            <h3 className="text-xs text-fg">{a.title}</h3>
            <PinButton id={a.id} pinned={a.id in pinned} onPin={onPin} readOnly={readOnly} />
          </div>
          <pre className="overflow-x-auto p-3 font-mono text-xs leading-relaxed whitespace-pre text-fg-muted">{a.content.trim()}</pre>
        </section>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- console

export function ConsolePanel({ session, onChanged }: { session: OpsSession; onChanged: () => void }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<{ cmd: string; out: string; ok: boolean }[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  async function run(cmd: string) {
    if (!cmd.trim()) return;
    if (cmd.trim() === "help") {
      setLines((l) => [...l, { cmd, out: HELP, ok: true }]);
      setInput("");
      return;
    }
    setBusy(true);
    const res = await opsCommand({ sessionId: session.id, command: cmd, clientActionId: crypto.randomUUID() });
    setBusy(false);
    setInput("");
    const out = res.ok ? res.data.output + (res.data.performed ? "\n(Recorded as an investigation action; simulated time advanced.)" : "") : res.error;
    setLines((l) => [...l, { cmd, out, ok: res.ok && res.data.accepted }]);
    if (res.ok && res.data.performed) onChanged();
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ block: "end" }));
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="flex items-center gap-2 text-xs text-fg-subtle">
        <TerminalSquare className="size-3.5" aria-hidden="true" />
        Read-only simulation console. Allowed: logs, metrics, traces, deployments, service-status, database-status. Nothing runs on a real system.
      </p>
      <div className="max-h-[420px] min-h-48 overflow-y-auto rounded-lg border border-line bg-canvas p-3 font-mono text-xs" aria-live="polite">
        {lines.length === 0 ? <p className="text-fg-subtle">Type `help` for examples.</p> : null}
        {lines.map((l, i) => (
          <div key={i} className="mb-3">
            <p className="text-fg">$ {l.cmd}</p>
            <pre className={cn("mt-1 whitespace-pre-wrap", l.ok ? "text-fg-muted" : "text-fg")}>{l.out}</pre>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(input);
        }}
      >
        <label htmlFor="ops-console" className="sr-only">Command</label>
        <input
          id="ops-console"
          className={`${field} flex-1 font-mono`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="logs --service api --level error"
          maxLength={300}
          autoComplete="off"
          spellCheck={false}
        />
        <Button type="submit" size="sm" disabled={busy || !input.trim()}>Run</Button>
      </form>
    </div>
  );
}

const HELP = `logs [--service S] [--level info|warning|error|critical] [--request-id R] [--search TEXT] [--last N]
metrics [--service S] [--metric error_rate|p95|...] [--last N]
traces [--request-id R | --id T] [--errors]
deployments [--service S]
service-status
database-status`;
