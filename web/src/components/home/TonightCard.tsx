import { ArrowRight, Plus } from "lucide-react";
import type { ReactNode } from "react";

import type { Day, Meal } from "@/api/types";
import { AppLink } from "@/components/AppLink";
import { MealAvatar } from "@/components/meals/MealAvatar";
import { DAY_EDGE } from "@/components/plan/days";
import { MealPicker } from "@/components/plan/MealPicker";
import { buttonVariants } from "@/components/ui/button";
import { formatAmount, scaledIngredients } from "@/lib/quantities";
import { cn } from "@/lib/utils";

const MAX_SUGGESTIONS = 4;

/**
 * The page's focal point: what is for dinner, and what it takes, scaled to
 * the number cooked for. With nothing planned, the one thing to do is right
 * there: choose a meal, saved as soon as it is chosen.
 */
export function TonightCard({
  day,
  isToday,
  dateLabel,
  meal,
  servings,
  tomorrow,
  meals,
  plannedIds,
  onPick,
  onCreate,
}: {
  day: Day;
  /** Tonight, or the day this week starts on when the week is not this one. */
  isToday: boolean;
  /** e.g. "Wed, Nov 18" */
  dateLabel: string;
  meal: Meal | null;
  servings: number;
  /** The next day's meal, for what to buy or thaw ahead; absent on Sunday. */
  tomorrow: { day: Day; meal: Meal | null } | null;
  meals: readonly Meal[];
  plannedIds: ReadonlySet<number>;
  onPick: (meal: Meal) => void;
  onCreate: (name: string) => void;
}) {
  const when = isToday ? "tonight" : day;
  const ingredients = meal ? scaledIngredients(meal, servings) : [];
  // A few meals to plan in one click: ones not yet had this week first,
  // for variety, then repeats. The search is there for everything else.
  const suggestions = [...meals]
    .sort((a, b) => Number(plannedIds.has(a.id)) - Number(plannedIds.has(b.id)))
    .slice(0, MAX_SUGGESTIONS);

  const picker = (label: string, trigger: string, content: ReactNode) => (
    <MealPicker
      meals={meals}
      plannedIds={plannedIds}
      current={meal}
      title={`Choose a meal for ${when}`}
      triggerLabel={label}
      triggerClassName={trigger}
      onPick={onPick}
      onCreate={onCreate}
    >
      {() => content}
    </MealPicker>
  );

  return (
    <section
      aria-labelledby="tonight"
      className={cn(
        "flex flex-col rounded-2xl border border-t-4 bg-card p-5 sm:p-6",
        meal ? DAY_EDGE[day] : "border-t-border",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <h2
          id="tonight"
          className="text-xs font-semibold tracking-wider text-muted-foreground uppercase"
        >
          {isToday ? "Tonight" : day}
          <span className="font-normal normal-case tracking-normal"> · {dateLabel}</span>
        </h2>
        {meal &&
          picker(
            `Change ${isToday ? "tonight's" : `${day}'s`} meal`,
            buttonVariants({ variant: "outline", size: "sm" }),
            "Change",
          )}
      </div>

      {meal ? (
        <>
          <div className="mt-4 flex items-center gap-4">
            <MealAvatar meal={meal} size="lg" />
            <div className="min-w-0">
              <p className="font-heading text-2xl leading-tight font-semibold sm:text-3xl">
                {meal.name}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Serves {servings}
                {meal.ingredients.length > 0 &&
                  ` · ${meal.ingredients.length} ingredient${meal.ingredients.length === 1 ? "" : "s"}`}
              </p>
            </div>
          </div>

          {ingredients.length > 0 ? (
            <div className="mt-6">
              <h3 className="text-sm font-medium">
                What you need
                {servings !== meal.servings && (
                  <span className="font-normal text-muted-foreground">
                    {" "}
                    · the recipe serves {meal.servings}, scaled to {servings}
                  </span>
                )}
              </h3>
              <ul className="mt-2 grid gap-x-8 text-sm sm:grid-cols-2">
                {ingredients.map((ingredient) => (
                  <li
                    key={ingredient.ingredient_id}
                    className="flex items-baseline justify-between gap-3 border-b border-dashed py-1.5"
                  >
                    <span className="min-w-0">{ingredient.name}</span>
                    <span className="shrink-0 text-muted-foreground tabular-nums">
                      {formatAmount(ingredient.qty, ingredient.unit)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-6 text-sm text-muted-foreground">
              No ingredients yet, so nothing for it on the grocery list.{" "}
              <AppLink
                to="/meals"
                params={{ meal: String(meal.id) }}
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                Add its ingredients
              </AppLink>
            </p>
          )}
        </>
      ) : (
        <div className="mt-4 flex flex-col items-start gap-3">
          <p className="font-heading text-2xl leading-tight font-semibold sm:text-3xl">
            Nothing planned yet
          </p>
          <p className="text-sm text-muted-foreground">
            {meals.length
              ? "Choose one of your meals, or type a new one. It's saved to your plan straight away."
              : "Type a meal's name to create it and plan it in one go."}
          </p>
          {picker(
            `Choose a meal for ${when}`,
            buttonVariants({ size: "lg" }),
            <>
              <Plus aria-hidden />
              Choose a meal
            </>,
          )}
          {suggestions.length > 0 && (
            <div className="mt-3 w-full">
              <p className="text-xs text-muted-foreground">Or in one click</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {suggestions.map((suggestion) => (
                  <li key={suggestion.id}>
                    <button
                      type="button"
                      onClick={() => onPick(suggestion)}
                      aria-label={`Plan ${suggestion.name} for ${when}`}
                      className="flex items-center gap-2 rounded-full border bg-background py-1 pr-3 pl-1 text-sm transition-colors outline-none hover:border-primary/40 hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring dark:bg-input/30"
                    >
                      <MealAvatar meal={suggestion} size="sm" />
                      {suggestion.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* At the foot of the card however tall the card is beside the stats. */}
      {tomorrow && (
        <div className="mt-auto pt-6">
          <p className="flex flex-wrap items-center gap-x-2 border-t pt-4 text-sm">
            <span className="text-muted-foreground">Tomorrow</span>
            {tomorrow.meal ? (
              <span className="flex items-center gap-2 font-medium">
                <MealAvatar meal={tomorrow.meal} size="sm" />
                {tomorrow.meal.name}
              </span>
            ) : (
              <AppLink
                to="/plan"
                params={{ day: tomorrow.day }}
                className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
              >
                Nothing yet, plan {tomorrow.day}
                <ArrowRight aria-hidden className="size-3.5" />
              </AppLink>
            )}
          </p>
        </div>
      )}
    </section>
  );
}
