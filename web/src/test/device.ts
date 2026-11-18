import { vi } from "vitest";

/**
 * A device whose light/dark preference the test controls. jsdom has no
 * matchMedia, so this stands in for it; undo with vi.unstubAllGlobals().
 */
export function fakeDevice(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  const query = {
    get matches() {
      return prefersDark;
    },
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", () => query);
  return {
    switchTo(dark: boolean) {
      prefersDark = dark;
      listeners.forEach((listener) => listener());
    },
    listening: () => listeners.size,
  };
}
