import { ChevronRight, Plus, Search } from "lucide-react";
import { useState } from "react";

import type { DayAssignment, Meal } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { MealAvatar } from "./MealAvatar";
import { plannedDays } from "./planned";

/**
 * Every meal, searchable, each one a single target that opens it. Creating
 * a meal starts here too, so the list is the one place a meal is found.
 */
export function MealList({
  meals,
  plan,
  selectedId,
  onSelect,
  onNew,
  className,
}: {
  meals: readonly Meal[];
  plan: readonly DayAssignment[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  className?: string;
}) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = needle ? meals.filter((m) => m.name.toLowerCase().includes(needle)) : meals;

  return (
    <section aria-label="Your meals" className={cn("rounded-xl border bg-card", className)}>
      <div className="flex items-center gap-2 border-b p-3">
        <div className="relative min-w-0 flex-1">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            aria-label="Search meals"
            placeholder="Search meals"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-8"
          />
        </div>
        <Button onClick={onNew}>
          <Plus aria-hidden />
          New meal
        </Button>
      </div>

      {meals.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-muted-foreground">
          No meals yet. Create one, or start from a template.
        </p>
      ) : shown.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-muted-foreground">
          No meals match “{query.trim()}”.
        </p>
      ) : (
        <ul className="space-y-0.5 p-1.5">
          {shown.map((meal) => {
            const days = plannedDays(plan, meal.id);
            return (
              <li key={meal.id}>
                <article aria-label={meal.name}>
                  <button
                    type="button"
                    onClick={() => onSelect(meal.id)}
                    aria-current={meal.id === selectedId ? "true" : undefined}
                    className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:bg-primary-subtle"
                  >
                    <MealAvatar meal={meal} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{meal.name}</span>
                      <span className="block text-xs text-muted-foreground">
                        Serves {meal.servings} · {meal.ingredients.length} ingredient
                        {meal.ingredients.length === 1 ? "" : "s"}
                      </span>
                    </span>
                    {days.length > 0 && (
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {days.join(" · ")}
                      </span>
                    )}
                    <ChevronRight aria-hidden className="size-4 shrink-0 text-muted-foreground lg:hidden" />
                  </button>
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
