"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { useFormStatus } from "react-dom";

import { launchActivity } from "@/app/actions";
import { Button, ButtonLink } from "@/components/ui/button";
import type { Activity } from "@/lib/types";

function Submit({ label, variant }: { label: string; variant: "primary" | "secondary" | "ghost" }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="sm" variant={variant} disabled={pending}>
      {pending ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : null}
      {pending ? "Starting…" : label}
      {pending ? null : <ArrowRight aria-hidden="true" />}
    </Button>
  );
}

/** Starts an assessment or AI interview for a recommended activity. */
export function LaunchButton({
  activity,
  label,
  variant = "primary",
}: {
  activity: Activity;
  label?: string;
  variant?: "primary" | "secondary" | "ghost";
}) {
  if (activity.type === "coding" && activity.challenge_slug) {
    return (
      <ButtonLink href={`/lab/challenges/${activity.challenge_slug}`} size="sm" variant={variant}>
        {label ?? "Open challenge"}
        <ArrowRight aria-hidden="true" />
      </ButtonLink>
    );
  }
  return (
    <form action={launchActivity}>
      <input type="hidden" name="type" value={activity.type} />
      <input type="hidden" name="skill" value={activity.skill_slug} />
      <input type="hidden" name="difficulty" value={activity.difficulty} />
      {activity.mode ? <input type="hidden" name="mode" value={activity.mode} /> : null}
      <Submit
        label={label ?? (activity.type === "interview" ? "Start interview" : "Start assessment")}
        variant={variant}
      />
    </form>
  );
}
