import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { OpsWorkspaceLoader } from "@/components/ops/workspace-loader";
import { Skeleton } from "@/components/ui/skeleton";
import { getOpsSession, getOpsStatus } from "@/lib/api";

export const metadata: Metadata = { title: "Incident" };

export default function IncidentSessionPage({ params }: PageProps<"/ops/sessions/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="h-dvh w-full rounded-none" />}>
      <Session params={params} />
    </Suspense>
  );
}

async function Session({ params }: { params: PageProps<"/ops/sessions/[id]">["params"] }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const [session, status] = await Promise.all([getOpsSession(id), getOpsStatus()]);
  if (!session) notFound();
  return <OpsWorkspaceLoader key={session.id} initial={session} status={status} />;
}
