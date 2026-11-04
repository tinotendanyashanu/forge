import { Fragment } from "react";

import { cn } from "@/lib/cn";

/**
 * Renders plain text with `inline code` spans. Content is treated as text,
 * never as HTML.
 */
export function InlineText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("`") && part.endsWith("`") && part.length > 2 ? (
          <code
            key={i}
            className="rounded border border-line-subtle bg-surface-raised px-1 py-px font-mono text-[0.88em] text-fg"
          >
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

export function CodeBlock({
  code,
  language,
  className,
}: {
  code: string;
  language?: string | null;
  className?: string;
}) {
  return (
    <figure
      className={cn(
        "overflow-hidden rounded-xl border border-line bg-canvas",
        className,
      )}
    >
      {language ? (
        <figcaption className="flex h-9 items-center border-b border-line-subtle px-4 font-mono text-xs text-fg-subtle">
          {language}
        </figcaption>
      ) : null}
      <pre
        tabIndex={0}
        aria-label={language ? `${language} code` : "Code"}
        className="overflow-x-auto p-4 font-mono text-[13px] leading-6 text-fg"
      >
        <code>{code}</code>
      </pre>
    </figure>
  );
}
