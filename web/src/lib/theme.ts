/**
 * Light, dark, or whatever the device prefers. Dark by default.
 *
 * The choice is a per-browser convenience, so it lives in localStorage, not
 * on the account. public/theme.js applies it before first paint; these are
 * the same rules for the running app, and the two must stay in step.
 */

export const THEMES = ["light", "dark", "system"] as const;
export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = "dark";
export const THEME_STORAGE_KEY = "theme";
export const DARK_QUERY = "(prefers-color-scheme: dark)";

export function isTheme(value: unknown): value is Theme {
  return THEMES.includes(value as Theme);
}

/** The saved choice, or the default if there is none or storage is blocked. */
export function savedTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(saved) ? saved : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage blocked: the choice lasts until the page closes.
  }
}

export function systemPrefersDark(): boolean {
  return window.matchMedia?.(DARK_QUERY).matches ?? false;
}

/** Whether a theme shows dark right now. */
export function isDark(theme: Theme): boolean {
  return theme === "dark" || (theme === "system" && systemPrefersDark());
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", isDark(theme));
}
