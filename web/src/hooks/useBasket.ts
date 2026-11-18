import { useState } from "react";

/**
 * What is already in the basket for a week: the grocery lines ticked off.
 *
 * Kept in this browser, per week, so a refresh or a detour to another page
 * in the middle of the shop does not lose your place. It is a shopping aid
 * for whoever holds the phone, not shared data, so it is not worth a round
 * trip or a database column. Storage can be unavailable (private windows,
 * blocked site data); then the basket simply lasts as long as the page.
 */
export function useBasket(week: string) {
  const [basket, setBasket] = useState(() => ({ week, keys: read(week) }));

  // A new week has its own basket. Adjusted during render, so the old
  // week's ticks are never shown against the new week's list.
  let current = basket;
  if (basket.week !== week) {
    current = { week, keys: read(week) };
    setBasket(current);
  }

  const update = (keys: ReadonlySet<string>) => {
    write(week, keys);
    setBasket({ week, keys });
  };

  return {
    keys: current.keys,
    toggle: (key: string) => {
      const next = new Set(current.keys);
      if (!next.delete(key)) next.add(key);
      update(next);
    },
    empty: () => update(new Set()),
  };
}

const storageKey = (week: string) => `meal-planner:basket:${week}`;

function read(week: string): ReadonlySet<string> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey(week)) ?? "[]");
    return new Set(
      Array.isArray(parsed) ? parsed.filter((k): k is string => typeof k === "string") : [],
    );
  } catch {
    return new Set();
  }
}

function write(week: string, keys: ReadonlySet<string>) {
  try {
    if (keys.size) localStorage.setItem(storageKey(week), JSON.stringify([...keys]));
    else localStorage.removeItem(storageKey(week));
  } catch {
    // Not saved; the basket still works for as long as the page is open.
  }
}
