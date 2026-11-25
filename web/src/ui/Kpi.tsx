import type { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  /** "up" or "down" colours the value; "big" makes it the screen's one large figure. */
  tone?: "up" | "down" | "flat";
  big?: boolean;
  className?: string;
}

/** One figure in a row of figures: a small label, the value, and a line of context under it. */
export function Kpi({ label, value, note, tone, big, className }: Props) {
  return (
    <div className={`stat${className ? ` ${className}` : ""}`}>
      <span className="k">{label}</span>
      <span className={`v${big ? " big" : ""}${tone ? ` ${tone}` : ""}`}>{value}</span>
      {note !== undefined && <span className="sub">{note}</span>}
    </div>
  );
}
