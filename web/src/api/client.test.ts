import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./client";

function mockFetch(response: Partial<Response> & { json?: () => unknown }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
    ...response,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("error handling", () => {
  it("surfaces the message the API wrote for the user", async () => {
    mockFetch({
      ok: false,
      status: 409,
      json: async () => ({ detail: "A meal named 'Spaghetti' already exists." }),
    });

    await expect(api.createMeal("Spaghetti", 1)).rejects.toThrow(
      "A meal named 'Spaghetti' already exists.",
    );
  });

  it("exposes the status code on the error", async () => {
    mockFetch({ ok: false, status: 404, json: async () => ({ detail: "Nope" }) });

    await expect(api.deleteMeal(1)).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
    });
  });

  it("reads an RFC 9457 problem: detail, type and request id", async () => {
    mockFetch({
      ok: false,
      status: 422,
      headers: new Headers({ "X-Request-ID": "3f2b-req" }),
      json: async () => ({
        type: "urn:meal-planner:problem:request-validation",
        title: "Request validation failed",
        status: 422,
        detail: "Some of those values aren't valid. Check them and try again.",
        instance: "/api/meals",
        invalid_params: [{ name: "body.servings", reason: "greater than 0" }],
      }),
    });

    await expect(api.createMeal("X", 1)).rejects.toMatchObject({
      message: "Some of those values aren't valid. Check them and try again.",
      type: "urn:meal-planner:problem:request-validation",
      requestId: "3f2b-req",
    });
  });

  it("never shows a detail that is not a sentence", async () => {
    // Anything but a string was written for developers, not for the person
    // using the app, so it is replaced rather than rendered.
    mockFetch({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [{ loc: ["body", "qty"], msg: "greater than 0" }],
      }),
    });

    await expect(api.createMeal("X", 1)).rejects.toThrow(/check the values/i);
  });

  it("falls back to the status when the body is not JSON", async () => {
    mockFetch({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    });

    await expect(api.getState("2026-08-03")).rejects.toThrow("Request failed (500)");
  });
});

describe("requests", () => {
  it("does not try to parse a body from 204 No Content", async () => {
    mockFetch({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error("204 has no body to parse");
      },
    });

    await expect(api.deleteMeal(1)).resolves.toBeUndefined();
  });

  it("sends JSON and targets a relative path", async () => {
    const fetchMock = mockFetch({ json: async () => ({ id: 1 }) });

    await api.createMeal("Spaghetti", 4);

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/meals");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ name: "Spaghetti", servings: 4 });
  });

  it("escapes template names so spaces and slashes survive the URL", async () => {
    const fetchMock = mockFetch({ json: async () => ({ id: 1 }) });

    await api.createMealFromTemplate("Fish and Chips");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/meals/from-template/Fish%20and%20Chips",
    );
  });
});

describe("ApiError", () => {
  it("is an Error, so it works with normal error handling", () => {
    const error = new ApiError(404, "missing");
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe("missing");
  });
});

describe("signed-out requests", () => {
  const notSignedIn = {
    ok: false,
    status: 401,
    json: async () => ({
      type: "urn:meal-planner:problem:not-signed-in",
      detail: "Sign in, or continue as a guest, to do that.",
    }),
  };
  const ok = (body: unknown = {}) => ({ ok: true, status: 200, json: async () => body });

  it("start a guest session and are retried once", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(notSignedIn)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({}) })
      .mockResolvedValueOnce(ok({ meals: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.getState("2026-08-03")).resolves.toEqual({ meals: [] });
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/state?week=2026-08-03",
      "/api/auth/guest",
      "/api/state?week=2026-08-03",
    ]);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });

  it("share one guest session when several are signed out at once", async () => {
    let releaseGuest: (value: unknown) => void = () => {};
    let guestDone = false;
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/auth/guest") {
        return new Promise((resolve) => {
          releaseGuest = () => resolve({ ok: true, status: 201, json: async () => ({}) });
        });
      }
      const signedIn = fetchMock.mock.calls.some(([p]) => p === "/api/auth/guest");
      return Promise.resolve(signedIn && guestDone ? ok([]) : notSignedIn);
    });
    vi.stubGlobal("fetch", fetchMock);

    const first = api.getGroceryList("2026-08-03");
    const second = api.getPlan("2026-08-03");
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.filter(([p]) => p === "/api/auth/guest")).toHaveLength(1),
    );
    guestDone = true;
    releaseGuest(undefined);

    await Promise.all([first, second]);
    expect(fetchMock.mock.calls.filter(([p]) => p === "/api/auth/guest")).toHaveLength(1);
  });

  it("are not retried a second time", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(notSignedIn)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({}) })
      .mockResolvedValueOnce(notSignedIn);
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.getPlan("2026-08-03")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("other 401s are not treated as signed out", async () => {
    const fetchMock = mockFetch({
      ok: false,
      status: 401,
      json: async () => ({
        type: "urn:meal-planner:problem:invalid-credentials",
        detail: "That email and password don't match an account.",
      }),
    });

    await expect(api.getPlan("2026-08-03")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surface a failure to start the guest session", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(notSignedIn)
        .mockResolvedValueOnce({
          ok: false,
          status: 503,
          json: async () => ({ detail: "The database is unavailable." }),
        }),
    );

    await expect(api.getPlan("2026-08-03")).rejects.toThrow("The database is unavailable.");
  });
});
