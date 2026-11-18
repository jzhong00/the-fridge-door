import { beforeEach, describe, expect, it } from "vitest";

import { navigate, redirectLegacyTabLink } from "./location";

const here = () => window.location.pathname + window.location.search;

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("links from when pages were tabs", () => {
  it.each([
    ["/?tab=meals&week=2026-08-03", "/meals?week=2026-08-03"],
    ["/?tab=plan", "/plan"],
    ["/?tab=grocery&week=2026-08-03", "/groceries?week=2026-08-03"],
    ["/?tab=settings&week=2026-08-03", "/?week=2026-08-03"],
  ])("%s opens %s", (old, now) => {
    window.history.replaceState(null, "", old);
    redirectLegacyTabLink();
    expect(here()).toBe(now);
  });

  it("leaves every other address alone", () => {
    window.history.replaceState(null, "", "/meals?tab=plan");
    redirectLegacyTabLink();
    expect(here()).toBe("/meals?tab=plan");
  });

  it("replaces the old address rather than adding to history", () => {
    window.history.replaceState(null, "", "/?tab=plan");
    const before = window.history.length;
    redirectLegacyTabLink();
    expect(window.history.length).toBe(before);
  });
});

describe("changing page", () => {
  it("adds to history and keeps the week", () => {
    window.history.replaceState(null, "", "/plan?week=2026-08-03");
    const before = window.history.length;
    navigate("/groceries");
    expect(here()).toBe("/groceries?week=2026-08-03");
    expect(window.history.length).toBe(before + 1);
  });

  it("does nothing when already there", () => {
    window.history.replaceState(null, "", "/plan");
    const before = window.history.length;
    navigate("/plan");
    expect(window.history.length).toBe(before);
  });
});
