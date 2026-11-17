import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { api } from "@/api/client";
import { createQueryClient } from "@/api/queryClient";
import { makeMeal, makeState } from "@/test/factories";

vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  api: { getState: vi.fn(), getPlan: vi.fn() },
}));

const mocked = vi.mocked(api);

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
  mocked.getState.mockImplementation(async (week: string) =>
    makeState({ week_start: week, meals: [makeMeal({ id: 1, name: "Spaghetti" })] }),
  );
});

async function renderApp(path = "/") {
  window.history.replaceState(null, "", path);
  render(
    <QueryClientProvider client={createQueryClient({ retry: false })}>
      <App />
    </QueryClientProvider>,
  );
  // Wait for the first load, so assertions see the loaded app.
  await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
}

const selectedTab = () =>
  screen.getAllByRole("tab").find((tab) => tab.getAttribute("aria-selected") === "true");

describe("the tab in the URL", () => {
  it("opens on Meals by default", async () => {
    await renderApp();

    expect(selectedTab()).toHaveTextContent("Meals");
  });

  it("opens the tab named in the link", async () => {
    await renderApp("/?tab=grocery");

    expect(selectedTab()).toHaveTextContent("Grocery List");
  });

  it("ignores a tab it does not know", async () => {
    await renderApp("/?tab=settings");

    expect(selectedTab()).toHaveTextContent("Meals");
  });

  it("records the tab chosen, keeping the week", async () => {
    const user = userEvent.setup();
    await renderApp("/?week=2026-08-03");

    await user.click(screen.getByRole("tab", { name: "Weekly Plan" }));

    const params = new URLSearchParams(window.location.search);
    expect(params.get("tab")).toBe("plan");
    expect(params.get("week")).toBe("2026-08-03");
    expect(selectedTab()).toHaveTextContent("Weekly Plan");
  });
});

describe("loading", () => {
  it("shows the week from the link once loaded", async () => {
    await renderApp("/?week=2026-08-05");

    expect(mocked.getState).toHaveBeenCalledWith("2026-08-03");
    expect(screen.getByLabelText("Week starting")).toHaveValue("2026-08-03");
  });
});
