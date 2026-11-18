import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import type { Day } from "@/api/types";
import { DAYS } from "@/api/types";
import { AppLink } from "@/components/AppLink";
import { DAY_FILL } from "@/components/plan/days";
import { cn } from "@/lib/utils";

/**
 * Three numbers for the week, each leading to what to do about it: the
 * nights still to plan open the first of them on the plan; the items to
 * buy open the grocery list.
 */
export function WeekStats({
  plannedDays,
  servings,
  mealCount,
  itemsToBuy,
}: {
  plannedDays: ReadonlySet<Day>;
  servings: number;
  /** Different meals planned. */
  mealCount: number;
  /** Lines on the grocery list, or null while it loads. */
  itemsToBuy: number | null;
}) {
  const next = DAYS.find((day) => !plannedDays.has(day));

  return (
    // On a phone, the nights across the top and the two counts side by side
    // under it, rather than three cards stacked a screen and a half tall.
    <div className="grid grid-cols-2 content-start gap-3 sm:grid-cols-3 xl:grid-cols-1">
      <Stat
        className="col-span-2 sm:col-span-1"
        label="Nights planned"
        value={plannedDays.size}
        of="of 7"
        detail={next ? `Next: plan ${next}` : "Every night is planned"}
        to="/plan"
        params={next ? { day: next } : undefined}
      >
        {/* Each night in its own colour once planned, in week order, so the
            bar also shows which nights are left. */}
        <div aria-hidden className="mt-3 grid grid-cols-7 gap-1">
          {DAYS.map((day) => (
            <span
              key={day}
              className={cn(
                "h-1.5 rounded-full",
                plannedDays.has(day) ? DAY_FILL[day] : "bg-muted",
              )}
            />
          ))}
        </div>
      </Stat>

      <Stat
        label="Servings"
        value={servings}
        detail={
          mealCount
            ? `Across ${mealCount} different meal${mealCount === 1 ? "" : "s"}`
            : "Nothing planned yet"
        }
      />

      <Stat
        label="To buy"
        value={itemsToBuy ?? "…"}
        of={itemsToBuy === null ? undefined : itemsToBuy === 1 ? "item" : "items"}
        detail={
          itemsToBuy === 0 && plannedDays.size === 0
            ? "Plan a meal to start a list"
            : "Open the grocery list"
        }
        to="/groceries"
        busy={itemsToBuy === null}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  of,
  detail,
  to,
  params,
  busy = false,
  className,
  children,
}: {
  className?: string;
  label: string;
  value: number | string;
  /** What the value is out of, or counts: "of 7", "items". */
  of?: string;
  detail: string;
  /** Where acting on the number happens, if anywhere. */
  to?: string;
  params?: Readonly<Record<string, string>>;
  busy?: boolean;
  children?: ReactNode;
}) {
  const body = (
    <>
      <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
        {label}
        {to && <ChevronRight aria-hidden className="size-4" />}
      </span>
      <span className="mt-1 flex items-baseline gap-1.5">
        <span className="font-heading text-3xl font-semibold tabular-nums">{value}</span>
        {of && <span className="text-sm text-muted-foreground">{of}</span>}
      </span>
      {children}
      <span
        className={cn(
          "mt-2 block text-sm",
          to ? "font-medium text-primary" : "text-muted-foreground",
        )}
      >
        {detail}
      </span>
    </>
  );
  const style = cn("block rounded-xl border bg-card p-4", className);

  return to ? (
    <AppLink
      to={to}
      params={params}
      aria-busy={busy || undefined}
      className={cn(
        style,
        "outline-none transition-colors hover:border-primary/40 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {body}
    </AppLink>
  ) : (
    <div className={style}>{body}</div>
  );
}
