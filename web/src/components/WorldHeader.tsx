import { percentSigned, points, pointsSigned } from "../lib/format";
import type { IndexKind, WorldSnapshot } from "../lib/world";
import { INDEX_TEXT, indexTitle, sessionAt } from "../lib/worldview";
import { ThemeSwitch } from "./ThemeSwitch";

const SESSION_WORDS = { CLOSED: "Closed", PRE_OPEN: "Before the open", OPEN: "Open" } as const;

/** The top line: the market's index, which way it has moved today, and whether the market is open. */
export function WorldHeader({ snapshot, kind }: { snapshot: WorldSnapshot | null; kind: IndexKind }) {
  const view = snapshot?.indices[kind] ?? null;
  const session = snapshot === null ? "PRE_OPEN" : sessionAt(snapshot.now, snapshot.open_at, snapshot.close_at);
  const dir = view === null || view.change === 0 ? "flat" : view.change > 0 ? "up" : "down";
  return (
    <header className="top">
      <div className="brand">
        <div className="brand-name">Market Lab</div>
        <div className="muted small">Pretend money, made-up companies</div>
      </div>
      <div className="quote">
        <span className="symbol">{snapshot === null ? "Shifty 12" : indexTitle(snapshot, kind)}</span>
        <span className="price" aria-live="off">
          {view === null ? "…" : points(view.level)}
        </span>
        {view !== null && (
          <span className={`change ${dir}`}>
            {dir === "flat" ? "unchanged" : `${dir === "up" ? "▲" : "▼"} ${pointsSigned(view.change)} (${percentSigned(view.change, view.open)})`}
          </span>
        )}
        {view !== null && (
          <span className="muted small">
            since yesterday's close of {points(view.open)} · {INDEX_TEXT[kind].name.toLowerCase()}
          </span>
        )}
      </div>
      <div className="top-right">
        <span className={`chip chip-${session.toLowerCase()}`}>{SESSION_WORDS[session]}</span>
        <ThemeSwitch />
      </div>
    </header>
  );
}
