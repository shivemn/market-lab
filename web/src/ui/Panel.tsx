import type { ReactNode } from "react";

interface Props {
  id: string;
  title: ReactNode;
  /** Shown at the right of the title line: a count, a time, a help bubble. */
  meta?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** A panel with a one-line title. The Instrument look draws the title as a small monospace label. */
export function Panel({ id, title, meta, className, children }: Props) {
  return (
    <section className={`panel${className ? ` ${className}` : ""}`} aria-labelledby={id}>
      <div className="ptitle">
        <h2 id={id}>{title}</h2>
        {meta}
      </div>
      {children}
    </section>
  );
}
