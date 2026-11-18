import { Combobox } from "@base-ui/react/combobox";
import { Popover } from "@base-ui/react/popover";
import { Plus } from "lucide-react";
import { type ReactNode, useState } from "react";

import type { Meal } from "@/api/types";
import { MealAvatar } from "@/components/meals/MealAvatar";

type Item = { kind: "meal"; meal: Meal } | { kind: "create"; name: string };

const label = (item: Item) => (item.kind === "meal" ? item.meal.name : item.name);
const key = (item: Item) => (item.kind === "meal" ? `meal:${item.meal.id}` : "create");

/**
 * Choose a day's meal by typing a few letters. Meals already in this week's
 * plan come first, being the likeliest to repeat; anything typed that is
 * not a meal yet can be created right here, without leaving the plan.
 *
 * Base UI does the hard parts: the popover handles focus and Escape, and
 * the combobox inside it handles arrow keys, Enter and announcing all of it
 * to a screen reader.
 */
export function MealPicker({
  meals,
  plannedIds,
  current,
  title,
  triggerLabel,
  onPick,
  onCreate,
  children,
}: {
  meals: readonly Meal[];
  /** Meals planned somewhere this week, shown first. */
  plannedIds: ReadonlySet<number>;
  current: Meal | null;
  /** What the popup is for, for screen readers: "Choose a meal for Monday". */
  title: string;
  /**
   * The trigger's name, e.g. "Monday: Tacos". A combobox does not take its
   * name from its content as a button does, so without this a screen
   * reader would announce seven unnamed comboboxes.
   */
  triggerLabel: string;
  onPick: (meal: Meal) => void;
  onCreate: (name: string) => void;
  /** The trigger: the day's card content. */
  children: (props: { open: boolean }) => ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const ordered = [...meals].sort(
    (a, b) => Number(plannedIds.has(b.id)) - Number(plannedIds.has(a.id)),
  );
  const items: Item[] = ordered.map((meal) => ({ kind: "meal", meal }));
  const needle = query.trim().toLowerCase();
  const matches = items.filter((item) => label(item).toLowerCase().includes(needle));
  const exact = meals.some((m) => m.name.toLowerCase() === needle);
  const shown: Item[] =
    needle && !exact ? [...matches, { kind: "create", name: query.trim() }] : matches;

  const close = () => {
    setOpen(false);
    setQuery("");
  };

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      {/* A plain button, not the combobox's own trigger: that one picks a
          meal as soon as a letter is typed on it, the way a native select
          does, and with saving as you go one stray key would plan a meal. */}
      <Popover.Trigger
        aria-label={triggerLabel}
        className="flex w-full min-w-0 items-center gap-2.5 rounded-lg text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {children({ open })}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner align="start" sideOffset={6} className="z-50">
          {/* Focus goes to the search box, except on touch, where the popup
              itself takes it so the keyboard does not cover the list. */}
          <Popover.Popup
            aria-label={title}
            className="w-72 max-w-[var(--available-width)] origin-[var(--transform-origin)] overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-lg transition-[scale,opacity] duration-100 outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0"
          >
            <Combobox.Root<Item>
              inline
              open
              items={items}
              filteredItems={shown}
              value={current ? { kind: "meal", meal: current } : null}
              onValueChange={(item) => {
                if (!item) return;
                close();
                if (item.kind === "create") onCreate(item.name);
                else if (item.meal.id !== current?.id) onPick(item.meal);
              }}
              inputValue={query}
              onInputValueChange={setQuery}
              itemToStringLabel={label}
              isItemEqualToValue={(a, b) => key(a) === key(b)}
              autoHighlight
            >
              <div className="border-b p-2">
                <Combobox.Input
                  aria-label="Search meals"
                  placeholder={meals.length ? "Search meals, or type a new one" : "Type a meal's name"}
                  className="h-9 w-full rounded-md bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground"
                />
              </div>
        <Combobox.Empty>
          <p className="px-3 py-4 text-sm text-muted-foreground">
            Type a name to create your first meal.
          </p>
        </Combobox.Empty>
        <Combobox.List className="max-h-[min(20rem,var(--available-height))] overflow-y-auto overscroll-contain p-1 empty:p-0">
          {(item: Item) =>
            item.kind === "meal" ? (
              <Combobox.Item
                key={key(item)}
                value={item}
                className="flex cursor-default items-center gap-2.5 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-muted data-selected:font-medium"
              >
                <MealAvatar meal={item.meal} size="sm" />
                <span className="min-w-0 flex-1 truncate">{item.meal.name}</span>
                {plannedIds.has(item.meal.id) && (
                  <span className="shrink-0 text-xs text-muted-foreground">This week</span>
                )}
              </Combobox.Item>
            ) : (
              <Combobox.Item
                key={key(item)}
                value={item}
                className="flex cursor-default items-start gap-2.5 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-muted"
              >
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary-subtle text-primary-subtle-foreground">
                  <Plus aria-hidden className="size-3.5" />
                </span>
                <span className="min-w-0">
                  <span className="block">
                    New meal “<span className="font-medium">{item.name}</span>”
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    Add its ingredients on the Meals page
                  </span>
                </span>
              </Combobox.Item>
            )
          }
        </Combobox.List>
            </Combobox.Root>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
