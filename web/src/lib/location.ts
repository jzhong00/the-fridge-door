/**
 * The URL as React state: which page (the path) and which week (`?week=`),
 * so a refresh, the back button or a shared link opens the same view.
 *
 * Four pages need no router library: the path is read with
 * `useSyncExternalStore`, and changed with the History API.
 *
 * - Changing page uses `pushState`, so the back button goes back a page.
 * - Changing week uses `replaceState`: clicking through weeks would
 *   otherwise fill the back button with every week visited.
 *
 * Reads subscribe to `popstate` and to this module's own writes, so every
 * component reading the URL sees the same value.
 */

import { useCallback, useSyncExternalStore } from "react";

import { fromIso, mondayOf, toIso } from "./dates";

const CHANGED = "meal-planner:location-changed";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

function changed() {
  window.dispatchEvent(new Event(CHANGED));
}

const readSearch = () => window.location.search;
const readPath = () => window.location.pathname;

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
      changed();
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

/** The current query string, e.g. "?week=2026-11-16". */
export function useSearch(): string {
  return useSyncExternalStore(subscribe, readSearch, () => "");
}

/** The current path, e.g. "/meals". */
export function usePathname(): string {
  return useSyncExternalStore(subscribe, readPath, () => "/");
}

/**
 * Go to another page, keeping the query string: the week a person is
 * looking at stays the same when they change page.
 */
export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  window.history.pushState(null, "", path + window.location.search);
  window.scrollTo(0, 0);
  changed();
}

/** Where each page lived when pages were tabs: `/?tab=grocery`. */
const LEGACY_TABS: Record<string, string> = {
  meals: "/meals",
  plan: "/plan",
  grocery: "/groceries",
};

/**
 * Rewrite a link from before pages had paths, so it still opens the page it
 * meant to, with its week. Run once, before the app renders.
 */
export function redirectLegacyTabLink(): void {
  const url = new URL(window.location.href);
  const tab = url.searchParams.get("tab");
  if (url.pathname !== "/" || tab === null) return;
  url.searchParams.delete("tab");
  url.pathname = LEGACY_TABS[tab] ?? "/";
  window.history.replaceState(window.history.state, "", url);
}
