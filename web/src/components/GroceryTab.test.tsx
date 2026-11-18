import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GroceryLine } from "@/api/types";
import { GroceryTab } from "@/components/GroceryTab";

const WEEK = "2026-08-03";
const lines: GroceryLine[] = [
  { name: "Beef Mince", qty: 1500, unit: "g", display: "1.5 kg" },
  { name: "Onion", qty: 2, unit: "", display: "2" },
  { name: "Pasta", qty: 400, unit: "g", display: "400 g" },
];

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/groceries");
});

function renderList(props: Partial<Parameters<typeof GroceryTab>[0]> = {}) {
  return render(<GroceryTab weekStart={WEEK} lines={lines} plannedDays={2} {...props} />);
}

const toGet = () => screen.getByRole("region", { name: /^To get/ });
const basket = () => screen.queryByRole("region", { name: /^In the basket/ });
const names = (region: HTMLElement) =>
  within(region)
    .getAllByRole("checkbox")
    .map((box) => box.closest("label")?.textContent);
const count = () => screen.getByText(/in the basket$/).parentElement;

describe("before there is a list", () => {
  it("waits while it loads", () => {
    renderList({ lines: null });
    expect(screen.getByRole("status")).toHaveTextContent("Loading the list…");
  });

  it("leads to planning when nothing is planned", () => {
    renderList({ lines: [], plannedDays: 0 });
    expect(screen.getByText(/Nothing is planned this week/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plan the week" })).toHaveAttribute("href", "/plan");
  });

  it("leads to the meals when what is planned has no ingredients", () => {
    renderList({ lines: [], plannedDays: 3 });
    expect(screen.getByText(/have no ingredients yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add ingredients" })).toHaveAttribute("href", "/meals");
  });
});

describe("shopping", () => {
  it("lists everything to get, with the amounts the API formatted", () => {
    renderList();

    // 1500 g arrives already turned into 1.5 kg by the domain layer.
    expect(names(toGet())).toEqual(["Beef Mince 1.5 kg", "Onion 2", "Pasta 400 g"]);
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).not.toBeChecked();
    expect(count()).toHaveTextContent("0of 3 in the basket");
    expect(basket()).not.toBeInTheDocument();
  });

  it("drops a ticked item into the basket, keeping the next one on top", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" }));

    expect(names(toGet())).toEqual(["Onion 2", "Pasta 400 g"]);
    expect(names(basket()!)).toEqual(["Beef Mince 1.5 kg"]);
    expect(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" })).toBeChecked();
    expect(count()).toHaveTextContent("1of 3 in the basket");
  });

  it("takes an item back out of the basket", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(screen.getByRole("checkbox", { name: "Onion 2" }));
    await user.click(screen.getByRole("checkbox", { name: "Onion 2" }));

    expect(names(toGet())).toEqual(["Beef Mince 1.5 kg", "Onion 2", "Pasta 400 g"]);
    expect(basket()).not.toBeInTheDocument();
  });

  it("keeps keyboard focus on the list: on the item that took the ticked one's place", async () => {
    const user = userEvent.setup();
    renderList();

    screen.getByRole("checkbox", { name: "Onion 2" }).focus();
    await user.keyboard(" ");
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).toHaveFocus();

    // The last one left: focus follows it into the basket.
    await user.keyboard(" ");
    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" }));
    expect(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" })).toHaveFocus();
    expect(screen.getByText("That's everything. Enjoy the cooking.")).toBeInTheDocument();
  });

  it("starts again with an empty basket", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(screen.getByRole("checkbox", { name: "Pasta 400 g" }));

    await user.click(screen.getByRole("button", { name: "Start again" }));

    expect(count()).toHaveTextContent("0of 3 in the basket");
    expect(screen.queryByRole("button", { name: "Start again" })).not.toBeInTheDocument();
  });
});

describe("the basket", () => {
  it("survives a reload, so a refresh mid-shop loses nothing", async () => {
    const user = userEvent.setup();
    const { unmount } = renderList();
    await user.click(screen.getByRole("checkbox", { name: "Pasta 400 g" }));
    unmount();

    renderList();
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).toBeChecked();
  });

  it("is kept per week", async () => {
    const user = userEvent.setup();
    const { rerender } = renderList();
    await user.click(screen.getByRole("checkbox", { name: "Pasta 400 g" }));

    rerender(<GroceryTab weekStart="2026-08-10" lines={lines} plannedDays={2} />);
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).not.toBeChecked();

    rerender(<GroceryTab weekStart={WEEK} lines={lines} plannedDays={2} />);
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).toBeChecked();
  });

  it("still works when the browser will not store it", async () => {
    const user = userEvent.setup();
    const blocked = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    try {
      renderList();
      await user.click(screen.getByRole("checkbox", { name: "Pasta 400 g" }));
      expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).toBeChecked();
    } finally {
      blocked.mockRestore();
    }
  });

  it("ignores a stored basket it cannot read", () => {
    localStorage.setItem(`meal-planner:basket:${WEEK}`, "{not json");
    renderList();
    expect(count()).toHaveTextContent("0of 3 in the basket");
  });
});

describe("sharing", () => {
  it("copies what is left to get", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    renderList();
    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" }));

    await user.click(screen.getByRole("button", { name: "Copy what's left" }));

    expect(writeText).toHaveBeenCalledWith("- Onion: 2\n- Pasta: 400 g");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});
