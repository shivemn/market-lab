import { useCallback, useEffect, useState } from "react";

export const THEMES = [
  { id: "desk", label: "Desk" },
  { id: "terminal", label: "Terminal" },
  { id: "notebook", label: "Notebook" },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

const KEY = "marketlab-theme";

export function savedTheme(): ThemeId {
  try {
    const value = window.localStorage.getItem(KEY);
    if (THEMES.some((t) => t.id === value)) return value as ThemeId;
  } catch {
    // storage can be blocked; the default look is fine
  }
  return "desk";
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
