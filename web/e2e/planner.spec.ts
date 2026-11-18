/**
 * The six flows the app exists for, in a real browser against the real API.
 *
 * Each spec works in its own week and names its own meals, so they do not
 * depend on each other or on the order they run in.
 */

import { expect, test } from "@playwright/test";

import { addMeal, chooseOption, goTo, mealRow, openWeek, pageLink, uniqueName } from "./helpers.ts";

test("add a meal", async ({ page }) => {
  await openWeek(page, "2026-01-05");
  const name = uniqueName("Lentil Soup");

  await addMeal(page, name, 6);

  await expect(page.getByText("Serves 6 · 0 ingredients")).toBeVisible();
});

test("add a meal from a template, ingredients included", async ({ page }) => {
  await openWeek(page, "2026-01-05");

  await page.getByRole("button", { name: /Quick add from templates/ }).click();
  await page.getByRole("button", { name: "Add Chicken Stir Fry" }).click();

  await expect(mealRow(page, "Chicken Stir Fry")).toBeVisible();
  // Within its own card: the sample meals a guest starts with have
  // summaries too.
  await expect(
    page.getByRole("article", { name: "Chicken Stir Fry" }).getByText("Serves 4 · 5 ingredients"),
  ).toBeVisible();
  // The template is marked as added, so it cannot be added twice.
  await expect(
    page.getByRole("button", { name: "Chicken Stir Fry (added)" }),
  ).toBeDisabled();
});

test("add an ingredient and edit its amount", async ({ page }) => {
  await openWeek(page, "2026-01-05");
  const name = uniqueName("Fried Rice");
  await addMeal(page, name);
  await chooseOption(page, "Select meal", name);

  await page.getByLabel("Ingredient", { exact: true }).fill("Rice");
  await page.getByLabel("Quantity", { exact: true }).fill("200");
  await page.getByLabel("Unit", { exact: true }).fill("g");
  await page.getByRole("button", { name: "Add ingredient" }).click();
  await expect(page.getByRole("button", { name: "Edit Rice" })).toContainText("200 g");

  await page.getByRole("button", { name: "Edit Rice" }).click();
  await page.getByLabel("Quantity of Rice").fill("300");
  await page.getByRole("button", { name: "Save", exact: true }).click();

  await expect(page.getByRole("button", { name: "Edit Rice" })).toContainText("300 g");
  // Saved to the server, not just the screen.
  await page.reload();
  await chooseOption(page, "Select meal", name);
  await expect(page.getByRole("button", { name: "Edit Rice" })).toContainText("300 g");
});

test("plan a week and save it", async ({ page }) => {
  await openWeek(page, "2026-01-12");
  const name = uniqueName("Shakshuka");
  await addMeal(page, name, 2);

  await goTo(page, "Plan");
  await chooseOption(page, "Monday", name);
  await expect(page.getByLabel("Serves")).toHaveValue("2");
  await page.getByRole("button", { name: "Save plan" }).click();
  await expect(page.getByRole("button", { name: "Save plan" })).toBeDisabled();

  // The URL keeps the page and week, so a reload lands on the saved plan.
  await page.reload();
  await expect(page).toHaveURL(/\/plan\?week=2026-01-12$/);
  await expect(pageLink(page, "Plan")).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("combobox", { name: "Monday" })).toContainText(name);
});

test("the grocery list totals the week and converts units", async ({ page }) => {
  await openWeek(page, "2026-01-19");
  // One of the sample meals every guest starts with.
  await expect(mealRow(page, "Spaghetti Bolognese")).toBeVisible();

  await goTo(page, "Plan");
  await chooseOption(page, "Monday", "Spaghetti Bolognese");
  await chooseOption(page, "Tuesday", "Spaghetti Bolognese");
  await page.getByRole("button", { name: "Save plan" }).click();
  await expect(page.getByRole("button", { name: "Save plan" })).toBeDisabled();

  await goTo(page, "Groceries");
  await page.getByRole("button", { name: "Generate list" }).click();

  // Two nights of a recipe using 400 g pasta and 500 g mince.
  await expect(page.getByRole("button", { name: /^Pasta\s*800 g$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Beef Mince\s*1 kg$/ })).toBeVisible();
});

test("copy last week's plan forward", async ({ page }) => {
  await openWeek(page, "2026-01-26", "plan");
  const name = uniqueName("Pho");
  await goTo(page, "Meals");
  await addMeal(page, name);
  await goTo(page, "Plan");
  await chooseOption(page, "Wednesday", name);
  await page.getByRole("button", { name: "Save plan" }).click();
  await expect(page.getByRole("button", { name: "Save plan" })).toBeDisabled();

  await page.getByRole("button", { name: "Next week" }).click();
  await expect(page.getByLabel("Week starting")).toHaveValue("2026-02-02");
  await expect(page.getByRole("combobox", { name: "Wednesday" })).toContainText("No meal");
  await page.getByRole("button", { name: "Copy previous week" }).click();

  await expect(page.getByRole("combobox", { name: "Wednesday" })).toContainText(name);
});
