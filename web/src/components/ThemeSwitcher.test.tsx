import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { useTheme } from "@/hooks/useTheme";
import { THEME_STORAGE_KEY } from "@/lib/theme";
import { fakeDevice } from "@/test/device";

function Harness() {
  const { theme, setTheme } = useTheme();
  return <ThemeSwitcher theme={theme} onChange={setTheme} />;
}

const isDarkNow = () => document.documentElement.classList.contains("dark");

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("starts dark, with Dark pressed", () => {
  render(<Harness />);
  expect(isDarkNow()).toBe(true);
  expect(screen.getByRole("button", { name: "Dark theme" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("switches to light and remembers it", async () => {
  const user = userEvent.setup();
  render(<Harness />);

  await user.click(screen.getByRole("button", { name: "Light theme" }));

  expect(isDarkNow()).toBe(false);
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  expect(screen.getByRole("button", { name: "Light theme" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "Dark theme" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

it("follows the device while set to match it, and stops when it is not", async () => {
  const device = fakeDevice(false);
  const user = userEvent.setup();
  render(<Harness />);

  await user.click(screen.getByRole("button", { name: "Match device theme" }));
  expect(isDarkNow()).toBe(false);

  device.switchTo(true);
  expect(isDarkNow()).toBe(true);

  await user.click(screen.getByRole("button", { name: "Light theme" }));
  expect(device.listening()).toBe(0);
  device.switchTo(true);
  expect(isDarkNow()).toBe(false);
});
