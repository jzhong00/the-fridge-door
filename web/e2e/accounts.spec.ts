import { expect, test } from "@playwright/test";

import { addMeal, mealRow, openWeek, uniqueName } from "./helpers.ts";

test("each visitor gets their own guest session, invisible to anyone else", async ({
  browser,
}) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  try {
    const mine = await first.newPage();
    const theirs = await second.newPage();
    const name = uniqueName("Private Lasagne");

    await openWeek(mine, "2026-03-02");
    await addMeal(mine, name);

    await openWeek(theirs, "2026-03-02");
    await expect(theirs.getByLabel("Meal name")).toBeVisible();
    await expect(mealRow(theirs, name)).toHaveCount(0);

    // The first visitor's session survives a reload: the cookie is the account.
    await mine.reload();
    await expect(mealRow(mine, name)).toBeVisible();

    const cookies = await first.cookies();
    const session = cookies.find((cookie) => cookie.name === "__Host-session");
    expect(session).toMatchObject({ httpOnly: true, secure: true, sameSite: "Strict" });
  } finally {
    await first.close();
    await second.close();
  }
});
