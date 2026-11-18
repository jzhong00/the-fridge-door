import { Minus, Plus, X } from "lucide-react";

import type { Day, DayAssignment, Meal } from "@/api/types";
import { MealAvatar } from "@/components/meals/MealAvatar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { MealPicker } from "./MealPicker";

/** Each day's colour, the same wherever a day appears. */
const DAY_EDGE: Record<Day, string> = {
  Monday: "border-t-mon",
  Tuesday: "border-t-tue",
  Wednesday: "border-t-wed",
  Thursday: "border-t-thu",
  Friday: "border-t-fri",
  Saturday: "border-t-sat",
  Sunday: "border-t-sun",
};

const MAX_SERVINGS = 99;

/**
 * One day: its meal, how many it serves, and a way to clear it. The whole
 * meal area is the target for choosing a meal, empty or not.
 */
export function DayCard({
  day,
  date,
  today,
  assignment,
  meal,
  meals,
  plannedIds,
  onPick,
  onCreate,
  onServings,
  onClear,
}: {
  day: Day;
  /** Day of the month, e.g. 16. */
  date: number;
  today: boolean;
  assignment: DayAssignment;
  meal: Meal | null;
  meals: readonly Meal[];
  plannedIds: ReadonlySet<number>;
  onPick: (meal: Meal) => void;
  onCreate: (name: string) => void;
  onServings: (servings: number) => void;
  onClear: () => void;
}) {
  const servings = assignment.servings ?? meal?.servings ?? 1;

  return (
    <li
      aria-label={day}
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-t-4 bg-card p-3 sm:min-h-36",
        meal ? DAY_EDGE[day] : "border-dashed border-t-border bg-card/50",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold tracking-wider uppercase">
          <span className={meal ? "text-foreground" : "text-muted-foreground"}>
            {day.slice(0, 3)}
          </span>{" "}
          <span className="font-normal text-muted-foreground tabular-nums">{date}</span>
          {today && (
            <span className="ml-1.5 rounded-full bg-primary-subtle px-1.5 py-0.5 text-[10px] tracking-normal text-primary-subtle-foreground normal-case">
              Today
            </span>
          )}
        </p>
        {meal && (
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={`Clear ${day}`}
            onClick={onClear}
            className="-mr-1 text-muted-foreground"
          >
            <X aria-hidden />
          </Button>
        )}
      </div>

      <MealPicker
        meals={meals}
        plannedIds={plannedIds}
        current={meal}
        title={`Choose a meal for ${day}`}
        triggerLabel={`${day}: ${meal?.name ?? "no meal"}`}
        onPick={onPick}
        onCreate={onCreate}
      >
        {() =>
          meal ? (
            <>
              <MealAvatar meal={meal} />
              <span className="min-w-0 flex-1 text-sm leading-snug font-medium">
                {meal.name}
              </span>
            </>
          ) : (
            <span className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed py-3 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
              <Plus aria-hidden className="size-4" />
              Add a meal
            </span>
          )
        }
      </MealPicker>

      {meal && (
        <div className="mt-auto flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">Serves</span>
          <div className="flex items-center gap-1" role="group" aria-label={`Servings on ${day}`}>
            <Button
              variant="outline"
              size="icon-xs"
              aria-label={`Fewer servings on ${day}`}
              disabled={servings <= 1}
              onClick={() => onServings(servings - 1)}
            >
              <Minus aria-hidden />
            </Button>
            <output aria-live="polite" className="w-6 text-center text-sm font-medium tabular-nums">
              {servings}
            </output>
            <Button
              variant="outline"
              size="icon-xs"
              aria-label={`More servings on ${day}`}
              disabled={servings >= MAX_SERVINGS}
              onClick={() => onServings(servings + 1)}
            >
              <Plus aria-hidden />
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
