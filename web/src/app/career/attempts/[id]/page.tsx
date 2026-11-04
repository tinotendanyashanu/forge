import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AttemptLoader } from "@/components/career/workspace-loader";
import { Skeleton } from "@/components/ui/skeleton";
import { getCareerAttempt } from "@/lib/api";

export const metadata: Metadata = { title: "Assessment" };

export default function AttemptPage({ params }: PageProps<"/career/attempts/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="m-8 h-96 rounded-xl" />}>
      <Attempt params={params} />
    </Suspense>
  );
}

async function Attempt({ params }: { params: PageProps<"/career/attempts/[id]">["params"] }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const a = await getCareerAttempt(id);
  if (!a) notFound();
  return <AttemptLoader key={a.id} initial={a} />;
}
