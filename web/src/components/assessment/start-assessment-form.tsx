"use client";

import { ArrowRight, CircleAlert, LoaderCircle } from "lucide-react";
import { useActionState, useState } from "react";

import { startAssessment, type StartState } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { difficultyLabel, pluralize } from "@/lib/format";
import { DIFFICULTIES, type Difficulty, type SkillDetail } from "@/lib/types";

const DESCRIPTIONS: Record<Difficulty, string> = {
  beginner: "Core concepts and common pitfalls.",
  intermediate: "Applying concepts to realistic code.",
  advanced: "Design trade-offs and failure modes.",
};

const initialState: StartState = { error: null };

export function StartAssessmentForm({ skill }: { skill: SkillDetail }) {
  const [state, formAction, pending] = useActionState(startAssessment, initialState);
  const firstAvailable =
    DIFFICULTIES.find((d) => skill.questions_by_difficulty[d] > 0) ?? null;
  const [difficulty, setDifficulty] = useState<Difficulty | null>(firstAvailable);

  return (
    <form action={formAction} className="flex flex-col gap-5">
      <input type="hidden" name="skill" value={skill.slug} />
      <fieldset>
        <legend className="mb-3 text-sm font-medium text-fg">
          Choose a difficulty
        </legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {DIFFICULTIES.map((d) => {
            const count = skill.questions_by_difficulty[d] ?? 0;
            const disabled = count === 0;
            const checked = difficulty === d;
            return (
              <label
                key={d}
                className={cn(
                  "relative flex cursor-pointer flex-col rounded-xl border p-4 transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-fg",
                  checked
                    ? "border-fg bg-surface-raised"
                    : "border-line bg-surface hover:border-neutral-600",
                  disabled && "cursor-not-allowed opacity-40",
                )}
              >
                <input
                  type="radio"
                  name="difficulty"
                  value={d}
                  checked={checked}
                  disabled={disabled}
                  onChange={() => setDifficulty(d)}
                  className="sr-only"
                />
                <span className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-fg">
                    {difficultyLabel[d]}
                  </span>
                  <span
                    aria-hidden="true"
                    className={cn(
                      "flex size-4 items-center justify-center rounded-full border",
                      checked ? "border-fg" : "border-neutral-600",
                    )}
                  >
                    {checked ? <span className="size-2 rounded-full bg-fg" /> : null}
                  </span>
                </span>
                <span className="mt-1.5 text-[13px] leading-snug text-fg-muted">
                  {DESCRIPTIONS[d]}
                </span>
                <span className="mt-3 text-xs text-fg-subtle tabular-nums">
                  {disabled ? "No questions yet" : pluralize(count, "question")}
                </span>
              </label>
            );
          })}
        </div>
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

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-fg-subtle">
          Up to 5 questions. Your answers are saved as you go.
        </p>
        <Button
          type="submit"
          disabled={pending || difficulty === null}
          className="w-full sm:w-auto"
        >
          {pending ? (
            <>
              <LoaderCircle className="animate-spin" aria-hidden="true" />
              Starting…
            </>
          ) : (
            <>
              Start assessment
              <ArrowRight aria-hidden="true" />
            </>
          )}
        </Button>
      </div>
    </form>
  );
}
