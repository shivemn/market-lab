import { clock, percentSigned, points, pointsSigned } from "../lib/format";
import type { IndexKind, WorldSnapshot } from "../lib/world";
import { INDEX_TEXT, indexTitle, sessionAt } from "../lib/worldview";
import { Delta, StatusBar } from "../ui";

/** The top line: the market's index, which way it has moved today, whether the market is open, and the market clock. */
export function WorldHeader({ snapshot, kind }: { snapshot: WorldSnapshot | null; kind: IndexKind }) {
  const view = snapshot?.indices[kind] ?? null;
  const session = snapshot === null ? "PRE_OPEN" : sessionAt(snapshot.now, snapshot.open_at, snapshot.close_at);
  const dir = view === null || view.change === 0 ? "flat" : view.change > 0 ? "up" : "down";
  const time = snapshot === null ? null : clock(snapshot.now, snapshot.open_at, snapshot.close_at);
  return (
    <StatusBar session={session} clock={time}>
      <span className="symbol">{snapshot === null ? "Shifty 12" : indexTitle(snapshot, kind)}</span>
      <span className="price" aria-live="off">
        {view === null ? "…" : points(view.level)}
      </span>
      {view !== null && (
        <Delta dir={dir}>
          {dir === "flat" ? "unchanged" : `${dir === "up" ? "▲" : "▼"} ${pointsSigned(view.change)} (${percentSigned(view.change, view.open)})`}
        </Delta>
      )}
      {view !== null && (
        <span className="muted small">
          since yesterday's close of {points(view.open)} · {INDEX_TEXT[kind].name.toLowerCase()}
        </span>
      )}
    </StatusBar>
  );
}
