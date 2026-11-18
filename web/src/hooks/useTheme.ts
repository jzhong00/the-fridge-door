import { useCallback, useEffect, useState } from "react";

import {
  applyTheme,
  DARK_QUERY,
  savedTheme,
  saveTheme,
  type Theme,
} from "@/lib/theme";

/**
 * The chosen theme and a way to change it. While the choice is "system",
 * the page follows the device switching between light and dark, as it does
 * at sunset on most phones, without a reload.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(savedTheme);

  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system" || !window.matchMedia) return;
    const query = window.matchMedia(DARK_QUERY);
    const follow = () => applyTheme("system");
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    saveTheme(next);
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
