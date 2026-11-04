import { ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";

import type { ExecutionStatus } from "@/lib/types";

/** States plainly whether code runs, and under what isolation. */
export function ExecutionBanner({ status, compact = false }: { status: ExecutionStatus | null; compact?: boolean }) {
  if (!status) {
    return <Note icon="warn" title="Execution status unavailable" body="The API couldn't be reached." />;
  }
  if (status.backend === "disabled") {
    return (
      <Note
        icon="warn"
        title="Code execution is disabled"
        body="You can read challenges and write drafts, but nothing runs on this server. An administrator can enable the sandbox worker."
      />
    );
  }
  if (status.backend === "mock") {
    return (
      <Note
        icon="warn"
        title="Mock runner: your code is never executed"
        body="Runs and submissions go through the real queue, but every test is reported as not executed. Nothing counts as evidence."
      />
    );
  }
  if (!status.worker_online) {
    return (
      <Note
        icon="warn"
        title="No execution worker is online"
        body="Jobs will wait in the queue until a worker starts (python -m app.coding.worker)."
      />
    );
  }
  if (!status.verified) {
    return (
      <Note
        icon="alert"
        title="Sandbox failed its security self-check"
        body={`Nothing will run. ${status.problems.join("; ")}`}
      />
    );
  }
  if (compact) return null;
  return (
    <Note
      icon="ok"
      title="Sandboxed execution"
      body="Each run uses a fresh container with no network, a read-only filesystem, no privileges and strict CPU, memory and time limits. Isolation is container-based and acknowledged for single-user use only."
    />
  );
}

function Note({ icon, title, body }: { icon: "ok" | "warn" | "alert"; title: string; body: string }) {
  const Icon = icon === "ok" ? ShieldCheck : icon === "alert" ? ShieldAlert : TriangleAlert;
  return (
    <div role={icon === "ok" ? "note" : "status"} className="flex items-start gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
      <Icon className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
      <p className="text-fg-muted">
        <span className="font-medium text-fg">{title}.</span> {body}
      </p>
    </div>
  );
}
