import type { Day } from "@/api/types";

/*
 * Each day's colour, the same wherever a day appears: the edge of its card
 * on the plan, its cell in the week strip, its share of the progress bar.
 * Written out in full because Tailwind finds classes by reading the source;
 * `border-t-${day}` would never be generated.
 */

export const DAY_EDGE: Record<Day, string> = {
  Monday: "border-t-mon",
  Tuesday: "border-t-tue",
  Wednesday: "border-t-wed",
  Thursday: "border-t-thu",
  Friday: "border-t-fri",
  Saturday: "border-t-sat",
  Sunday: "border-t-sun",
};

export const DAY_FILL: Record<Day, string> = {
  Monday: "bg-mon",
  Tuesday: "bg-tue",
  Wednesday: "bg-wed",
  Thursday: "bg-thu",
  Friday: "bg-fri",
  Saturday: "bg-sat",
  Sunday: "bg-sun",
};
