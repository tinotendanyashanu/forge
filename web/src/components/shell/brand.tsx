import { Anvil } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/cn";

export function Brand({
  collapsed = false,
  onNavigate,
}: {
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href="/"
      onClick={onNavigate}
      className="flex h-9 min-w-0 items-center gap-2.5 rounded-lg px-1.5"
      aria-label="FORGE home"
    >
      <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-fg text-canvas">
        <Anvil className="size-4" aria-hidden="true" strokeWidth={2.25} />
      </span>
      <span
        className={cn(
          "text-[15px] font-semibold tracking-[0.12em] text-fg",
          collapsed && "sr-only",
        )}
      >
        FORGE
      </span>
    </Link>
  );
}
