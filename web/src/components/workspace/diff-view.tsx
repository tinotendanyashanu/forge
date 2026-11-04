"use client";

import { ChevronDown, ChevronRight, MessageSquarePlus } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import type { FileDiff } from "@/lib/workspace-types";

const STATUS: Record<FileDiff["status"], string> = { added: "Added", modified: "Modified", deleted: "Deleted" };

/**
 * Structured unified diff. On the PR page, `renderAfter(path, newLine)` places
 * inline comments under a line and `onComment(path, newLine)` opens a composer.
 */
export function DiffView({
  diffs,
  emptyText = "No changes.",
  onComment,
  renderAfter,
  defaultOpen = true,
}: {
  diffs: FileDiff[];
  emptyText?: string;
  onComment?: (path: string, line: number) => void;
  renderAfter?: (path: string, line: number | null) => ReactNode;
  defaultOpen?: boolean;
}) {
  if (!diffs.length) {
    return <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-fg-muted">{emptyText}</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {diffs.map((d) => <FileBlock key={d.path} diff={d} onComment={onComment} renderAfter={renderAfter} defaultOpen={defaultOpen} />)}
    </div>
  );
}

function FileBlock({
  diff,
  onComment,
  renderAfter,
  defaultOpen,
}: {
  diff: FileDiff;
  onComment?: (path: string, line: number) => void;
  renderAfter?: (path: string, line: number | null) => ReactNode;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="overflow-hidden rounded-xl border border-line bg-canvas">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 border-b border-line-subtle bg-surface px-3 py-2 text-left hover:bg-surface-hover"
      >
        {open ? <ChevronDown className="size-4 text-fg-subtle" aria-hidden="true" /> : <ChevronRight className="size-4 text-fg-subtle" aria-hidden="true" />}
        <span className="min-w-0 flex-1 truncate font-mono text-[13px] text-fg">{diff.path}</span>
        <span className="text-xs text-fg-subtle">{STATUS[diff.status]}</span>
        <span className="font-mono text-xs text-fg tabular-nums">+{diff.additions}</span>
        <span className="font-mono text-xs text-fg-subtle tabular-nums">−{diff.deletions}</span>
      </button>
      {open ? (
        <div className="overflow-x-auto">
          {renderAfter ? renderAfter(diff.path, null) : null}
          <table className="w-full border-collapse font-mono text-[12.5px] leading-5">
            <tbody>
              {diff.hunks.map((h, hi) => (
                <HunkRows key={hi} hunk={h} first={hi === 0} path={diff.path} onComment={onComment} renderAfter={renderAfter} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function HunkRows({
  hunk,
  first,
  path,
  onComment,
  renderAfter,
}: {
  hunk: FileDiff["hunks"][number];
  first: boolean;
  path: string;
  onComment?: (path: string, line: number) => void;
  renderAfter?: (path: string, line: number | null) => ReactNode;
}) {
  return (
    <>
      {!first ? (
        <tr><td colSpan={4} className="border-y border-line-subtle bg-surface px-3 py-0.5 text-[11px] text-fg-subtle">⋯</td></tr>
      ) : null}
      {hunk.lines.map((l, i) => {
        const after = renderAfter && l.new !== null ? renderAfter(path, l.new) : null;
        return (
          <FragmentRow key={i}>
            <tr
              className={cn(
                "group",
                l.type === "add" && "bg-white/[0.06]",
                l.type === "del" && "bg-black/40 text-fg-subtle",
              )}
            >
              <td className="w-10 select-none px-2 text-right text-fg-subtle tabular-nums">{l.old ?? ""}</td>
              <td className="w-10 select-none px-2 text-right text-fg-subtle tabular-nums">
                {onComment && l.new !== null ? (
                  <button
                    type="button"
                    onClick={() => onComment(path, l.new!)}
                    aria-label={`Comment on ${path} line ${l.new}`}
                    className="inline-flex w-full items-center justify-end gap-1 rounded hover:text-fg focus-visible:text-fg"
                  >
                    <MessageSquarePlus className="size-3 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100" aria-hidden="true" />
                    {l.new}
                  </button>
                ) : (l.new ?? "")}
              </td>
              <td className="w-5 select-none text-center text-fg-subtle" aria-hidden="true">
                {l.type === "add" ? "+" : l.type === "del" ? "−" : ""}
              </td>
              <td className={cn("pr-4 whitespace-pre", l.type === "add" ? "text-fg" : "")}>
                <span className="sr-only">{l.type === "add" ? "added: " : l.type === "del" ? "removed: " : ""}</span>
                {l.text || " "}
              </td>
            </tr>
            {after ? (
              <tr><td colSpan={4} className="border-y border-line-subtle bg-surface px-3 py-2 font-sans">{after}</td></tr>
            ) : null}
          </FragmentRow>
        );
      })}
    </>
  );
}

function FragmentRow({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
