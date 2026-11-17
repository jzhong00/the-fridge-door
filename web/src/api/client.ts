/**
 * Typed wrapper over the HTTP API.
 *
 * Every call goes through `request`, so error handling and JSON decoding
 * live in one place. Paths are relative: in development Vite proxies /api to
 * the local server, and in production Vercel serves both from one origin.
 */

import type {
  AppState,
  DayAssignment,
  GroceryLine,
  Meal,
  WeekPlan,
} from "./types";

/**
 * An error carrying the message the API wrote for the user.
 *
 * Every API error is an RFC 9457 problem: `detail` becomes the message,
 * `type` identifies the kind of failure for code that needs to branch on it,
 * and `requestId` matches the server's log lines for that request.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly type: string | null;
  readonly requestId: string | null;

  constructor(
    status: number,
    message: string,
    { type = null, requestId = null }: { type?: string | null; requestId?: string | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.type = type;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  // 204 No Content has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Build an ApiError from a failed response.
 *
 * The API writes `detail` as a sentence for the user, so it is shown as is.
 * Anything else in that field was written for developers and is replaced
 * with a generic message rather than leaking a field path into the UI.
 */
async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers?.get("X-Request-ID") ?? null;
  try {
    const body = await response.json();
    const type = typeof body?.type === "string" ? body.type : null;
    if (typeof body?.detail === "string") {
      return new ApiError(response.status, body.detail, { type, requestId });
    }
    if (body?.detail !== undefined) {
      return new ApiError(
        response.status,
        "That doesn't look right — please check the values and try again.",
        { type, requestId },
      );
    }
  } catch {
    // Body was not JSON; fall through to the status-based message.
  }
  return new ApiError(response.status, `Request failed (${response.status}).`, {
    requestId,
  });
}

export const api = {
  /** Everything needed to render a week, in one round trip. */
  getState: (week: string): Promise<AppState> =>
    request(`/api/state?week=${week}`),

  /** Just the day assignments. Meals and templates do not vary by week, so
   *  changing week fetches this rather than the whole of getState. */
  getPlan: (week: string): Promise<WeekPlan> => request(`/api/plan/${week}`),

  createMeal: (name: string, servings: number): Promise<Meal> =>
    request("/api/meals", {
      method: "POST",
      body: JSON.stringify({ name, servings }),
    }),

  createMealFromTemplate: (templateName: string): Promise<Meal> =>
    request(`/api/meals/from-template/${encodeURIComponent(templateName)}`, {
      method: "POST",
    }),

  updateMeal: (id: number, name: string, servings: number): Promise<Meal> =>
    request(`/api/meals/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name, servings }),
    }),

  deleteMeal: (id: number): Promise<void> =>
    request(`/api/meals/${id}`, { method: "DELETE" }),

  addIngredient: (
    mealId: number,
    name: string,
    qty: number,
    unit: string,
  ): Promise<Meal> =>
    request(`/api/meals/${mealId}/ingredients`, {
      method: "POST",
      body: JSON.stringify({ name, qty, unit }),
    }),

  updateIngredient: (
    mealId: number,
    ingredientId: number,
    qty: number,
    unit: string,
  ): Promise<Meal> =>
    request(`/api/meals/${mealId}/ingredients/${ingredientId}`, {
      method: "PATCH",
      body: JSON.stringify({ qty, unit }),
    }),

  removeIngredient: (mealId: number, ingredientId: number): Promise<Meal> =>
    request(`/api/meals/${mealId}/ingredients/${ingredientId}`, {
      method: "DELETE",
    }),

  setPlan: (week: string, days: DayAssignment[]): Promise<WeekPlan> =>
    request(`/api/plan/${week}`, {
      method: "PUT",
      body: JSON.stringify({ days }),
    }),

  copyPreviousWeek: (week: string): Promise<WeekPlan> =>
    request(`/api/plan/${week}/copy-previous`, { method: "POST" }),

  getGroceryList: (week: string): Promise<GroceryLine[]> =>
    request(`/api/grocery-list/${week}`),
};
