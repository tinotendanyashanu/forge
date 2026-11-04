"use client";

import { CircleStop, Clock, Loader2, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { fetchOpsEvidence, fetchOpsLogs, fetchOpsSession, opsAbandon, opsAction, opsPin, opsReset } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { ActionResult, OpsAction, OpsArtifact, OpsDeployment, OpsSession, OpsStatus, OpsTrace } from "@/lib/types";

import { ConsolePanel, DeploymentsPanel, DiagnosticsPanel, LogsPanel, MetricsPanel, OverviewPanel, TracesPanel } from "./evidence";
import { LEVEL_LABEL, STATUS_LABEL, STATUS_STEPS, clock } from "./format";
import { PostmortemPanel, ResolvePanel, SummaryPanel, TimelinePanel } from "./resolution";
import { ActionsPanel, CommanderPanel, NotebookPanel } from "./side";
import { useLoad } from "./use-load";

type MainTab = "overview" | "metrics" | "logs" | "traces" | "deployments" | "diagnostics" | "console" | "timeline" | "resolve" | "summary" | "postmortem";
type SideTab = "actions" | "notebook" | "commander";
type MobileView = "main" | "side";

export function OpsWorkspace({ initial, status }: { initial: OpsSession; status: OpsStatus | null }) {
  const router = useRouter();
  const [session, setSession] = useState(initial);
  const closed = ["resolved", "postmortem", "abandoned"].includes(session.state.status);
  const [tab, setTab] = useState<MainTab>(closed ? "summary" : "overview");
  const [side, setSide] = useState<SideTab>("actions");
  const [mobile, setMobile] = useState<MobileView>("main");
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<{ label: string; text: string; accepted: boolean } | null>(null);
  const [traceFocus, setTraceFocus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const revKey = `${session.revision}:${session.state.minute}`;

  const labels = useLoad(`labels:${revKey}`, async (): Promise<ActionResult<Record<string, string>>> => {
    const [logs, traces, deps, arts] = await Promise.all([
      fetchOpsLogs({ sessionId: session.id }),
      fetchOpsEvidence({ sessionId: session.id, kind: "traces" }),
      fetchOpsEvidence({ sessionId: session.id, kind: "deployments" }),
      fetchOpsEvidence({ sessionId: session.id, kind: "artifacts" }),
    ]);
    const out: Record<string, string> = {};
    if (logs.ok) for (const l of logs.data) out[l.id] = `${l.service} ${l.level}: ${l.message.slice(0, 60)}`;
    if (traces.ok) for (const t of traces.data as OpsTrace[]) out[t.id] = `trace ${t.title}`;
    if (deps.ok) for (const d of deps.data as OpsDeployment[]) out[d.id] = `${d.service} ${d.version}`;
    if (arts.ok) for (const a of arts.data as OpsArtifact[]) out[a.id] = a.title;
    return { ok: true, data: out };
  });
  const evidenceLabel = useCallback((id: string) => labels.data?.[id] ?? "", [labels.data]);

  const refresh = useCallback(async () => {
    const r = await fetchOpsSession(session.id);
    if (r.ok) setSession(r.data);
  }, [session.id]);

  async function act(a: OpsAction) {
    setBusy(a.id);
    setError(null);
    const r = await opsAction({ sessionId: session.id, actionId: a.id, clientActionId: crypto.randomUUID() });
    setBusy(null);
    if (!r.ok) return setError(r.error);
    setSession(r.data.session);
    const res = r.data.result;
    setLast({ label: a.label, accepted: res.accepted, text: res.accepted ? res.outcome || (res.revealed.length ? "New evidence is available." : "") : res.reason ?? "" });
    if (res.accepted && res.revealed.length && a.kind === "investigate") setTab(res.revealed.some((id) => id.startsWith("log")) && !res.revealed.some((id) => !id.startsWith("log")) ? "logs" : "diagnostics");
  }

  async function pin(id: string, on: boolean) {
    const r = await opsPin({ sessionId: session.id, evidenceId: id, pinned: on });
    if (!r.ok) return setError(r.error);
    setSession((s) => ({ ...s, pinned: r.data.pinned }));
  }

  async function end() {
    if (!confirmEnd) {
      setConfirmEnd(true);
      return;
    }
    setConfirmEnd(false);
    setBusy("abandon");
    const r = await opsAbandon(session.id);
    setBusy(null);
    if (r.ok) {
      setSession(r.data);
      setTab("summary");
    } else setError(r.error);
  }

  async function reset() {
    setBusy("reset");
    const r = await opsReset(session.id);
    setBusy(null);
    if (r.ok) router.push(`/ops/sessions/${r.data.id}`);
    else setError(r.error);
  }

  const tabs: [MainTab, string, boolean][] = [
    ["overview", "Overview", true],
    ["metrics", "Metrics", true],
    ["logs", `Logs (${session.evidence_counts.logs})`, true],
    ["traces", `Traces (${session.evidence_counts.traces})`, true],
    ["deployments", "Deployments", true],
    ["diagnostics", `Diagnostics (${session.evidence_counts.artifacts})`, true],
    ["console", "Console", !closed],
    ["timeline", "Timeline & replay", true],
    ["resolve", "Resolve", session.state.status === "monitoring"],
    ["summary", "Outcome & debrief", closed],
    ["postmortem", "Postmortem", session.state.status === "resolved" || session.state.status === "postmortem"],
  ];
  const evProps = { session, revKey, pinned: session.pinned, onPin: pin, readOnly: closed };
  const stepIndex = STATUS_STEPS.indexOf(session.state.status);
  const condition = session.state.condition;

  const main = (
    <div className="flex min-h-0 flex-col">
      <div role="tablist" aria-label="Investigation views" className="flex shrink-0 gap-1 overflow-x-auto border-b border-line-subtle px-3 pt-2">
        {tabs.filter(([, , show]) => show).map(([k, label]) => (
          <button key={k} role="tab" type="button" aria-selected={tab === k} onClick={() => setTab(k)}
            className={cn("shrink-0 rounded-t-md border-b-2 px-3 py-2 text-[13px] whitespace-nowrap", tab === k ? "border-fg text-fg" : "border-transparent text-fg-muted hover:text-fg")}>
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "overview" ? <OverviewPanel {...evProps} /> : null}
        {tab === "metrics" ? <MetricsPanel {...evProps} /> : null}
        {tab === "logs" ? <LogsPanel {...evProps} onTrace={(rid) => { setTraceFocus(rid); setTab("traces"); }} /> : null}
        {tab === "traces" ? <TracesPanel {...evProps} focusRequestId={traceFocus} /> : null}
        {tab === "deployments" ? <DeploymentsPanel {...evProps} /> : null}
        {tab === "diagnostics" ? <DiagnosticsPanel {...evProps} /> : null}
        {tab === "console" ? <ConsolePanel session={session} onChanged={() => void refresh()} /> : null}
        {tab === "timeline" ? <TimelinePanel session={session} /> : null}
        {tab === "resolve" ? <ResolvePanel session={session} onResolved={(s) => { setSession(s); setTab("summary"); }} /> : null}
        {tab === "summary" ? <SummaryPanel session={session} evidenceLabel={evidenceLabel} /> : null}
        {tab === "postmortem" ? <PostmortemPanel session={session} onStarted={() => void refresh()} /> : null}
      </div>
    </div>
  );

  const sidePanel = (
    <div className="flex min-h-0 flex-col">
      <div role="tablist" aria-label="Incident tools" className="flex shrink-0 gap-1 border-b border-line-subtle px-2 pt-2">
        {([["actions", "Actions"], ["notebook", "Notebook"], ["commander", "AI commander"]] as const).map(([k, l]) => (
          <button key={k} role="tab" type="button" aria-selected={side === k} onClick={() => setSide(k)}
            className={cn("rounded-t-md border-b-2 px-3 py-2 text-[13px]", side === k ? "border-fg text-fg" : "border-transparent text-fg-muted hover:text-fg")}>
            {l}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="min-h-0 flex-1 overflow-y-auto">
        {side === "actions" ? <ActionsPanel session={session} busy={busy} onAction={(a) => void act(a)} lastResult={last} readOnly={closed} /> : null}
        {side === "notebook" ? <NotebookPanel key={session.id} session={session} onChanged={() => void refresh()} onPin={(id, on) => void pin(id, on)} evidenceLabel={evidenceLabel} readOnly={closed} /> : null}
        {side === "commander" ? <CommanderPanel key={session.id} session={session} status={status} evidenceLabel={evidenceLabel} /> : null}
      </div>
    </div>
  );

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col md:h-dvh">
      <header className="flex flex-col gap-2 border-b border-line-subtle px-4 py-2.5">
        <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs text-fg-subtle">
              <a href="/ops" className="hover:text-fg">FORGE OPS</a> / {LEVEL_LABEL[session.scenario.level]} · scenario v{session.scenario.version}
              {!session.scenario.current_version ? " (an earlier version)" : ""}
            </p>
            <h1 className="truncate text-[15px] font-medium text-fg">{session.scenario.title}</h1>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs text-fg-muted">
            <span className="flex items-center gap-1" title="Simulated clock"><Clock className="size-3.5" aria-hidden="true" />{clock(session.state.clock)} UTC · +{session.state.minute}m</span>
          </div>
          <div className="flex gap-1.5">
            <Button size="sm" variant="ghost" onClick={() => void reset()} disabled={busy !== null} title="End this attempt (kept in history) and start a fresh one">
              {busy === "reset" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}Reset
            </Button>
            {!closed ? (
              <Button size="sm" variant="ghost" onClick={() => void end()} disabled={busy !== null} title="End the attempt and see the debrief; no evidence is recorded">
                <CircleStop aria-hidden="true" />{confirmEnd ? "Confirm: end attempt" : "End attempt"}
              </Button>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ol className="flex flex-wrap items-center gap-1 text-[11px]" aria-label="Incident state">
            {STATUS_STEPS.map((s, i) => (
              <li key={s} aria-current={session.state.status === s ? "step" : undefined}
                className={cn("rounded-full border px-2 py-0.5", session.state.status === s ? "border-fg bg-fg text-canvas" : i < stepIndex ? "border-line text-fg-muted" : "border-line-subtle text-fg-subtle")}>
                {STATUS_LABEL[s]}
              </li>
            ))}
            {session.state.status === "abandoned" ? <li className="rounded-full border border-fg px-2 py-0.5 text-fg">Ended</li> : null}
          </ol>
          <p className="min-w-0 flex-1 truncate text-xs text-fg-muted" role="status" aria-live="polite">
            <span className="text-fg">{condition.label}.</span> {condition.summary}
          </p>
        </div>
        {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
      </header>

      <div role="tablist" aria-label="Workspace panels" className="flex border-b border-line-subtle lg:hidden">
        {([["main", "Investigate"], ["side", "Actions & AI"]] as const).map(([k, l]) => (
          <button key={k} role="tab" type="button" aria-selected={mobile === k} onClick={() => setMobile(k)}
            className={cn("flex-1 border-b-2 py-2.5 text-sm", mobile === k ? "border-fg text-fg" : "border-transparent text-fg-muted")}>
            {l}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_400px]">
        <section aria-label="Investigation" className={cn("min-h-0 flex-col lg:flex", mobile === "main" ? "flex" : "hidden")}>{main}</section>
        <aside aria-label="Actions and AI" className={cn("min-h-0 flex-col border-line-subtle lg:flex lg:border-l", mobile === "side" ? "flex" : "hidden")}>{sidePanel}</aside>
      </div>
    </div>
  );
}

