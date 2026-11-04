"use client";

import { Clock, Loader2, Pin, Plus, Search, Send, ShieldAlert, Wrench } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { fetchOpsMessages, opsHypothesis, opsMessage, opsNotes } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { MessageText } from "@/components/ui/message-text";
import { cn } from "@/lib/cn";
import type { OpsAction, OpsMessage, OpsMode, OpsSession, OpsStatus } from "@/lib/types";
import { OPS_MODES } from "@/lib/types";

import { MODE_INFO } from "./format";

const field = "forge-field min-h-9 px-3 py-1.5 text-[13px]";

// ---------------------------------------------------------------- actions

export function ActionsPanel({
  session,
  busy,
  onAction,
  lastResult,
  readOnly,
}: {
  session: OpsSession;
  busy: string | null;
  onAction: (a: OpsAction) => void;
  lastResult: { label: string; text: string; accepted: boolean } | null;
  readOnly: boolean;
}) {
  const observe = session.actions.find((a) => a.id === "observe");
  const groups: [string, OpsAction["kind"], typeof Search][] = [
    ["Investigate", "investigate", Search],
    ["Mitigate", "mitigate", Wrench],
  ];
  return (
    <div className="flex flex-col gap-4 p-4">
      {lastResult ? (
        <div role="status" className={cn("rounded-lg border p-3 text-[13px]", lastResult.accepted ? "border-line bg-surface-elevated text-fg" : "border-dashed border-line text-fg-muted")}>
          <p className="mb-1 text-[11px] text-fg-subtle">{lastResult.accepted ? "Result" : "Not done"}: {lastResult.label}</p>
          {lastResult.text || "Done."}
        </div>
      ) : null}
      {observe ? (
        <section aria-label="Observe">
          <ActionButton a={observe} busy={busy} onAction={onAction} readOnly={readOnly} />
          <p className="mt-1 text-[11px] text-fg-subtle">{session.state.recovery.message}</p>
        </section>
      ) : null}
      <p className="text-xs leading-relaxed text-fg-subtle">
        Actions take simulated minutes and are recorded in the audit log. Mitigations change the system; not every one helps.
      </p>
      {groups.map(([title, kind, Icon]) => (
        <section key={kind} aria-label={title}>
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-fg-subtle">
            <Icon className="size-3.5" aria-hidden="true" />{title}
          </h3>
          <ul className="flex flex-col gap-1.5">
            {session.actions.filter((a) => a.kind === kind && a.id !== "observe").map((a) => (
              <li key={a.id}>
                <ActionButton a={a} busy={busy} onAction={onAction} readOnly={readOnly} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function ActionButton({ a, busy, onAction, readOnly }: { a: OpsAction; busy: string | null; onAction: (a: OpsAction) => void; readOnly: boolean }) {
  const disabled = readOnly || busy !== null || (a.done && !a.available);
  return (
    <button
      type="button"
      onClick={() => onAction(a)}
      disabled={disabled}
      title={a.reason ?? a.description}
      className={cn(
        "flex w-full items-start gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
        a.done && !a.available ? "border-line-subtle bg-canvas" : "border-line bg-surface hover:bg-surface-hover",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] text-fg">{a.label}</span>
        <span className="block text-[11px] text-fg-subtle">{a.done && !a.available ? "Done · " : ""}{a.description}</span>
        {!a.available && a.reason && !a.done ? <span className="mt-0.5 block text-[11px] text-fg-muted">{a.reason}</span> : null}
      </span>
      <span className="flex shrink-0 items-center gap-1 font-mono text-[11px] text-fg-subtle">
        {busy === a.id ? <Loader2 className="size-3 animate-spin" aria-hidden="true" /> : <Clock className="size-3" aria-hidden="true" />}
        {a.minutes}m
      </span>
    </button>
  );
}

// ---------------------------------------------------------------- notebook

export function NotebookPanel({
  session,
  onChanged,
  onPin,
  evidenceLabel,
  readOnly,
}: {
  session: OpsSession;
  onChanged: () => void;
  onPin: (id: string, pin: boolean) => void;
  evidenceLabel: (id: string) => string;
  readOnly: boolean;
}) {
  const id = useId();
  const [statement, setStatement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState(session.notes);
  const [notesState, setNotesState] = useState<"saved" | "unsaved" | "saving">("saved");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pinnedIds = Object.keys(session.pinned);

  async function addHypothesis() {
    setBusy(true);
    setError(null);
    const res = await opsHypothesis({ sessionId: session.id, number: null, statement, status: "open", evidenceIds: pinnedIds.slice(0, 12) });
    setBusy(false);
    if (!res.ok) return setError(res.error);
    setStatement("");
    onChanged();
  }

  async function setStatus(n: number, s: string, st: "open" | "supported" | "rejected", ev: string[]) {
    const res = await opsHypothesis({ sessionId: session.id, number: n, statement: s, status: st, evidenceIds: ev });
    if (!res.ok) setError(res.error);
    else onChanged();
  }

  function onNotes(v: string) {
    setNotes(v);
    setNotesState("unsaved");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setNotesState("saving");
      const res = await opsNotes({ sessionId: session.id, notes: v });
      setNotesState(res.ok ? "saved" : "unsaved");
      if (!res.ok) setError(res.error);
    }, 1000);
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      <section aria-labelledby={`${id}-h`}>
        <h3 id={`${id}-h`} className="mb-2 text-xs font-medium text-fg">Hypotheses</h3>
        {session.hypotheses.length ? (
          <ol className="mb-2 flex flex-col gap-1.5">
            {session.hypotheses.map((h) => (
              <li key={h.id} className="rounded-lg border border-line p-2.5">
                <p className={cn("text-[13px]", h.status === "rejected" ? "text-fg-subtle line-through" : "text-fg")}>H{h.number}. {h.statement}</p>
                {h.evidence_ids.length ? <p className="mt-1 font-mono text-[11px] text-fg-subtle">evidence: {h.evidence_ids.join(", ")}</p> : null}
                {!readOnly ? (
                  <div className="mt-1.5 flex gap-1" role="group" aria-label={`Status of hypothesis ${h.number}`}>
                    {(["open", "supported", "rejected"] as const).map((st) => (
                      <button
                        key={st}
                        type="button"
                        aria-pressed={h.status === st}
                        onClick={() => void setStatus(h.number, h.statement, st, h.evidence_ids)}
                        className={cn("rounded px-2 py-0.5 text-[11px]", h.status === st ? "bg-fg text-canvas" : "text-fg-muted hover:bg-surface-hover")}
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                ) : <p className="mt-1 text-[11px] text-fg-subtle">{h.status}</p>}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mb-2 text-xs text-fg-subtle">State what you think is happening and what would prove it wrong.</p>
        )}
        {!readOnly ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void addHypothesis();
            }}
            className="flex flex-col gap-2"
          >
            <label htmlFor={`${id}-st`} className="sr-only">New hypothesis</label>
            <textarea id={`${id}-st`} className={`${field} min-h-14 resize-y`} maxLength={2000} value={statement} onChange={(e) => setStatement(e.target.value)} placeholder="e.g. X started failing after change Y; if that is true, Z should also be visible in the logs." />
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" variant="secondary" disabled={busy || !statement.trim()}><Plus aria-hidden="true" />Record hypothesis</Button>
              {pinnedIds.length ? <span className="text-[11px] text-fg-subtle">Links your {pinnedIds.length} pinned item(s)</span> : null}
            </div>
          </form>
        ) : null}
      </section>

      <section>
        <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-fg"><Pin className="size-3.5" aria-hidden="true" />Pinned evidence</h3>
        {pinnedIds.length ? (
          <ul className="flex flex-col gap-1">
            {pinnedIds.map((e) => (
              <li key={e} className="flex items-center justify-between gap-2 rounded-md bg-surface px-2 py-1.5 text-xs">
                <span className="min-w-0 truncate text-fg"><span className="font-mono text-fg-subtle">{e}</span> {evidenceLabel(e)}</span>
                {!readOnly ? <button type="button" className="text-[11px] text-fg-muted hover:text-fg" onClick={() => onPin(e, false)}>Unpin</button> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-fg-subtle">Pin the logs, traces, deployments and diagnostics that support your conclusion. Key evidence counts toward the verified outcome.</p>
        )}
      </section>

      <section>
        <div className="mb-1 flex items-center justify-between">
          <label htmlFor={`${id}-notes`} className="text-xs font-medium text-fg">Investigation notes</label>
          <span className="text-[11px] text-fg-subtle" role="status">{notesState === "saved" ? "Saved" : notesState === "saving" ? "Saving…" : "Unsaved"}</span>
        </div>
        <textarea id={`${id}-notes`} className={`${field} min-h-40 resize-y`} maxLength={20000} value={notes} readOnly={readOnly} onChange={(e) => onNotes(e.target.value)} placeholder="Timeline, observations, what you ruled out and why." />
      </section>
      {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
    </div>
  );
}

// ---------------------------------------------------------------- commander

export function CommanderPanel({ session, status, evidenceLabel }: { session: OpsSession; status: OpsStatus | null; evidenceLabel: (id: string) => string }) {
  const id = useId();
  const [messages, setMessages] = useState<OpsMessage[] | null>(null);
  const [mode, setMode] = useState<OpsMode>(session.mode);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const configured = status?.llm.configured ?? false;

  useEffect(() => {
    let alive = true;
    fetchOpsMessages(session.id).then((r) => {
      if (alive && r.ok) setMessages(r.data);
    });
    return () => {
      alive = false;
    };
  }, [session.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages?.length]);

  async function send() {
    if (!draft.trim()) return;
    setBusy(true);
    setError(null);
    pending.current ??= crypto.randomUUID();
    const res = await opsMessage({ sessionId: session.id, content: draft, clientMessageId: pending.current, mode });
    setBusy(false);
    if (!res.ok) return setError(res.error);
    pending.current = null;
    setDraft("");
    setMessages((m) => {
      const seen = new Set((m ?? []).map((x) => x.id));
      return [...(m ?? []), ...res.data.messages.filter((x) => !seen.has(x.id))];
    });
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line-subtle p-3">
        <label htmlFor={`${id}-mode`} className="mb-1 block text-[11px] text-fg-subtle">Mode</label>
        <select id={`${id}-mode`} className={field} value={mode} onChange={(e) => setMode(e.target.value as OpsMode)}>
          {OPS_MODES.map((m) => <option key={m} value={m}>{MODE_INFO[m].label}</option>)}
        </select>
        <p className="mt-1 text-[11px] text-fg-subtle">{MODE_INFO[mode].description}</p>
        {configured ? (
          <p className="mt-1 font-mono text-[11px] text-fg-subtle">AI: {status?.llm.provider}/{status?.llm.model}</p>
        ) : (
          <p className="mt-2 rounded-md border border-line bg-surface-elevated p-2 text-[11px] text-fg-muted">
            No AI provider configured on the API (FORGE_LLM_*). Messages are saved and answered with an “unavailable” notice.
          </p>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3" aria-live="polite">
        {messages === null ? <p className="text-xs text-fg-subtle">Loading…</p> : null}
        {messages?.length === 0 ? (
          <p className="text-xs leading-relaxed text-fg-muted">
            Share your current hypothesis and the evidence behind it. The commander only knows what the simulation has shown you;
            it can&apos;t run actions or see hidden data, and it won&apos;t hand you the root cause.
          </p>
        ) : null}
        <ol className="flex flex-col gap-3">
          {(messages ?? []).map((m) => (
            <li
              key={m.id}
              className={cn(
                "rounded-lg px-3 py-2.5 text-[13px] leading-relaxed",
                m.role === "learner" && "ml-6 bg-surface-elevated text-fg",
                m.role === "commander" && "mr-4 border border-line text-fg",
                m.role === "system" && "text-xs text-fg-muted",
              )}
            >
              <p className="mb-1 flex items-center gap-1 text-[11px] text-fg-subtle">
                {m.role === "commander" ? <ShieldAlert className="size-3" aria-hidden="true" /> : null}
                {m.role === "learner" ? "You" : m.role === "commander" ? `Incident commander (AI) · ${MODE_INFO[m.mode].label}` : "FORGE"}
              </p>
              <MessageText text={m.content} />
              {m.cited_evidence.length ? (
                <p className="mt-1.5 font-mono text-[11px] text-fg-subtle">cites: {m.cited_evidence.map((e) => `${e} (${evidenceLabel(e)})`).join(", ")}</p>
              ) : null}
            </li>
          ))}
          {busy ? (
            <li className="mr-4 flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-xs text-fg-muted">
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />The commander is reviewing your evidence…
            </li>
          ) : null}
        </ol>
        <div ref={endRef} />
      </div>
      <form
        className="border-t border-line-subtle p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label htmlFor={`${id}-msg`} className="sr-only">Message to the incident commander</label>
        <textarea
          id={`${id}-msg`}
          className={`${field} min-h-20 resize-y`}
          maxLength={6000}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            pending.current = null;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="My hypothesis is… because…"
        />
        {error ? <p role="alert" className="mt-1 text-xs text-fg">{error}</p> : null}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[11px] text-fg-subtle">⌘/Ctrl + Enter to send</span>
          <Button type="submit" size="sm" disabled={busy || !draft.trim()}><Send aria-hidden="true" />Send</Button>
        </div>
      </form>
    </div>
  );
}
