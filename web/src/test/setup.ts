import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Node 25+ has Web Storage built in: a `localStorage` global that is
// undefined unless Node was started with --localstorage-file, and it shadows
// jsdom's. Put jsdom's back, so code under test gets a working one, as it
// would in a browser.
const dom = (globalThis as { jsdom?: { window: Window } }).jsdom;
if (dom && !globalThis.localStorage) {
  Object.defineProperty(globalThis, "localStorage", {
    value: dom.window.localStorage,
    configurable: true,
    writable: true,
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// jsdom has no layout, so it reports `scrollTo` as not implemented (loudly).
// Changing page scrolls to the top; here there is nothing to scroll.
window.scrollTo = () => {};
