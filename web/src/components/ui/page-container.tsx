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
        "mx-auto w-full px-5 pt-8 pb-20 sm:px-8 md:pt-14 lg:px-12",
        width === "default" ? "max-w-6xl" : "max-w-3xl",
        className,
      )}
      {...props}
    />
  );
}
