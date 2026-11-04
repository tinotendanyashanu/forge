import type { Difficulty, EvaluationStatus, QuestionFormat } from "@/lib/types";

export const difficultyLabel: Record<Difficulty, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

export const formatLabel: Record<QuestionFormat, string> = {
  single_choice: "Multiple choice",
  free_text: "Written answer",
};

export function outcomeLabel(status: EvaluationStatus, isCorrect: boolean | null) {
  if (status === "pending_ai_evaluation") return "Written, not scored";
  return isCorrect ? "Correct" : "Incorrect";
}

export function pluralize(count: number, singular: string, plural?: string) {
  return `${count} ${count === 1 ? singular : (plural ?? `${singular}s`)}`;
}

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** Rendered on the server only, in the server's time zone. */
export function formatDateTime(iso: string) {
  return dateFormat.format(new Date(iso));
}
