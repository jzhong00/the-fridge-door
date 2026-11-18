import type { Meal } from "@/api/types";
import { cn } from "@/lib/utils";

/**
 * A meal's colour, from its id rather than its name, so renaming a meal
 * does not change how it is recognised everywhere else. Text is a 700/800
 * shade on light (AA on its own tint) and a 300 shade on dark.
 */
const TONES = [
  "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  "bg-amber-500/20 text-amber-800 dark:text-amber-300",
  "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  "bg-sky-500/15 text-sky-800 dark:text-sky-300",
  "bg-lime-500/20 text-lime-800 dark:text-lime-300",
  "bg-orange-500/15 text-orange-800 dark:text-orange-300",
  "bg-teal-500/15 text-teal-800 dark:text-teal-300",
  "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300",
] as const;

/**
 * A round tile with the meal's initial in its colour: the same meal looks
 * the same in the list, its panel and the plan, so it can be spotted
 * without reading. Decorative: the meal's name is always next to it.
 */
export function MealAvatar({
  meal,
  size = "md",
}: {
  meal: Pick<Meal, "id" | "name">;
  size?: "sm" | "md" | "lg";
}) {
  const initial = Array.from(meal.name.trim())[0]?.toUpperCase() ?? "?";
  return (
    <span
      aria-hidden
      className={cn(
        "grid shrink-0 place-items-center rounded-full font-semibold",
        size === "sm" && "size-6 text-xs",
        size === "md" && "size-9 text-sm",
        size === "lg" && "size-12 font-heading text-xl",
        TONES[Math.abs(meal.id) % TONES.length],
      )}
    >
      {initial}
    </span>
  );
}
