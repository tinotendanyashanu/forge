"use client";

import { ChevronDown, ChevronRight, FileCode, FilePlus, Folder, FolderOpen, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { FileMeta } from "@/lib/workspace-types";

type Node = { name: string; path: string; children: Node[]; file?: FileMeta };

function build(files: FileMeta[]): Node[] {
  const root: Node = { name: "", path: "", children: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let node = root;
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let child = node.children.find((c) => c.name === part && !!c.file === (i === parts.length - 1));
      if (!child) {
        child = { name: part, path, children: [], file: i === parts.length - 1 ? f : undefined };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (n: Node) => {
    n.children.sort((a, b) => (a.file ? 1 : 0) - (b.file ? 1 : 0) || a.name.localeCompare(b.name));
    n.children.forEach(sort);
  };
  sort(root);
  return root.children;
}

const MARK: Record<FileMeta["status"], string> = { unchanged: "", modified: "M", added: "A" };

export function FileTree({
  files,
  active,
  dirty,
  onOpen,
  onCreate,
  onDelete,
  disabled,
}: {
  files: FileMeta[];
  active: string | null;
  dirty: Set<string>;
  onOpen: (path: string) => void;
  onCreate: (path: string) => Promise<string | null>;
  onDelete: (path: string) => Promise<string | null>;
  disabled?: boolean;
}) {
  const tree = useMemo(() => build(files), [files]);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  function toggle(path: string) {
    setClosed((s) => {
      const next = new Set(s);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const path = name.trim().replace(/^\/+/, "");
    if (!path) return;
    const err = await onCreate(path);
    if (err) setError(err);
    else {
      setCreating(false);
      setName("");
      setError(null);
    }
  }

  function render(nodes: Node[], depth: number) {
    return nodes.map((n) => {
      if (!n.file) {
        const open = !closed.has(n.path);
        return (
          <li key={`d:${n.path}`} role="treeitem" aria-expanded={open} aria-selected={false}>
            <button
              type="button"
              onClick={() => toggle(n.path)}
              className="flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-[13px] text-fg-muted hover:bg-surface-hover hover:text-fg"
              style={{ paddingLeft: 6 + depth * 12 }}
            >
              {open ? <ChevronDown className="size-3.5 shrink-0" aria-hidden="true" /> : <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />}
              {open ? <FolderOpen className="size-3.5 shrink-0" aria-hidden="true" /> : <Folder className="size-3.5 shrink-0" aria-hidden="true" />}
              <span className="truncate">{n.name}</span>
            </button>
            {open ? <ul role="group">{render(n.children, depth + 1)}</ul> : null}
          </li>
        );
      }
      const isActive = n.path === active;
      const mark = MARK[n.file.status];
      return (
        <li key={`f:${n.path}`} role="treeitem" aria-selected={isActive}>
          <button
            type="button"
            onClick={() => onOpen(n.path)}
            aria-current={isActive ? "true" : undefined}
            className={cn(
              "flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-[13px] hover:bg-surface-hover",
              isActive ? "bg-surface-hover text-fg" : "text-fg-muted hover:text-fg",
            )}
            style={{ paddingLeft: 20 + depth * 12 }}
          >
            <FileCode className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate">{n.name}</span>
            {dirty.has(n.path) ? <span className="size-1.5 shrink-0 rounded-full bg-fg" aria-label="unsaved" /> : null}
            {mark ? <span className="font-mono text-[10px] text-fg-subtle" aria-label={n.file.status}>{mark}</span> : null}
          </button>
        </li>
      );
    });
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between px-2 py-2">
        <h2 className="text-[11px] font-medium tracking-wide text-fg-subtle uppercase">Files</h2>
        <div className="flex gap-0.5">
          <button
            type="button"
            onClick={() => { setCreating((c) => !c); setError(null); }}
            disabled={disabled}
            aria-label="New file"
            title="New file"
            className="rounded-md p-1 text-fg-muted hover:bg-surface-hover hover:text-fg disabled:opacity-40"
          >
            <FilePlus className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={disabled || !active}
            aria-label={active ? `Delete ${active}` : "Delete file"}
            title="Delete the open file"
            className="rounded-md p-1 text-fg-muted hover:bg-surface-hover hover:text-fg disabled:opacity-40"
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
      {creating ? (
        <form onSubmit={create} className="mx-2 mb-2 flex flex-col gap-1.5">
          <label htmlFor="new-file" className="text-[11px] text-fg-subtle">Path, e.g. app/utils.py</label>
          <input
            id="new-file"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setCreating(false)}
            className="h-8 rounded-md border border-line bg-canvas px-2 font-mono text-xs text-fg focus:border-neutral-500 focus:outline-none"
          />
          {error ? <p role="alert" className="text-[11px] text-fg">{error}</p> : null}
          <div className="flex gap-1.5">
            <Button type="submit" size="sm">Create</Button>
            <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
          </div>
        </form>
      ) : null}
      {confirmDelete && active ? (
        <div role="alertdialog" aria-label="Confirm delete" className="mx-2 mb-2 rounded-lg border border-line bg-surface p-2 text-xs text-fg-muted">
          Delete <span className="font-mono text-fg">{active}</span>? A snapshot keeps earlier versions.
          <div className="mt-2 flex gap-1.5">
            <Button size="sm" variant="secondary" onClick={async () => {
              const err = await onDelete(active);
              setConfirmDelete(false);
              if (err) setError(err);
            }}>Delete</Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
          </div>
        </div>
      ) : null}
      {error && !creating ? <p role="alert" className="mx-2 mb-2 text-[11px] text-fg">{error}</p> : null}
      <ul role="tree" aria-label="Project files" className="min-h-0 flex-1 overflow-y-auto px-1 pb-3">
        {render(tree, 0)}
      </ul>
    </div>
  );
}
