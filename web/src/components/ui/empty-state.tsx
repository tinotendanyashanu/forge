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
        "flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-10 text-center",
        className,
      )}
    >
      <span className="mb-4 flex size-10 items-center justify-center rounded-lg border border-line bg-surface text-fg-muted">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <h3 className="text-sm font-medium text-fg">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fg-muted">
        {description}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
