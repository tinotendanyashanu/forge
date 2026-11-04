import { Bot, ShieldCheck, ShieldOff } from "lucide-react";

import type { WorkspaceStatus } from "@/lib/workspace-types";

/** States plainly whether code really runs, and in what, and whether AI review is available. */
export function WorkspaceStatusBanner({ status }: { status: WorkspaceStatus | null }) {
  if (!status) {
    return <p role="status" className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg-muted">Execution status unavailable: the API couldn&apos;t be reached.</p>;
  }
  const e = status.execution;
  const ready = e.backend === "docker" && e.verified && e.worker_online;
  const text = ready
    ? "Tests run in an isolated, self-verified container sandbox (no network, read-only, non-root, resource-limited)."
    : e.backend === "disabled"
      ? "Code execution is disabled on this server. You can read and edit projects, but tests can't run."
      : e.backend === "mock"
        ? "Mock runner: jobs go through the queue but nothing executes. Results are never evidence."
        : !e.worker_online
          ? "No execution worker is online. Jobs will wait in the queue until one starts."
          : `The sandbox failed its security self-check, so nothing runs: ${e.problems.join("; ")}`;
  return (
    <div role="status" className="flex flex-col gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-fg-muted sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-start gap-2">
        {ready ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-fg" aria-hidden="true" /> : <ShieldOff className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
        <span>{text}</span>
      </p>
      <p className="flex shrink-0 items-center gap-2 text-fg-subtle">
        <Bot className="size-4" aria-hidden="true" />
        {status.llm.configured ? `AI review: ${status.llm.model}` : "AI review not configured"}
      </p>
    </div>
  );
}
