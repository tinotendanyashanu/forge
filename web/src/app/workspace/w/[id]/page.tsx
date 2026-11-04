import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";

import { WorkspaceIde } from "@/components/workspace/ide";
import { getWorkspace, getWorkspaceStatus } from "@/lib/workspace-api";

export const metadata: Metadata = { title: "Workspace" };

export default function WorkspacePage(props: PageProps<"/workspace/w/[id]">) {
  return (
    <Suspense fallback={<LoadingRegion label="Loading" className="p-6"><Skeleton className="h-[70vh] w-full rounded-xl" /></LoadingRegion>}>
      <Inner {...props} />
    </Suspense>
  );
}

async function Inner({ params }: PageProps<"/workspace/w/[id]">) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const [ws, status] = await Promise.all([getWorkspace(id), getWorkspaceStatus().catch(() => null)]);
  if (!ws) notFound();
  return <WorkspaceIde initial={ws} status={status} />;
}
