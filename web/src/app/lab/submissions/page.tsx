import { History } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { SubmissionList } from "@/components/coding/submission-list";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCodeSubmissions } from "@/lib/api";

export const metadata: Metadata = { title: "Submissions" };

export default function SubmissionsPage({ searchParams }: PageProps<"/lab/submissions">) {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader eyebrow="Coding lab" title="Submission history" description="Every submission with its hidden-test outcome. Open one for results and an AI review." />
      <Suspense fallback={<LoadingRegion label="Loading submissions"><Skeleton className="h-64 w-full rounded-xl" /></LoadingRegion>}>
        <List searchParams={searchParams} />
      </Suspense>
    </PageContainer>
  );
}

async function List({ searchParams }: { searchParams: PageProps<"/lab/submissions">["searchParams"] }) {
  const { challenge } = await searchParams;
  const subs = await getCodeSubmissions(typeof challenge === "string" ? challenge : undefined, 100);
  if (!subs || subs.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No submissions yet"
        description="Submit a solution and it will appear here with its results."
        action={<ButtonLink href="/lab/challenges" size="sm">Browse challenges</ButtonLink>}
      />
    );
  }
  return <SubmissionList submissions={subs} />;
}
