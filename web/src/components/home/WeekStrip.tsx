import { ArrowRight } from "lucide-react";

import type { Day, Meal } from "@/api/types";
import { AppLink } from "@/components/AppLink";
import { MealAvatar } from "@/components/meals/MealAvatar";
import { DAY_EDGE } from "@/components/plan/days";
import { cn } from "@/lib/utils";

export interface StripDay {
  day: Day;
  /** Day of the month. */
  date: number;
  today: boolean;
  meal: Meal | null;
}

/**
 * The week at a glance. Each day is a link to the plan that opens that
 * day's meal search, so changing Thursday from here is one click and a few
 * letters, not a hunt for Thursday on another page.
 */
export function WeekStrip({ days }: { days: readonly StripDay[] }) {
  return (
    <section aria-labelledby="the-week">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="the-week" className="text-base font-semibold">
          The week
        </h2>
        <AppLink
          to="/plan"
          className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Open the plan
          <ArrowRight aria-hidden className="size-3.5" />
        </AppLink>
      </div>

      <ol className="mt-3 grid gap-2 md:grid-cols-7">
        {days.map(({ day, date, today, meal }) => (
          <li key={day}>
            <AppLink
              to="/plan"
              params={{ day }}
              className={cn(
                "flex h-full items-center gap-3 rounded-xl border border-t-4 bg-card px-3 py-2.5 outline-none transition-colors hover:border-primary/40 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring md:flex-col md:items-start md:gap-2 md:py-3",
                meal ? DAY_EDGE[day] : "border-dashed border-t-border bg-card/50",
                today && "ring-2 ring-primary/60",
              )}
            >
              <span className="w-14 shrink-0 text-xs font-semibold tracking-wider uppercase md:w-auto">
                <span aria-hidden>{day.slice(0, 3)}</span>
                <span className="sr-only">{day}</span>{" "}
                <span className="font-normal text-muted-foreground tabular-nums">{date}</span>
                {today && <span className="sr-only">, today</span>}
              </span>{" "}
              {meal ? (
                <span className="flex min-w-0 items-center gap-2 text-sm font-medium md:items-start">
                  <MealAvatar meal={meal} size="sm" />
                  <span className="line-clamp-2 leading-snug">{meal.name}</span>
                </span>
              ) : (
                <span className="text-sm text-muted-foreground">Not planned</span>
              )}
            </AppLink>
          </li>
        ))}
      </ol>
    </section>
  );
}
