import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeSwitch } from "./ThemeSwitch";
import { initializeTheme, readTheme, setColorTheme, themeStorageKey } from "./theme";

afterEach(() => {
  vi.restoreAllMocks();
  setColorTheme("light");
  localStorage.removeItem(themeStorageKey);
});

describe("color theme", () => {
  it("restores a saved theme and applies the shared library mode", () => {
    localStorage.setItem(themeStorageKey, "dark");
    initializeTheme();
    expect(document.documentElement.dataset.tcMode).toBe("dark");
    expect(readTheme()).toBe("dark");
  });

  it("switches and remembers the user's choice", async () => {
    const user = userEvent.setup();
    setColorTheme("light");
    render(<ThemeSwitch />);
    await user.click(screen.getByRole("button", { name: "暗色" }));
    expect(localStorage.getItem(themeStorageKey)).toBe("dark");
    expect(document.documentElement.dataset.tcMode).toBe("dark");
    expect(screen.getByRole("button", { name: "暗色" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "亮色" }));
    expect(document.documentElement.dataset.tcMode).toBe("light");
  });

  it("uses the system preference for a missing or invalid saved value", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    localStorage.setItem(themeStorageKey, "invalid");
    expect(readTheme()).toBe("dark");
    vi.unstubAllGlobals();
  });

  it("still switches when persistence is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => setColorTheme("dark")).not.toThrow();
    expect(document.documentElement.dataset.tcMode).toBe("dark");
  });

  it("synchronizes controls after another window changes the preference", () => {
    setColorTheme("light");
    render(<ThemeSwitch />);
    act(() => {
      localStorage.setItem(themeStorageKey, "dark");
      window.dispatchEvent(new StorageEvent("storage", { key: themeStorageKey, newValue: "dark" }));
    });
    expect(screen.getByRole("button", { name: "暗色" })).toHaveAttribute("aria-pressed", "true");
  });
});


describe("custom palettes", () => {
  it("keeps light and dark independent and restores them on mode changes", async () => {
    const { savePalette, readPalette, paletteDefaults, setColorTheme, initializeTheme } = await import("./theme");
    savePalette("light", { ...paletteDefaults.light, accent: "#123456" });
    savePalette("dark", { ...paletteDefaults.dark, accent: "#abcdef" });
    setColorTheme("light");
    expect(document.documentElement.style.getPropertyValue("--tc-accent")).toBe("#123456");
    setColorTheme("dark"); initializeTheme();
    expect(document.documentElement.style.getPropertyValue("--tc-accent")).toBe("#abcdef");
    savePalette("dark", { ...paletteDefaults.dark });
    expect(readPalette("light").accent).toBe("#123456");
    expect(readPalette("dark")).toEqual(paletteDefaults.dark);
  });
  it("ignores corrupt saved colors", async () => {
    const { readPalette, paletteDefaults } = await import("./theme");
    localStorage.setItem("shotmill.palette.light", JSON.stringify({ base: "invalid" }));
    expect(readPalette("light")).toEqual(paletteDefaults.light);
  });
});
