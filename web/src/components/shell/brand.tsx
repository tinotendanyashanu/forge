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
      className="flex h-10 min-w-0 items-center gap-3 rounded-xl px-1.5"
      aria-label="FORGE home"
    >
      <span className="flex size-8 shrink-0 items-center justify-center text-fg">
        <Anvil className="size-7" aria-hidden="true" />
      </span>
      <span
        className={cn(
          "text-base font-semibold tracking-[0.08em] text-fg",
          collapsed && "sr-only",
        )}
      >
        FORGE
      </span>
    </Link>
  );
}
