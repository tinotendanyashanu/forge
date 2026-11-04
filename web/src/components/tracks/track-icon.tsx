import {
  Atom,
  BookOpen,
  Braces,
  Database,
  FileCode,
  FlaskConical,
  Globe,
  Network,
  ShieldCheck,
  Container,
  GitBranch,
  Blocks,
  Code,
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
  "programming-fundamentals": Code,
  security: ShieldCheck,
  devops: Container,
  "distributed-systems": Blocks,
  "senior-practices": GitBranch,
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
        "flex size-11 shrink-0 items-center justify-center rounded-xl bg-surface-hover text-fg",
        className,
      )}
    >
      <Icon className="size-5" aria-hidden="true" />
    </span>
  );
}
