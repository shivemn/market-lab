import type { ReactNode } from "react";

/** A change that says which way it went in words or signs, coloured as a second cue, never as the only one. */
export function Delta({ dir, children }: { dir: "up" | "down" | "flat"; children: ReactNode }) {
  return <span className={`change ${dir}`}>{children}</span>;
}
