import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Badge({
  className,
  variant = "outline",
  ...props
}: ComponentProps<"span"> & { variant?: "outline" | "solid" }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3.5 [&_svg]:shrink-0",
        variant === "outline"
          ? "border border-line text-fg-muted"
          : "bg-surface-hover text-fg",
        className,
      )}
      {...props}
    />
  );
}
