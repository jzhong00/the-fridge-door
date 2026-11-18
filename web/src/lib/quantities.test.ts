import { describe, expect, it } from "vitest";

import { makeMeal } from "@/test/factories";

import { formatAmount, formatQty, scaledIngredients } from "./quantities";

describe("formatQty", () => {
  it.each([
    [400, "400"],
    [1.5, "1.5"],
    [1 / 3, "0.33"],
    [0.1 + 0.2, "0.3"],
    [2.0, "2"],
  ])("writes %s as %s", (qty, text) => {
    expect(formatQty(qty)).toBe(text);
  });

  it("leaves no stray space after a count", () => {
    expect(formatAmount(2, "")).toBe("2");
    expect(formatAmount(250, "g")).toBe("250 g");
  });
});

describe("scaledIngredients", () => {
  const meal = makeMeal({
    servings: 4,
    ingredients: [{ ingredient_id: 1, name: "Rice", qty: 300, unit: "g" }],
  });

  it("scales a recipe to the number cooked for", () => {
    expect(scaledIngredients(meal, 2)[0].qty).toBe(150);
    expect(scaledIngredients(meal, 6)[0].qty).toBe(450);
  });

  it("leaves a recipe with no servings as written, rather than dividing by zero", () => {
    expect(scaledIngredients({ ...meal, servings: 0 }, 3)[0].qty).toBe(300);
  });
});
