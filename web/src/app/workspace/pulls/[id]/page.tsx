import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";

import { PullRequestView } from "@/components/workspace/pull-request";
import { getPull, getWorkspaceStatus } from "@/lib/workspace-api";

export const metadata: Metadata = { title: "Pull request" };

export default function PullPage(props: PageProps<"/workspace/pulls/[id]">) {
  return (
    <Suspense fallback={<LoadingRegion label="Loading" className="p-6"><Skeleton className="h-[70vh] w-full rounded-xl" /></LoadingRegion>}>
      <Inner {...props} />
    </Suspense>
  );
}

async function Inner({ params }: PageProps<"/workspace/pulls/[id]">) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const [pr, status] = await Promise.all([getPull(id), getWorkspaceStatus().catch(() => null)]);
  if (!pr) notFound();
  return <PullRequestView initial={pr} status={status} />;
}
