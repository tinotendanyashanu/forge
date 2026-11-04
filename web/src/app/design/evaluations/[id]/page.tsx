import { ChevronLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { EvaluationView } from "@/components/design/evaluation-view";
import { ButtonLink } from "@/components/ui/button";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getDesignEvaluation } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Design evaluation" };

export default function EvaluationPage({ params }: PageProps<"/design/evaluations/[id]">) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-6 pb-16 sm:px-6">
      <Link href="/design" className="mb-5 inline-flex w-fit items-center gap-1 rounded-md text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden="true" />
        Design lab
      </Link>
      <Suspense fallback={<LoadingRegion label="Loading evaluation"><Skeleton className="h-96 rounded-xl" /></LoadingRegion>}>
        <Evaluation params={params} />
      </Suspense>
    </div>
  );
}

async function Evaluation({ params }: { params: PageProps<"/design/evaluations/[id]">["params"] }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const ev = await getDesignEvaluation(id);
  if (!ev) notFound();
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-fg-subtle">Version {ev.architecture_version} · {formatDateTime(ev.created_at)}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">{ev.project_title}</h1>
        </div>
        <ButtonLink href={`/design/projects/${ev.project_id}`} size="sm" variant="secondary">Open design</ButtonLink>
      </header>
      <EvaluationView ev={ev} />
    </div>
  );
}
