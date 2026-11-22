import { useCallback, useEffect, useState } from "react";

/** Instrument light, Instrument dark, and Classic (the look before the redesign). */
export const THEMES = [
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
  { id: "classic", label: "Classic" },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

const KEY = "marketlab-theme";

/** The saved choice, or else whatever the computer prefers. Old names from earlier versions map to the nearest look. */
export function savedTheme(): ThemeId {
  try {
    const value = window.localStorage.getItem(KEY);
    if (value === "light" || value === "dark" || value === "classic") return value;
    if (value === "terminal") return "dark";
    if (value !== null) return "light";
  } catch {
    // storage can be blocked; follow the computer's setting
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: ThemeId): void {
  document.documentElement.dataset.theme = theme;
}

export function useTheme(): [ThemeId, (theme: ThemeId) => void] {
  const [theme, setTheme] = useState<ThemeId>(savedTheme);
  useEffect(() => applyTheme(theme), [theme]);
  const choose = useCallback((next: ThemeId) => {
    setTheme(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // not saved, still applied for this visit
    }
  }, []);
  return [theme, choose];
}
