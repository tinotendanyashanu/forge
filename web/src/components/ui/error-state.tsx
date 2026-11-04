import { CircleAlert, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./button";

export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
  secondaryAction,
}: {
  title?: string;
  description: ReactNode;
  onRetry?: () => void;
  secondaryAction?: ReactNode;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center rounded-2xl border border-line-subtle bg-surface px-6 py-12 text-center"
    >
      <span className="mb-5 flex size-12 items-center justify-center rounded-full bg-surface-hover text-fg">
        <CircleAlert className="size-5" aria-hidden="true" />
      </span>
      <h2 className="text-base font-medium text-fg">{title}</h2>
      <p className="mt-1.5 max-w-md text-sm leading-relaxed text-fg-muted">
        {description}
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {onRetry ? (
          <Button size="sm" onClick={onRetry}>
            <RefreshCw aria-hidden="true" />
            Try again
          </Button>
        ) : null}
        {secondaryAction}
      </div>
    </div>
  );
}
