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

/**
 * Add a meal the way a person does: New meal, a name and servings, Create.
 * The new meal then opens, ready for its ingredients.
 */
export async function addMeal(page: Page, name: string, servings = 4) {
  await page
    .getByRole("region", { name: "Your meals" })
    .getByRole("button", { name: "New meal" })
    .click();
  await page.getByLabel("Meal name").fill(name);
  await page.getByLabel("Servings").fill(String(servings));
  await page.getByRole("button", { name: "Create meal" }).click();
  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
}

/** A meal in the list of meals. */
export function mealRow(page: Page, name: string) {
  return page.getByRole("article", { name, exact: true });
}

type PageName = "meals" | "plan" | "groceries";

/**
 * Open a page at a week. Every spec works in its own week. Meals are the
 * same every week, so that page has no week picker; the week is still in
 * the URL, and the other pages pick it up.
 */
export async function openWeek(page: Page, week: string, where: PageName = "meals") {
  await page.goto(`/${where}?week=${week}`);
  if (where === "meals") {
    await expect(page.getByLabel("Search meals")).toBeVisible();
  } else {
    await expect(page.getByLabel("Week starting")).toHaveValue(week);
  }
}

/** Change page through the navigation, as a person would. */
export async function goTo(page: Page, label: "Meals" | "Plan" | "Groceries") {
  await pageLink(page, label).click();
}

export function pageLink(page: Page, label: "Meals" | "Plan" | "Groceries") {
  return page
    .getByRole("navigation", { name: "Pages" })
    .getByRole("link", { name: label, exact: true });
}
