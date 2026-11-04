import { Clock } from "lucide-react";

import { DifficultyBadge } from "@/components/tracks/difficulty-badge";
import { CodeBlock, InlineText } from "@/components/ui/rich-text";
import { formatLabel } from "@/lib/format";
import type { QuestionPublic } from "@/lib/types";

/** Question header, prompt and code. Contains no answer material. */
export function QuestionView({
  question,
  position,
  total,
}: {
  question: QuestionPublic;
  position: number;
  total: number;
}) {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="text-[13px] font-medium text-fg-subtle tabular-nums">
          Question {position} of {total} · {question.topic.title}
        </p>
        <h1
          id="question-heading"
          tabIndex={-1}
          className="mt-2 text-2xl outline-none font-semibold tracking-tight text-balance text-fg sm:text-[28px] sm:leading-tight"
        >
          {question.title}
        </h1>
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-fg-subtle">
          <DifficultyBadge level={question.difficulty} />
          <span>{formatLabel[question.format]}</span>
          <span className="inline-flex items-center gap-1 tabular-nums">
            <Clock className="size-3.5" aria-hidden="true" />
            About {question.estimated_minutes} min
          </span>
        </div>
      </header>
      <section aria-label="Prompt" className="flex flex-col gap-5">
        <p className="text-base leading-relaxed text-pretty text-fg">
          <InlineText text={question.prompt} />
        </p>
        {question.code ? (
          <CodeBlock code={question.code} language={question.code_language} />
        ) : null}
      </section>
    </div>
  );
}
