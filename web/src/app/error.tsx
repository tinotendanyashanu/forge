"use client";

import { useEffect } from "react";

import { ButtonLink } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { PageContainer } from "@/components/ui/page-container";

export default function RouteError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const digest =
    error instanceof Error && "digest" in error
      ? String((error as Error & { digest?: string }).digest ?? "")
      : "";

  return (
    <PageContainer width="narrow">
      <ErrorState
        title="This page couldn't load"
        description={
          <>
            The FORGE API returned an error or couldn&apos;t be reached. Check
            that the API and database are running, then try again.
            {digest ? (
              <span className="mt-2 block font-mono text-xs text-fg-subtle">
                Reference: {digest}
              </span>
            ) : null}
          </>
        }
        onRetry={retry}
        secondaryAction={
          <ButtonLink href="/" variant="secondary" size="sm">
            Go to dashboard
          </ButtonLink>
        }
      />
    </PageContainer>
  );
}
