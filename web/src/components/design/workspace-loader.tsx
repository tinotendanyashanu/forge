"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

import type { WorkspaceProps } from "./workspace";

// Client-only: the canvas measures the DOM and recovery reads localStorage.
const Workspace = dynamic(() => import("./workspace").then((m) => m.Workspace), {
  ssr: false,
  loading: () => (
    <div role="status" aria-label="Loading workspace" className="grid h-[calc(100dvh-3.5rem)] gap-px md:h-dvh lg:grid-cols-[264px_1fr_320px] xl:grid-cols-[300px_1fr_380px]">
      <Skeleton className="hidden rounded-none lg:block" />
      <Skeleton className="rounded-none" />
      <Skeleton className="hidden rounded-none lg:block" />
    </div>
  ),
});

export function WorkspaceLoader(props: WorkspaceProps) {
  return <Workspace {...props} />;
}
