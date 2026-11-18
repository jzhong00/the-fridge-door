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
      // An empty value removes the parameter rather than leaving `?name=`.
      if (next) url.searchParams.set(name, next);
      else url.searchParams.delete(name);
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
 * The part of a query string that follows a person from page to page: the
 * week they are looking at. Anything else belongs to the page it was set on
 * (which meal is open, say), and is left behind.
 */
export function carriedSearch(search: string): string {
  const week = new URLSearchParams(search).get("week");
  return week ? `?${new URLSearchParams({ week })}` : "";
}

/**
 * The address of another page, keeping the week and adding what that page
 * should open on: `linkTo("/plan", "?week=2026-11-16", { day: "Tuesday" })`
 * is "/plan?week=2026-11-16&day=Tuesday".
 */
export function linkTo(
  path: string,
  search: string,
  params: Readonly<Record<string, string>> = {},
): string {
  const query = new URLSearchParams(carriedSearch(search));
  for (const [name, value] of Object.entries(params)) query.set(name, value);
  const rest = query.toString();
  return rest ? `${path}?${rest}` : path;
}

/** Go to another page, keeping the week, and opening on `params`. */
export function navigate(path: string, params: Readonly<Record<string, string>> = {}): void {
  const here = path === window.location.pathname;
  // The link to the page already open does nothing, rather than resetting it.
  if (here && Object.keys(params).length === 0) return;
  const to = linkTo(path, window.location.search, params);
  if (here && to === window.location.pathname + window.location.search) return;
  window.history.pushState(null, "", to);
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
