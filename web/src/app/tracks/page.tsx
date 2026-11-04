import { BookOpen } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { TrackGrid, TrackGridSkeleton } from "@/components/tracks/track-card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion } from "@/components/ui/skeleton";
import { getSkills } from "@/lib/api";

export const metadata: Metadata = { title: "Skills" };

export default function TracksPage() {
  return (
    <PageContainer className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Skill tracks"
        title="Choose what to practise"
        description="Each track has beginner, intermediate and advanced questions. Pick one to see its topics and start an assessment."
      />
      <Suspense
        fallback={
          <LoadingRegion label="Loading skills">
            <TrackGridSkeleton />
          </LoadingRegion>
        }
      >
        <SkillList />
      </Suspense>
    </PageContainer>
  );
}

async function SkillList() {
  const skills = await getSkills();
  if (skills.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No skills published"
        description="The database has no skills yet. Run `python -m app.seed` in the api directory."
      />
    );
  }
  return <TrackGrid skills={skills} />;
}
