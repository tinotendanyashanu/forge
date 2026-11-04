import { CircleCheck, CircleDot, GitMerge, GitPullRequestClosed, ShieldCheck, ShieldOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { LEVEL_LABEL, TASK_TYPE_LABEL, type EngLevel, type PullRequestSummary } from "@/lib/workspace-types";

export function LevelBadge({ level }: { level: EngLevel }) {
  return <Badge>{LEVEL_LABEL[level]}</Badge>;
}

export function TaskTypeBadge({ type }: { type: string }) {
  return <Badge>{TASK_TYPE_LABEL[type] ?? type}</Badge>;
}

const PR: Record<PullRequestSummary["status"], { label: string; icon: typeof CircleDot; solid: boolean }> = {
  open: { label: "Open", icon: CircleDot, solid: false },
  changes_requested: { label: "Changes requested", icon: CircleDot, solid: false },
  approved: { label: "Approved", icon: GitMerge, solid: true },
  closed: { label: "Closed", icon: GitPullRequestClosed, solid: false },
};

export function PrStatusBadge({ status }: { status: PullRequestSummary["status"] }) {
  const s = PR[status];
  const Icon = s.icon;
  return (
    <Badge variant={s.solid ? "solid" : "outline"}>
      <Icon aria-hidden="true" />
      {s.label}
    </Badge>
  );
}

export function VerifiedBadge({ verified, executed }: { verified: boolean; executed: boolean }) {
  if (verified) {
    return <Badge variant="solid"><ShieldCheck aria-hidden="true" />Verified sandbox</Badge>;
  }
  return <Badge><ShieldOff aria-hidden="true" />{executed ? "Unverified sandbox" : "Not executed"}</Badge>;
}

export function PassBadge({ passed, total }: { passed: number; total: number }) {
  const all = passed === total && total > 0;
  return (
    <Badge variant={all ? "solid" : "outline"}>
      {all ? <CircleCheck aria-hidden="true" /> : null}
      <span className="tabular-nums">{passed}/{total}</span> tests
    </Badge>
  );
}
