import type { IngredientAmount, Meal } from "@/api/types";

/**
 * A quantity without float noise or a trailing ".0": 400, 1.5, 0.33. Two
 * places, like the server's `units.format_qty`, so the grocery list and a
 * meal's ingredients agree.
 */
export function formatQty(qty: number): string {
  return String(Math.round(qty * 100) / 100);
}

/** "400 g", or "2" for a count. */
export function formatAmount(qty: number, unit: string): string {
  return `${formatQty(qty)} ${unit}`.trim();
}

/**
 * A meal's ingredients for a different number of people: a recipe for 4
 * cooked for 2 needs half of everything. The grocery list scales the same
 * way, server side.
 */
export function scaledIngredients(meal: Meal, servings: number): IngredientAmount[] {
  const scale = meal.servings > 0 ? servings / meal.servings : 1;
  return meal.ingredients.map((ingredient) => ({
    ...ingredient,
    qty: ingredient.qty * scale,
  }));
}
