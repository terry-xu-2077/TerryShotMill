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
  applyPalette(next);
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
    if (event.key === themeStorageKey || event.key?.startsWith("shotmill.palette.") || event.key === null) applyTheme(readTheme());
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

export const paletteFields = [
  ["base", "底色", "--tc-base"], ["accent", "强调色", "--tc-accent"],
  ["effect", "特效色", "--tc-effect"], ["text", "普通文字", "--tc-text-main"],
  ["textBright", "高亮文字", "--tc-text-bright"],
] as const;
export type ThemePalette = Record<typeof paletteFields[number][0], string>;
export const paletteDefaults: Record<ColorTheme, ThemePalette> = {
  light: { base: "#68717b", accent: "#4154df", effect: "#477eda", text: "#25282e", textBright: "#111318" },
  dark: { base: "#151618", accent: "#687cfa", effect: "#7b9fef", text: "#dce0e5", textBright: "#f7fafc" },
};
export function readPalette(mode: ColorTheme): ThemePalette {
  const result = { ...paletteDefaults[mode] };
  try {
    const saved = JSON.parse(localStorage.getItem(`shotmill.palette.${mode}`) || "{}");
    for (const [key] of paletteFields) if (/^#[0-9a-f]{6}$/i.test(saved?.[key])) result[key] = saved[key];
  } catch { /* Invalid storage falls back to defaults. */ }
  return result;
}
function applyPalette(mode: ColorTheme) {
  const palette = readPalette(mode);
  for (const [key, , token] of paletteFields) document.documentElement.style.setProperty(token, palette[key]);
}
export function savePalette(mode: ColorTheme, palette: ThemePalette) {
  if (!paletteFields.every(([key]) => /^#[0-9a-f]{6}$/i.test(palette[key]))) return;
  try { localStorage.setItem(`shotmill.palette.${mode}`, JSON.stringify(palette)); } catch { /* Preview still works without storage. */ }
  if (mode === theme) for (const [key, , token] of paletteFields) document.documentElement.style.setProperty(token, palette[key]);
  window.dispatchEvent(new Event("shotmill-palette-change"));
}
