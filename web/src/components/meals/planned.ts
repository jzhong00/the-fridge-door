import type { DayAssignment } from "@/api/types";

/** The days a meal is planned on, as "Mon", "Sat", in week order. */
export function plannedDays(plan: readonly DayAssignment[], mealId: number): string[] {
  return plan.filter((day) => day.meal_id === mealId).map((day) => day.day.slice(0, 3));
}
