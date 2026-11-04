import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-2xl bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      <span className="mb-5 flex size-12 items-center justify-center rounded-full bg-surface-hover text-fg-muted">
        <Icon className="size-6" aria-hidden="true" />
      </span>
      <h3 className="text-base font-medium text-fg">{title}</h3>
      <p className="mt-2 max-w-sm text-sm leading-6 text-fg-muted">
        {description}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
