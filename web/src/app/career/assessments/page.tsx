import { Clock } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { KIND_LABEL, LEVEL_LABEL, TRACK_LABEL } from "@/components/career/format";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { getCareerTemplates } from "@/lib/api";

export const metadata: Metadata = { title: "Assessments" };

export default function AssessmentsPage() {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader eyebrow={<Link href="/career" className="hover:text-fg">FORGE Career</Link>} title="Assessments"
        description="Formal assessments are timed by the server and composed from FORGE's interview, coding, design and incident labs. Practice and diagnostic assessments are untimed and labelled as practice." />
      <Suspense fallback={<LoadingRegion label="Loading assessments"><Skeleton className="h-80 rounded-xl" /></LoadingRegion>}>
        <List />
      </Suspense>
    </PageContainer>
  );
}

async function List() {
  const ts = await getCareerTemplates();
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {ts.map((t) => (
        <li key={t.slug}>
          <Link href={`/career/assessments/${t.slug}`} className="flex h-full flex-col gap-2 rounded-xl border border-line bg-surface p-5 hover:bg-surface-hover">
            <span className="flex items-center justify-between gap-2 text-xs text-fg-subtle">
              <span>{TRACK_LABEL[t.track]} · {LEVEL_LABEL[t.level]} · v{t.version}</span>
              <span className="rounded border border-line px-1.5 py-0.5 uppercase tracking-wide">{t.purpose}</span>
            </span>
            <span className="text-base font-medium text-fg">{t.title}</span>
            <span className="text-sm text-fg-muted">{t.description}</span>
            <span className="mt-auto flex flex-wrap items-center gap-2 pt-2 text-xs text-fg-subtle">
              <Clock className="size-3.5" aria-hidden="true" />{t.time_limit_minutes ? `${t.time_limit_minutes} min` : "Untimed"}
              {" · "}{t.sections.map((s) => KIND_LABEL[s.kind]).join(", ")}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
