import { Compass } from "lucide-react";

import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";

export default function NotFound() {
  return (
    <PageContainer width="narrow">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="That track or question doesn't exist. It may have been renamed or removed from the question bank."
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <ButtonLink href="/tracks" size="sm">
              Browse tracks
            </ButtonLink>
            <ButtonLink href="/" variant="secondary" size="sm">
              Dashboard
            </ButtonLink>
          </div>
        }
      />
    </PageContainer>
  );
}
