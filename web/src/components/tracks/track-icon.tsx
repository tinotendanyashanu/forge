import {
  Atom,
  BookOpen,
  Braces,
  Database,
  FileCode,
  FlaskConical,
  Globe,
  Network,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

const ICONS: Record<string, LucideIcon> = {
  python: FileCode,
  fastapi: Zap,
  react: Atom,
  typescript: Braces,
  sql: Database,
  http: Globe,
  testing: FlaskConical,
  "system-design": Network,
};

export function TrackIcon({
  slug,
  className,
}: {
  slug: string;
  className?: string;
}) {
  const Icon = ICONS[slug] ?? BookOpen;
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-raised text-fg",
        className,
      )}
    >
      <Icon className="size-[18px]" aria-hidden="true" />
    </span>
  );
}
