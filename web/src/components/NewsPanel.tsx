import { clock, percentSigned } from "../lib/format";
import type { NewsView, WorldSnapshot } from "../lib/world";

/** Who an item is about, in words. */
export function newsTarget(item: NewsView, snapshot: WorldSnapshot): string {
  if (item.scope === "market") return "Whole market";
  if (item.scope === "sector") return snapshot.sectors.find((s) => s.key === item.target)?.label.split(":")[0] ?? item.target;
  return item.target;
}

/** What an item did, once the day is over: "+1.8%", "No visible effect", or nothing while the day is running. */
export function newsOutcome(impactBp: number | null): string {
  if (impactBp === null) return "";
  return impactBp === 0 ? "No visible effect" : `Moved the price ${percentSigned(impactBp, 10_000)}`;
}

export const headlineOf = (item: NewsView): string =>
  item.silent ? `No news: ${item.target} moved all the same` : item.headline;

/** The latest headline on one fixed-height line. A new item flashes once so it is noticed. */
export function NewsTicker({ snapshot }: { snapshot: WorldSnapshot }) {
  const latest = [...snapshot.news].reverse().find((n) => !n.silent);
  return (
    <div className="ticker" role="status" aria-live="polite">
      <span className="ticker-label">News</span>
      {latest === undefined ? (
        <span className="muted">Nothing has come out yet. Headlines appear here the moment they are published.</span>
      ) : (
        <span key={latest.id} className="ticker-item">
          <b>{clock(latest.at, snapshot.open_at, snapshot.close_at)}</b> {newsTarget(latest, snapshot)}: {latest.headline}
        </span>
      )}
    </div>
  );
}

/** Every headline so far, newest first. What each one did is added when the day is over. */
export function NewsPanel({ snapshot }: { snapshot: WorldSnapshot }) {
  const items = [...snapshot.news].reverse();
  if (items.length === 0) {
    return <p className="muted small">No news yet. A few items come out during the day. Some move prices and some do not.</p>;
  }
  return (
    <div className="newslist">
      <p className="muted small">
        Not every headline matters. Some big ones do nothing, some small ones move a price, and prices sometimes move with no
        news at all. What each one did is shown once the day is over.
      </p>
      <ol>
        {items.map((n) => (
          <li key={n.id} className={n.silent ? "silent" : ""}>
            <span className="t">{clock(n.at, snapshot.open_at, snapshot.close_at)}</span>
            <span className="who">{n.silent ? n.target : newsTarget(n, snapshot)}</span>
            <span className="what">{headlineOf(n)}</span>
            <span className="how">{newsOutcome(n.impact_bp)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
