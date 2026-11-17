/**
 * Server state is held by TanStack Query, one cache entry per resource.
 *
 * Every change to the data goes through this client, and each mutation
 * patches the cache from the API's response. So nothing goes stale behind
 * the app's back, and cached data never needs a background refetch: a week
 * visited once is served from memory until the page reloads.
 */

import { QueryClient } from "@tanstack/react-query";

export const queryKeys = {
  /** Meals, ingredient names and templates: everything not tied to a week. */
  library: ["library"] as const,
  plans: ["plan"] as const,
  plan: (week: string) => ["plan", week] as const,
  groceries: ["grocery"] as const,
  grocery: (week: string) => ["grocery", week] as const,
};

export function createQueryClient({ retry = 1 }: { retry?: number | false } = {}) {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: 30 * 60 * 1000,
        refetchOnWindowFocus: false,
        retry,
      },
      mutations: { retry: false },
    },
  });
}
