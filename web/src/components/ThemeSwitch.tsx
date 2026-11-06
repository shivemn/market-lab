import { THEMES, useTheme } from "../lib/theme";

const ICON = {
  light: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66 1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14-1.41-1.41M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z",
  dark: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
} as const;

/** Light or dark. The first visit follows the computer's setting. */
export function ThemeSwitch() {
  const [theme, choose] = useTheme();
  return (
    <div className="themes" role="group" aria-label="Colour theme">
      {THEMES.map((t) => (
        <button key={t.id} type="button" aria-pressed={theme === t.id} className={theme === t.id ? "on" : ""} onClick={() => choose(t.id)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d={ICON[t.id]} />
          </svg>
          {t.label}
        </button>
      ))}
    </div>
  );
}
