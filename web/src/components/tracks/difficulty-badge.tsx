import { Badge } from "@/components/ui/badge";
import { difficultyLabel } from "@/lib/format";
import type { Difficulty } from "@/lib/types";

const STEPS: Difficulty[] = ["beginner", "intermediate", "advanced"];

/** Monochrome level indicator: filled bars encode difficulty, text names it. */
export function DifficultyBadge({ level }: { level: Difficulty }) {
  const filled = STEPS.indexOf(level) + 1;
  return (
    <Badge>
      <span className="flex items-end gap-[2px]" aria-hidden="true">
        {STEPS.map((step, i) => (
          <span
            key={step}
            className={
              i < filled
                ? "w-[3px] rounded-[1px] bg-fg"
                : "w-[3px] rounded-[1px] bg-line"
            }
            style={{ height: 5 + i * 3 }}
          />
        ))}
      </span>
      {difficultyLabel[level]}
    </Badge>
  );
}
