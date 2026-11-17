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
