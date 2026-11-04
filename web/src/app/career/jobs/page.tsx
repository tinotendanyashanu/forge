import { FileSearch } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { analyseJob } from "@/app/actions";
import { LEVEL_LABEL, date } from "@/components/career/format";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { getCareerJobs } from "@/lib/api";

export const metadata: Metadata = { title: "Job description matcher" };

const field = "w-full rounded-md border border-line bg-canvas px-3 py-2 text-[13px] text-fg placeholder:text-fg-subtle focus:border-neutral-500 focus:outline-none";

export default function JobsPage({ searchParams }: PageProps<"/career/jobs">) {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader eyebrow={<Link href="/career" className="hover:text-fg">FORGE Career</Link>} title="Job description matcher"
        description="Paste a job description. FORGE maps its requirements to the competency framework and compares them with evidence you've produced here. It never scrapes sites, applies for jobs, or infers qualifications you haven't shown." />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-5">
          <Suspense fallback={<Skeleton className="h-80 rounded-lg" />}>
            <Form searchParams={searchParams} />
          </Suspense>
        </Card>
        <Suspense fallback={<Skeleton className="h-48 rounded-xl" />}><Recent /></Suspense>
      </div>
    </PageContainer>
  );
}

async function Form({ searchParams }: Pick<PageProps<"/career/jobs">, "searchParams">) {
  const sp = await searchParams;
  return (
    <form action={analyseJob} className="flex flex-col gap-3">
      <label className="text-xs text-fg-subtle">Role title (optional)
        <input name="title" maxLength={200} className={`${field} mt-1`} placeholder="e.g. Mid-level Full-Stack Engineer" />
      </label>
      <label className="text-xs text-fg-subtle">Job description
        <textarea name="description" required minLength={50} maxLength={20000} className={`${field} mt-1 min-h-72`} placeholder="Paste the full job description" />
      </label>
      {typeof sp.error === "string" ? <p role="alert" className="text-xs text-fg">{sp.error}</p> : null}
      <div><Button type="submit"><FileSearch aria-hidden="true" />Analyse</Button></div>
      <p className="text-xs text-fg-subtle">The text is treated as untrusted data. Instructions inside it are ignored.</p>
    </form>
  );
}

async function Recent() {
  const jobs = await getCareerJobs();
  return (
    <section>
      <h2 className="mb-2 text-xs font-medium text-fg-subtle">Analysed roles</h2>
      {jobs?.length ? (
        <ul className="flex flex-col gap-1.5">
          {jobs.map((j) => (
            <li key={j.id}><Link href={`/career/jobs/${j.id}`} className="block rounded-lg border border-line px-3 py-2 hover:bg-surface-hover">
              <span className="block truncate text-[13px] text-fg">{j.title}</span>
              <span className="text-[11px] text-fg-subtle">{date(j.created_at)} · {LEVEL_LABEL[j.level as keyof typeof LEVEL_LABEL] ?? j.level} · {j.summary?.match ?? 0} match, {j.summary?.gap ?? 0} gap, {j.summary?.untested ?? 0} untested</span>
            </Link></li>
          ))}
        </ul>
      ) : <p className="text-xs text-fg-subtle">None yet.</p>}
    </section>
  );
}
