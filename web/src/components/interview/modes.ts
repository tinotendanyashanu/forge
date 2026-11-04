import { DraftingCompass, Gavel, GraduationCap, SquareTerminal, type LucideIcon } from "lucide-react";

import type { InterviewMode } from "@/lib/types";

export const MODE_META: Record<
  InterviewMode,
  { label: string; description: string; icon: LucideIcon }
> = {
  tutor: {
    label: "Tutor",
    description: "Scaffolded questions, progressive hints and up to two follow-ups.",
    icon: GraduationCap,
  },
  grill: {
    label: "Grill",
    description: "Strict interviewer. No hints until you've made an attempt.",
    icon: Gavel,
  },
  debug: {
    label: "Debug",
    description: "Diagnose realistic code and production failures.",
    icon: SquareTerminal,
  },
  architect: {
    label: "Architect",
    description: "Design discussion: scale, security, failure modes and trade-offs.",
    icon: DraftingCompass,
  },
};
