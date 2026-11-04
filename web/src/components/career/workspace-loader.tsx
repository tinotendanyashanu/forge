"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";
import type { AttemptView } from "@/lib/types";

// Client-only: drafts live in localStorage and the timer uses the browser clock offset.
const AttemptWorkspace = dynamic(() => import("./workspace").then((m) => m.AttemptWorkspace), {
  ssr: false,
  loading: () => <div role="status" aria-label="Loading assessment" className="mx-auto max-w-6xl p-8"><Skeleton className="h-96 rounded-xl" /></div>,
});

export function AttemptLoader({ initial }: { initial: AttemptView }) {
  return <AttemptWorkspace initial={initial} />;
}
