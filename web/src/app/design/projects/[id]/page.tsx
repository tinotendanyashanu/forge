import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { WorkspaceLoader } from "@/components/design/workspace-loader";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getDesignAdrs,
  getDesignCatalog,
  getDesignFailures,
  getDesignProject,
  getDesignReview,
  getDesignReviews,
  getDesignStatus,
  getDesignVersions,
} from "@/lib/api";

export const metadata: Metadata = { title: "Design workspace" };

export default function ProjectPage({ params }: PageProps<"/design/projects/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="h-dvh w-full rounded-none" />}>
      <Project params={params} />
    </Suspense>
  );
}

async function Project({ params }: { params: PageProps<"/design/projects/[id]">["params"] }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const [project, versions, adrs, reviews, failures, catalog, status] = await Promise.all([
    getDesignProject(id),
    getDesignVersions(id),
    getDesignAdrs(id),
    getDesignReviews(id),
    getDesignFailures(id),
    getDesignCatalog(),
    getDesignStatus(),
  ]);
  if (!project) notFound();
  const latestReview = reviews?.[0] ? await getDesignReview(reviews[0].id) : null;
  return (
    <WorkspaceLoader
      key={project.id}
      project={project}
      versions={versions ?? []}
      adrs={adrs ?? []}
      reviews={reviews ?? []}
      latestReview={latestReview}
      failures={failures ?? []}
      scenarios={catalog.failure_scenarios}
      status={status}
    />
  );
}
