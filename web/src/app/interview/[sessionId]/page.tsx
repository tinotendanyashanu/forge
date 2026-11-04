import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { InterviewChat } from "@/components/interview/interview-chat";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getInterview } from "@/lib/api";

export const metadata: Metadata = { title: "Interview" };

export default function InterviewSessionPage({
  params,
}: PageProps<"/interview/[sessionId]">) {
  return (
    <Suspense
      fallback={
        <LoadingRegion label="Loading interview" className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pt-20 sm:px-6">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="ml-auto h-16 w-2/3 rounded-2xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </LoadingRegion>
      }
    >
      <Session params={params} />
    </Suspense>
  );
}

async function Session({ params }: { params: PageProps<"/interview/[sessionId]">["params"] }) {
  const { sessionId } = await params;
  const state = await getInterview(sessionId);
  if (!state) notFound();
  // Keyed so navigating between interviews resets client state.
  return <InterviewChat key={state.session.id} initial={state} />;
}
