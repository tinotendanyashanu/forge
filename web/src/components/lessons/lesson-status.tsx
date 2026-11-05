import { BadgeCheck, Bot, PencilLine } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { LessonStatus } from "@/lib/types";

const META: Record<LessonStatus, { label: string; title: string; icon: typeof Bot }> = {
  verified: {
    label: "Human-verified",
    title: "Reviewed by a human subject-matter expert.",
    icon: BadgeCheck,
  },
  reviewed: {
    label: "AI-reviewed",
    title: "Written with AI assistance and checked by an automated review. Not yet verified by a human expert.",
    icon: Bot,
  },
  draft: { label: "Draft", title: "Not yet reviewed.", icon: PencilLine },
};

/** Makes the provenance of teaching content visible; AI review is not human verification. */
export function LessonStatusBadge({ status }: { status: LessonStatus }) {
  const meta = META[status];
  const Icon = meta.icon;
  return (
    <Badge variant={status === "verified" ? "solid" : "outline"} title={meta.title}>
      <Icon aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}
