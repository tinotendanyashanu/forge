"use client";

import { Lightbulb } from "lucide-react";
import { useId, useState } from "react";

import { InlineText } from "@/components/ui/rich-text";
import { cn } from "@/lib/cn";

export function HintDisclosure({ hint }: { hint: string }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div className="rounded-xl border border-line bg-surface">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-sm text-fg-muted transition-colors hover:text-fg"
      >
        <Lightbulb className="size-4 shrink-0" aria-hidden="true" />
        <span className="flex-1 font-medium">
          {open ? "Hide hint" : "Show a hint"}
        </span>
        <span className="text-xs text-fg-subtle">Optional</span>
      </button>
      <div
        id={panelId}
        hidden={!open}
        className={cn(
          "border-t border-line-subtle px-4 py-3 text-sm leading-relaxed text-fg-muted",
          open && "animate-fade-in",
        )}
      >
        <InlineText text={hint} />
      </div>
    </div>
  );
}
