import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-3 text-sm font-medium text-fg-muted">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="max-w-3xl text-[28px] leading-tight font-semibold tracking-[-0.035em] text-balance text-fg sm:text-[34px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-3 max-w-2xl text-[15px] leading-7 text-pretty text-fg-muted sm:text-base">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>
      ) : null}
    </header>
  );
}

export function SectionHeader({
  id,
  title,
  description,
  action,
}: {
  id?: string;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div>
        <h2 id={id} className="text-lg font-semibold tracking-tight text-fg">
          {title}
        </h2>
        {description ? (
          <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}
