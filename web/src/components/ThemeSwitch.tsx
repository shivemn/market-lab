import { THEMES, useTheme } from "../lib/theme";

export function ThemeSwitch() {
  const [theme, choose] = useTheme();
  return (
    <div className="themes" role="group" aria-label="Look of the page">
      {THEMES.map((t) => (
        <button key={t.id} type="button" aria-pressed={theme === t.id} className={theme === t.id ? "on" : ""} onClick={() => choose(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
