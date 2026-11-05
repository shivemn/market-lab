import type { ReactNode } from "react";

/** A small "?" that opens a short explanation, so panels do not have to open with a paragraph. */
export function Help({ children, label = "What is this?" }: { children: ReactNode; label?: string }) {
  return (
    <details className="help">
      <summary aria-label={label}>?</summary>
      <div className="help-body">{children}</div>
    </details>
  );
}
