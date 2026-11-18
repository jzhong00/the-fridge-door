import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AppState, DayAssignment, Meal, WeekPlan } from "@/api/types";
import { WeeklyPlanTab } from "@/components/WeeklyPlanTab";
import { makeMeal, makeState } from "@/test/factories";

const WEEK = "2026-08-03";
const spaghetti = makeMeal({ id: 1, name: "Spaghetti", servings: 4 });
const tacos = makeMeal({ id: 2, name: "Tacos", servings: 2 });
const curry = makeMeal({ id: 3, name: "Curry", servings: 6 });

const echo = async (week: string, days: DayAssignment[]): Promise<WeekPlan | null> => ({
  week_start: week,
  days,
});

function renderPlan(state: Partial<AppState> = {}) {
  const props = {
    state: makeState({ week_start: WEEK, meals: [spaghetti, tacos, curry], ...state }),
    pending: false,
    onSave: vi.fn(echo),
    onCopyPrevious: vi.fn(async (): Promise<WeekPlan | null> => null),
    onCreateMeal: vi.fn(async (): Promise<Meal | null> => null),
  };
  return { ...render(<WeeklyPlanTab {...props} />), props };
}

const day = (name: string) => screen.getByRole("listitem", { name });
const picker = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name}:`) });
const saveState = () => screen.getByText(/^(Saving…|Saved|Not saved)$/);

/** Open a day's search, waiting for the cursor to arrive as a person would. */
async function open(user: UserEvent, dayName: string) {
  await user.click(picker(dayName));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Search meals" })).toHaveFocus());
}

/** Open a day, type, and take the first match, as a keyboard user would. */
async function choose(user: UserEvent, dayName: string, typed: string) {
  await open(user, dayName);
  await user.keyboard(typed);
  // The meal, and below it the offer to create a new meal by that name.
  await screen.findAllByRole("option", { name: new RegExp(typed, "i") });
  await user.keyboard("{Enter}");
}

/** The days sent in the most recent save, by day. */
function lastSaved(onSave: ReturnType<typeof vi.fn>): Record<string, DayAssignment> {
  const call = onSave.mock.lastCall;
  if (!call) throw new Error("Nothing has been saved.");
  return Object.fromEntries((call[1] as DayAssignment[]).map((d) => [d.day, d]));
}

describe("the week", () => {
  it("shows every day with its date, and how much of the week is planned", () => {
    renderPlan({
      plan: [
        { day: "Monday", meal_id: 1, servings: 4 },
        { day: "Thursday", meal_id: 2, servings: 2 },
      ],
    });

    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    expect(day("Monday")).toHaveTextContent("Mon 3");
    expect(day("Sunday")).toHaveTextContent("Sun 9");
    expect(screen.getByText("of 7 nights planned").parentElement).toHaveTextContent(
      "2 of 7 nights planned",
    );
    expect(picker("Monday")).toHaveAccessibleName("Monday: Spaghetti");
    expect(picker("Tuesday")).toHaveAccessibleName("Tuesday: no meal");
    expect(within(day("Thursday")).getByText("2")).toBeInTheDocument();
  });
});

describe("choosing a meal", () => {
  it("plans it with a few letters and Enter, and saves straight away", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan();

    await choose(user, "Tuesday", "tac");

    expect(picker("Tuesday")).toHaveAccessibleName("Tuesday: Tacos");
    expect(props.onSave).toHaveBeenCalledWith(WEEK, expect.any(Array));
    // A new day starts at the recipe's own servings.
    expect(lastSaved(props.onSave).Tuesday).toEqual({ day: "Tuesday", meal_id: 2, servings: 2 });
    // Every day is sent, planned or not: the API replaces the week.
    expect(props.onSave.mock.lastCall?.[1]).toHaveLength(7);
  });

  it("keeps a day's servings when swapping its meal", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan({ plan: [{ day: "Monday", meal_id: 1, servings: 3 }] });

    await choose(user, "Monday", "curry");

    expect(lastSaved(props.onSave).Monday).toEqual({ day: "Monday", meal_id: 3, servings: 3 });
  });

  it("lists meals already planned this week first", async () => {
    const user = userEvent.setup();
    renderPlan({ plan: [{ day: "Friday", meal_id: 3, servings: 6 }] });

    await open(user, "Monday");
    const options = await screen.findAllByRole("option");

    expect(options[0]).toHaveTextContent("Curry");
    expect(options[0]).toHaveTextContent("This week");
  });

  it("creates a meal that does not exist yet, and plans it", async () => {
    const user = userEvent.setup();
    const pie = makeMeal({ id: 9, name: "Fish Pie", servings: 4 });
    const { props } = renderPlan();
    props.onCreateMeal.mockResolvedValue(pie);

    await open(user, "Wednesday");
    await user.keyboard("Fish Pie");
    await user.click(await screen.findByRole("option", { name: /New meal “Fish Pie”/ }));

    expect(props.onCreateMeal).toHaveBeenCalledWith("Fish Pie", 4);
    await waitFor(() =>
      expect(lastSaved(props.onSave).Wednesday).toEqual({
        day: "Wednesday",
        meal_id: 9,
        servings: 4,
      }),
    );
  });

  it("does nothing when a letter is typed on a closed day", async () => {
    // A native select picks an option on a keypress; with saving as you go,
    // tabbing through the week and typing would plan meals by accident.
    const user = userEvent.setup();
    const { props } = renderPlan();

    picker("Monday").focus();
    await user.keyboard("t");

    expect(props.onSave).not.toHaveBeenCalled();
    expect(picker("Monday")).toHaveAccessibleName("Monday: no meal");
  });

  it("choosing the meal a day already has changes nothing", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan({ plan: [{ day: "Monday", meal_id: 1, servings: 4 }] });

    await choose(user, "Monday", "spag");

    expect(props.onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not offer to create a meal that already exists", async () => {
    const user = userEvent.setup();
    renderPlan();

    await open(user, "Monday");
    await user.keyboard("tacos");

    expect(await screen.findByRole("option", { name: /Tacos/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /New meal/ })).not.toBeInTheDocument();
  });
});

describe("servings and clearing", () => {
  const planned = { plan: [{ day: "Monday" as const, meal_id: 1, servings: 2 }] };

  it("steps servings up and down, never below one", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan(planned);

    await user.click(screen.getByRole("button", { name: "More servings on Monday" }));
    expect(lastSaved(props.onSave).Monday.servings).toBe(3);

    await user.click(screen.getByRole("button", { name: "Fewer servings on Monday" }));
    await user.click(screen.getByRole("button", { name: "Fewer servings on Monday" }));
    expect(lastSaved(props.onSave).Monday.servings).toBe(1);
    expect(screen.getByRole("button", { name: "Fewer servings on Monday" })).toBeDisabled();
  });

  it("clears a day", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan(planned);

    await user.click(screen.getByRole("button", { name: "Clear Monday" }));

    expect(lastSaved(props.onSave).Monday).toEqual({ day: "Monday", meal_id: null, servings: null });
    expect(picker("Monday")).toHaveAccessibleName("Monday: no meal");
  });
});

describe("saving", () => {
  it("says when it is saving and when it is saved", async () => {
    const user = userEvent.setup();
    let finish!: (plan: WeekPlan) => void;
    const { props } = renderPlan();
    props.onSave.mockImplementation(() => new Promise((resolve) => (finish = resolve)));

    await choose(user, "Monday", "spag");
    expect(saveState()).toHaveTextContent("Saving…");

    await act(async () => finish({ week_start: WEEK, days: [] }));
    expect(saveState()).toHaveTextContent("Saved");
  });

  it("merges changes made during a save into one follow-up save", async () => {
    const user = userEvent.setup();
    const finishers: ((plan: WeekPlan) => void)[] = [];
    const { props } = renderPlan({ plan: [{ day: "Monday", meal_id: 1, servings: 2 }] });
    props.onSave.mockImplementation(() => new Promise((resolve) => finishers.push(resolve)));
    const more = screen.getByRole("button", { name: "More servings on Monday" });

    await user.click(more); // 3, sent
    await user.click(more); // 4, waits
    await user.click(more); // 5, replaces 4
    expect(props.onSave).toHaveBeenCalledTimes(1);

    await act(async () => finishers[0]({ week_start: WEEK, days: [] }));
    expect(props.onSave).toHaveBeenCalledTimes(2);
    expect(lastSaved(props.onSave).Monday.servings).toBe(5);
  });

  it("puts back what is really saved when a save fails", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan({ plan: [{ day: "Monday", meal_id: 1, servings: 4 }] });
    props.onSave.mockResolvedValue(null);

    await choose(user, "Monday", "tacos");

    await waitFor(() => expect(saveState()).toHaveTextContent("Not saved"));
    expect(picker("Monday")).toHaveAccessibleName("Monday: Spaghetti");
  });

  it("saves to the week the change was made in, even after changing week", async () => {
    const user = userEvent.setup();
    let finish!: (plan: WeekPlan) => void;
    const { props, rerender } = renderPlan();
    props.onSave.mockImplementation(() => new Promise((resolve) => (finish = resolve)));

    await choose(user, "Monday", "spag");
    rerender(
      <WeeklyPlanTab
        {...props}
        state={makeState({ week_start: "2026-08-10", meals: [spaghetti, tacos, curry] })}
      />,
    );
    await act(async () => finish({ week_start: WEEK, days: [] }));

    expect(props.onSave).toHaveBeenCalledTimes(1);
    expect(props.onSave).toHaveBeenCalledWith(WEEK, expect.any(Array));
    // The new week shows its own (empty) plan, not the change.
    expect(picker("Monday")).toHaveAccessibleName("Monday: no meal");
  });
});

describe("undo", () => {
  it("puts the week back as it was before the last change", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan({ plan: [{ day: "Monday", meal_id: 1, servings: 4 }] });

    await choose(user, "Monday", "tacos");
    await user.click(screen.getByRole("button", { name: "Undo Tacos on Monday" }));

    expect(lastSaved(props.onSave).Monday).toEqual({ day: "Monday", meal_id: 1, servings: 4 });
    expect(picker("Monday")).toHaveAccessibleName("Monday: Spaghetti");
    expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
  });

  it("undoes copying last week", async () => {
    const user = userEvent.setup();
    const { props } = renderPlan({ plan: [{ day: "Monday", meal_id: 1, servings: 4 }] });
    props.onCopyPrevious.mockResolvedValue({ week_start: WEEK, days: [] });

    await user.click(screen.getByRole("button", { name: /copy last week/i }));
    expect(props.onCopyPrevious).toHaveBeenCalledWith(WEEK);
    await user.click(await screen.findByRole("button", { name: "Undo copying last week" }));

    expect(lastSaved(props.onSave).Monday).toEqual({ day: "Monday", meal_id: 1, servings: 4 });
  });

  it("is forgotten on changing week, where it would rewrite the wrong week", async () => {
    const user = userEvent.setup();
    const { props, rerender } = renderPlan();

    await choose(user, "Monday", "spag");
    expect(screen.getByRole("button", { name: /^Undo/ })).toBeInTheDocument();
    rerender(
      <WeeklyPlanTab
        {...props}
        state={makeState({ week_start: "2026-08-10", meals: [spaghetti, tacos, curry] })}
      />,
    );

    expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
  });

  it("is not offered when a copy fails", async () => {
    const user = userEvent.setup();
    renderPlan();

    await user.click(screen.getByRole("button", { name: /copy last week/i }));

    expect(screen.queryByRole("button", { name: /^Undo/ })).not.toBeInTheDocument();
  });
});

describe("following the server", () => {
  it("shows a plan that changed elsewhere", () => {
    const { props, rerender } = renderPlan();

    rerender(
      <WeeklyPlanTab
        {...props}
        state={makeState({
          week_start: WEEK,
          meals: [spaghetti, tacos, curry],
          plan: [{ day: "Friday", meal_id: 2, servings: 2 }],
        })}
      />,
    );

    expect(picker("Friday")).toHaveAccessibleName("Friday: Tacos");
  });
});
