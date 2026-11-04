"use client";

import { ChevronLeft, FilePlus2, History } from "lucide-react";
import { useId, useState } from "react";

import { fetchAdrRevisions, saveAdr } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { Adr, AdrContent, AdrStatus } from "@/lib/types";

const field = "forge-field min-h-9 px-3 py-1.5 text-[13px]";
const labelCls = "mb-1.5 block text-xs font-medium text-fg-muted";
const STATUSES: AdrStatus[] = ["proposed", "accepted", "superseded", "rejected"];

const BLANK: AdrContent = {
  title: "",
  context: "",
  decision: "",
  alternatives: [],
  reasons: "",
  tradeoffs: "",
  consequences: "",
  risks: "",
  revisit_when: "",
};

const FIELDS: [keyof AdrContent, string, string][] = [
  ["context", "Context", "What forces this decision? Which requirement or constraint?"],
  ["decision", "Decision", "What did you decide?"],
  ["reasons", "Reasons", "Why this option over the others?"],
  ["tradeoffs", "Trade-offs", "What do you give up?"],
  ["consequences", "Consequences", "What changes as a result?"],
  ["risks", "Risks", "What could go wrong?"],
  ["revisit_when", "Revisit when", "Which signal would make you reconsider?"],
];

export function NotesPanel({
  projectId,
  explanation,
  onExplanation,
  initialAdrs,
}: {
  projectId: string;
  explanation: string;
  onExplanation: (v: string) => void;
  initialAdrs: Adr[];
}) {
  const id = useId();
  const [adrs, setAdrs] = useState(initialAdrs);
  const [editing, setEditing] = useState<Adr | "new" | null>(null);

  if (editing) {
    return (
      <AdrEditor
        projectId={projectId}
        adr={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
        onSaved={(a) => {
          setAdrs((cur) => [...cur.filter((x) => x.number !== a.number), a].sort((x, y) => x.number - y.number));
          setEditing(null);
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4">
      <section>
        <label htmlFor={`${id}-explain`} className="mb-1.5 block text-xs font-medium text-fg">
          Design explanation
        </label>
        <p className="mb-2 text-xs leading-relaxed text-fg-subtle">
          Walk through the main flows and justify your choices. The reviewer quotes this as evidence. Saved automatically.
        </p>
        <textarea
          id={`${id}-explain`}
          value={explanation}
          maxLength={20000}
          onChange={(e) => onExplanation(e.target.value)}
          placeholder="Clients reach the API through the load balancer. Writes go to PostgreSQL because…"
          className={`${field} min-h-56 resize-y leading-relaxed`}
        />
        <p className="mt-1 text-right font-mono text-[11px] text-fg-subtle">{explanation.length}/20000</p>
      </section>

      <section aria-labelledby={`${id}-adrs`}>
        <div className="mb-2 flex items-center justify-between">
          <h3 id={`${id}-adrs`} className="text-xs font-medium text-fg">Decision records</h3>
          <Button size="sm" variant="secondary" onClick={() => setEditing("new")}>
            <FilePlus2 aria-hidden="true" />New ADR
          </Button>
        </div>
        {adrs.length === 0 ? (
          <p className="text-xs leading-relaxed text-fg-subtle">
            Record significant decisions: context, alternatives, trade-offs and when to revisit. The AI reviewer questions you on them.
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {adrs.map((a) => (
              <li key={a.number}>
                <button
                  type="button"
                  onClick={() => setEditing(a)}
                  className="flex w-full items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-left hover:bg-surface-hover"
                >
                  <span className="font-mono text-[11px] text-fg-subtle">ADR-{a.number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-fg">{a.content.title}</span>
                    <span className="text-[11px] text-fg-subtle">{a.status} · revision {a.revision}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function AdrEditor({
  projectId,
  adr,
  onClose,
  onSaved,
}: {
  projectId: string;
  adr: Adr | null;
  onClose: () => void;
  onSaved: (a: Adr) => void;
}) {
  const id = useId();
  const [content, setContent] = useState<AdrContent>(adr?.content ?? BLANK);
  const [alternatives, setAlternatives] = useState((adr?.content.alternatives ?? []).join("\n"));
  const [status, setStatus] = useState<AdrStatus>(adr?.status ?? "proposed");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof fetchAdrRevisions>> | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    const res = await saveAdr({
      projectId,
      number: adr?.number ?? null,
      content: { ...content, alternatives: alternatives.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 8) },
      status,
      baseRevision: adr?.revision ?? null,
    });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.error);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-3 p-4"
    >
      <div className="flex items-center justify-between">
        <button type="button" onClick={onClose} className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg">
          <ChevronLeft className="size-3.5" aria-hidden="true" />Back
        </button>
        <span className="text-xs text-fg-subtle">{adr ? `ADR-${adr.number} · revision ${adr.revision}` : "New decision record"}</span>
      </div>
      <div>
        <label htmlFor={`${id}-title`} className={labelCls}>Title</label>
        <input id={`${id}-title`} required minLength={3} maxLength={160} className={field} value={content.title}
          onChange={(e) => setContent({ ...content, title: e.target.value })} placeholder="Use PostgreSQL as the system of record" />
      </div>
      <div>
        <label htmlFor={`${id}-status`} className={labelCls}>Status</label>
        <select id={`${id}-status`} className={field} value={status} onChange={(e) => setStatus(e.target.value as AdrStatus)}>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {FIELDS.slice(0, 2).map(([k, l, ph]) => (
        <div key={k}>
          <label htmlFor={`${id}-${k}`} className={labelCls}>{l}</label>
          <textarea id={`${id}-${k}`} required className={`${field} min-h-16 resize-y`} maxLength={4000} placeholder={ph}
            value={content[k] as string} onChange={(e) => setContent({ ...content, [k]: e.target.value })} />
        </div>
      ))}
      <div>
        <label htmlFor={`${id}-alts`} className={labelCls}>Alternatives considered (one per line)</label>
        <textarea id={`${id}-alts`} className={`${field} min-h-14 resize-y`} value={alternatives} onChange={(e) => setAlternatives(e.target.value)} placeholder={"DynamoDB\nRedis as primary store"} />
      </div>
      {FIELDS.slice(2).map(([k, l, ph]) => (
        <div key={k}>
          <label htmlFor={`${id}-${k}`} className={labelCls}>{l}</label>
          <textarea id={`${id}-${k}`} className={`${field} min-h-12 resize-y`} maxLength={4000} placeholder={ph}
            value={content[k] as string} onChange={(e) => setContent({ ...content, [k]: e.target.value })} />
        </div>
      ))}
      {error ? <p role="alert" className="text-xs text-fg">{error}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" disabled={busy}>{busy ? "Saving…" : adr ? "Save new revision" : "Create ADR"}</Button>
        {adr ? (
          <Button size="sm" variant="ghost" onClick={async () => setHistory(await fetchAdrRevisions({ projectId, number: adr.number }))}>
            <History aria-hidden="true" />Revisions
          </Button>
        ) : null}
      </div>
      {history ? (
        history.ok ? (
          <ol className="flex flex-col gap-2 border-t border-line-subtle pt-3">
            {history.data.map((r) => (
              <li key={r.revision} className="rounded-lg border border-line-subtle p-2.5 text-xs">
                <p className="text-fg-subtle">Revision {r.revision} · {r.status} · {new Date(r.created_at).toLocaleString()}</p>
                <p className="mt-1 text-fg">{r.content.title}</p>
                <p className="mt-0.5 line-clamp-3 text-fg-muted">{r.content.decision}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p role="alert" className="text-xs text-fg">{history.error}</p>
        )
      ) : null}
    </form>
  );
}
