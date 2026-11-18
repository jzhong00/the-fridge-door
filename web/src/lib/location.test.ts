import { beforeEach, describe, expect, it } from "vitest";

import { linkTo, navigate, redirectLegacyTabLink } from "./location";

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

  it("leaves behind what belonged to the last page", () => {
    window.history.replaceState(null, "", "/meals?week=2026-08-03&meal=4");
    navigate("/plan");
    expect(here()).toBe("/plan?week=2026-08-03");
  });

  it("does nothing when already there", () => {
    window.history.replaceState(null, "", "/plan");
    const before = window.history.length;
    navigate("/plan");
    expect(window.history.length).toBe(before);
  });

  it("does not reset the page it is on, so the open meal stays open", () => {
    window.history.replaceState(null, "", "/meals?week=2026-08-03&meal=4");
    navigate("/meals");
    expect(here()).toBe("/meals?week=2026-08-03&meal=4");
  });
});

describe("a link to another page", () => {
  it("keeps the week and adds what that page should open on", () => {
    expect(linkTo("/plan", "?week=2026-08-03&meal=4", { day: "Tuesday" })).toBe(
      "/plan?week=2026-08-03&day=Tuesday",
    );
    expect(linkTo("/groceries", "")).toBe("/groceries");
  });

  it("is followed in place, opening on what it names", () => {
    window.history.replaceState(null, "", "/?week=2026-08-03");
    navigate("/plan", { day: "Friday" });
    expect(here()).toBe("/plan?week=2026-08-03&day=Friday");
  });
});
