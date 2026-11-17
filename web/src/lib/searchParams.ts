/**
 * State that lives in the URL's query string, so a refresh or a shared link
 * opens the same tab and week.
 *
 * Writes use `replaceState`, not `pushState`: clicking through weeks would
 * otherwise fill the back button with every week visited. Reads subscribe to
 * `popstate` and to this module's own writes, so every component using the
 * same parameter sees the same value.
 */

import { useCallback, useSyncExternalStore } from "react";

import { fromIso, mondayOf, toIso } from "./dates";

const CHANGED = "meal-planner:search-params-changed";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

const readSearch = () => window.location.search;

/**
 * One query-string parameter as React state.
 *
 * `parse` turns the raw value (or null when absent) into a valid value, so a
 * hand-edited or stale link falls back to a default instead of breaking.
 */
export function useSearchParam<T extends string>(
  name: string,
  parse: (raw: string | null) => T,
): [T, (next: T) => void] {
  const search = useSyncExternalStore(subscribe, readSearch, () => "");
  const value = parse(new URLSearchParams(search).get(name));

  const setValue = useCallback(
    (next: T) => {
      const url = new URL(window.location.href);
      url.searchParams.set(name, next);
      window.history.replaceState(window.history.state, "", url);
      window.dispatchEvent(new Event(CHANGED));
    },
    [name],
  );

  return [value, setValue];
}

/** A valid ISO date snapped to its Monday, or the current week otherwise. */
export function parseWeek(raw: string | null): string {
  if (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) && toIso(fromIso(raw)) === raw) {
    return mondayOf(fromIso(raw));
  }
  return mondayOf(new Date());
}
