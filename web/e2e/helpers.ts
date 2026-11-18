import { expect, type Page } from "@playwright/test";

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

/** A day's meal button on the plan, named "Monday: Tacos" or "Monday: no meal". */
export function dayPicker(page: Page, day: string) {
  return page.getByRole("button", { name: new RegExp(`^${day}: `) });
}

/**
 * Plan a meal on a day as a person does (open the day, type the name, Enter)
 * and wait until the change has been saved to the server.
 */
export async function planDay(page: Page, day: string, meal: string) {
  await dayPicker(page, day).click();
  await expect(page.getByRole("combobox", { name: "Search meals" })).toBeFocused();
  await page.keyboard.type(meal);
  await expect(page.getByRole("option").first()).toContainText(meal);
  const saved = page.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().includes("/api/plan/"),
  );
  await page.keyboard.press("Enter");
  expect((await saved).ok()).toBe(true);
  await expect(dayPicker(page, day)).toHaveAccessibleName(`${day}: ${meal}`);
}
