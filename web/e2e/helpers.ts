import { expect, type Page } from "@playwright/test";

/**
 * Choose an option from a Base UI Select. It is not a native <select>: the
 * trigger opens a listbox in a portal, and the option is clicked.
 */
export async function chooseOption(page: Page, trigger: string, option: string) {
  await page.getByRole("combobox", { name: trigger }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/**
 * A meal name no other spec uses. The specs share one database, and meal
 * names are unique, so each spec names its own meals.
 */
export function uniqueName(base: string): string {
  return `${base} ${Math.random().toString(36).slice(2, 7)}`;
}

/** Add a meal through the form on the Meals tab, and wait for it to appear. */
export async function addMeal(page: Page, name: string, servings = 4) {
  await page.getByLabel("Meal name").fill(name);
  await page.getByLabel("Servings").fill(String(servings));
  await page.getByRole("button", { name: "Add meal" }).click();
  await expect(mealRow(page, name)).toBeVisible();
}

/**
 * A meal in the "Your meals" list, found by its edit button. The name alone
 * is ambiguous: it also appears in the ingredient editor's meal picker.
 */
export function mealRow(page: Page, name: string) {
  return page.getByRole("button", { name: `Edit ${name}`, exact: true });
}

/** Open the week in a given tab. Every spec works in its own week. */
export async function openWeek(page: Page, week: string, tab = "meals") {
  await page.goto(`/?tab=${tab}&week=${week}`);
  await expect(page.getByLabel("Week starting")).toHaveValue(week);
}
