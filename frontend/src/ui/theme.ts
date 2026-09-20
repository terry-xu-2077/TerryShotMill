import { useSyncExternalStore } from "react";

export type ColorTheme = "light" | "dark";
export const themeStorageKey = "shotmill.color-theme";
const listeners = new Set<() => void>();

export function readTheme(): ColorTheme {
  try {
    const saved = localStorage.getItem(themeStorageKey);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* The theme remains usable when browser storage is unavailable. */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

let theme = readTheme();

function applyTheme(next: ColorTheme) {
  theme = next;
  document.documentElement.dataset.tcMode = next;
  document.documentElement.classList.add("tc-theme");
  document.documentElement.dataset.mode = next;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", next === "dark" ? "#151618" : "#f3f5f7");
  listeners.forEach((listener) => listener());
}

export function initializeTheme() {
  applyTheme(readTheme());
}

export function setColorTheme(next: ColorTheme) {
  try { localStorage.setItem(themeStorageKey, next); } catch { /* Keep the current session usable. */ }
  applyTheme(next);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const synchronize = (event: StorageEvent) => {
    if (event.key === themeStorageKey || event.key === null) applyTheme(readTheme());
  };
  window.addEventListener("storage", synchronize);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", synchronize);
  };
}

export function useColorTheme() {
  return useSyncExternalStore(subscribe, () => theme);
}
