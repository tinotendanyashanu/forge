import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function PageContainer({
  className,
  width = "default",
  ...props
}: ComponentProps<"div"> & { width?: "default" | "narrow" }) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-4 pt-8 pb-16 sm:px-6 md:pt-12 lg:px-10",
        width === "default" ? "max-w-6xl" : "max-w-3xl",
        className,
      )}
      {...props}
    />
  );
}
