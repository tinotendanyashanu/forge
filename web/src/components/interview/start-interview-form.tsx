"use client";

import { ArrowRight, CircleAlert, LoaderCircle } from "lucide-react";
import { useActionState, useState } from "react";

import { startInterview, type StartState } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { difficultyLabel } from "@/lib/format";
import {
  DIFFICULTIES,
  INTERVIEW_MODES,
  type Difficulty,
  type InterviewMode,
  type SkillSummary,
} from "@/lib/types";

import { MODE_META } from "./modes";

const initialState: StartState = { error: null };

const cardClass = (checked: boolean) =>
  cn(
    "relative flex cursor-pointer rounded-2xl border transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-fg",
    checked ? "border-fg bg-surface-raised" : "border-line bg-surface hover:border-neutral-600",
  );

export function StartInterviewForm({
  skills,
  defaultSkill,
  defaultMode,
}: {
  skills: SkillSummary[];
  defaultSkill?: string;
  defaultMode?: InterviewMode;
}) {
  const [state, formAction, pending] = useActionState(startInterview, initialState);
  const [skill, setSkill] = useState(
    skills.some((s) => s.slug === defaultSkill) ? defaultSkill! : skills[0]?.slug,
  );
  const [difficulty, setDifficulty] = useState<Difficulty>("beginner");
  const [mode, setMode] = useState<InterviewMode>(defaultMode ?? "tutor");

  return (
    <form action={formAction} className="flex flex-col gap-8">
      <fieldset>
        <legend className="mb-3 text-sm font-medium text-fg">Mode</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {INTERVIEW_MODES.map((m) => {
            const meta = MODE_META[m];
            const Icon = meta.icon;
            return (
              <label key={m} className={cn(cardClass(mode === m), "items-start gap-3 p-5")}>
                <input
                  type="radio"
                  name="mode"
                  value={m}
                  checked={mode === m}
                  onChange={() => setMode(m)}
                  className="sr-only"
                />
                <Icon className="mt-0.5 size-5 shrink-0 text-fg" aria-hidden="true" />
                <span>
                  <span className="block text-sm font-medium text-fg">{meta.label}</span>
                  <span className="mt-1.5 block text-sm leading-relaxed text-fg-muted">
                    {meta.description}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-3 text-sm font-medium text-fg">Skill</legend>
        <div className="flex flex-wrap gap-2">
          {skills.map((s) => (
            <label key={s.slug} className={cn(
              "relative flex min-h-11 cursor-pointer items-center rounded-full border px-4 py-2 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-fg",
              skill === s.slug ? "border-fg bg-fg text-canvas" : "border-line text-fg-muted hover:border-fg-subtle hover:text-fg",
            )}>
              <input
                type="radio"
                name="skill"
                value={s.slug}
                checked={skill === s.slug}
                onChange={() => setSkill(s.slug)}
                className="sr-only"
              />
              <span>{s.title}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-3 text-sm font-medium text-fg">Starting difficulty</legend>
        <div className="inline-flex max-w-full flex-wrap gap-1 rounded-2xl bg-canvas p-1 sm:rounded-full">
          {DIFFICULTIES.map((d) => (
            <label
              key={d}
              className={cn(
                "flex min-h-10 cursor-pointer items-center rounded-full px-3 py-2 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-fg",
                difficulty === d ? "bg-fg text-canvas" : "text-fg-muted hover:text-fg",
              )}
            >
              <input
                type="radio"
                name="difficulty"
                value={d}
                checked={difficulty === d}
                onChange={() => setDifficulty(d)}
                className="sr-only"
              />
              {difficultyLabel[d]}
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-fg-subtle">
          Difficulty adjusts during the interview based on your recent answers.
        </p>
      </fieldset>

      {state.error ? (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-fg"
        >
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {state.error}
        </p>
      ) : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={pending || !skill} className="w-full sm:w-auto">
          {pending ? (
            <>
              <LoaderCircle className="animate-spin" aria-hidden="true" />
              Starting…
            </>
          ) : (
            <>
              Start interview
              <ArrowRight aria-hidden="true" />
            </>
          )}
        </Button>
      </div>
    </form>
  );
}
