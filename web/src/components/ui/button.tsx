import Link from "next/link";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

const base =
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap transition-colors duration-150 select-none disabled:pointer-events-none disabled:opacity-40 aria-disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0";

const variants: Record<Variant, string> = {
  primary: "bg-fg text-canvas hover:bg-neutral-200 active:bg-neutral-300",
  secondary:
    "border border-line bg-transparent text-fg hover:bg-surface-hover hover:border-fg-subtle",
  ghost: "text-fg-muted hover:bg-surface-hover hover:text-fg",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-3.5 text-[13px]",
  md: "h-11 px-5 text-sm",
};

interface StyleProps {
  variant?: Variant;
  size?: Size;
}

export function buttonClass({
  variant = "primary",
  size = "md",
  className,
}: StyleProps & { className?: string } = {}) {
  return cn(base, variants[variant], sizes[size], className);
}

export function Button({
  variant,
  size,
  className,
  type = "button",
  ...props
}: StyleProps & ComponentProps<"button">) {
  return (
    <button
      type={type}
      className={buttonClass({ variant, size, className })}
      {...props}
    />
  );
}

export function ButtonLink({
  variant,
  size,
  className,
  ...props
}: StyleProps & ComponentProps<typeof Link>) {
  return (
    <Link className={buttonClass({ variant, size, className })} {...props} />
  );
}
