"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";
import type { OpsSession, OpsStatus } from "@/lib/types";

// Client-only: charts measure the DOM and the RCA draft is kept in localStorage.
const OpsWorkspace = dynamic(() => import("./workspace").then((m) => m.OpsWorkspace), {
  ssr: false,
  loading: () => (
    <div role="status" aria-label="Loading incident" className="grid h-[calc(100dvh-3.5rem)] gap-px md:h-dvh lg:grid-cols-[1fr_340px]">
      <Skeleton className="rounded-none" />
      <Skeleton className="hidden rounded-none lg:block" />
    </div>
  ),
});

export function OpsWorkspaceLoader(props: { initial: OpsSession; status: OpsStatus | null }) {
  return <OpsWorkspace {...props} />;
}
