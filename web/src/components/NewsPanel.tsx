import { clock, percentSigned } from "../lib/format";
import type { NewsView, WorldSnapshot } from "../lib/world";

const TONE = { good: "Good news", bad: "Bad news", unclear: "Unclear" } as const;

/** Who an item is about, in words. */
export function newsTarget(item: NewsView, snapshot: WorldSnapshot): string {
  if (item.scope === "market") return "Whole market";
  if (item.scope === "sector") return snapshot.sectors.find((s) => s.key === item.target)?.label.split(":")[0] ?? item.target;
  return item.target;
}

/** The latest headline on one fixed-height line. A new item flashes once so it is noticed. */
export function NewsTicker({ snapshot }: { snapshot: WorldSnapshot }) {
  const latest = snapshot.news[snapshot.news.length - 1];
  return (
    <div className="ticker" role="status" aria-live="polite">
      <span className="ticker-label">News</span>
      {latest === undefined ? (
        <span className="muted">Nothing has come out yet. Headlines appear here the moment they are published.</span>
      ) : (
        <span key={latest.id} className={`ticker-item ${latest.tone}`}>
          <b>{clock(latest.at, snapshot.open_at, snapshot.close_at)}</b> {newsTarget(latest, snapshot)}: {latest.headline}
          <span className="tone"> ({TONE[latest.tone]})</span>
        </span>
      )}
    </div>
  );
}

/** Every headline so far, newest first. How far each one moved the price is added when the day is over. */
export function NewsPanel({ snapshot }: { snapshot: WorldSnapshot }) {
  const items = [...snapshot.news].reverse();
  if (items.length === 0) {
    return <p className="muted small">No news yet. A few items come out during the day, and prices react to them.</p>;
  }
  return (
    <div className="newslist">
      <p className="muted small">
        Prices react to news: mostly within seconds, and the rest over about two minutes. An unclear headline could go either
        way. How far each item moved its price is shown once the day is over.
      </p>
      <ol>
        {items.map((n) => (
          <li key={n.id} className={n.tone}>
            <span className="t">{clock(n.at, snapshot.open_at, snapshot.close_at)}</span>
            <span className="who">{newsTarget(n, snapshot)}</span>
            <span className="what">{n.headline}</span>
            <span className="how">
              {n.impact_bp === null ? TONE[n.tone] : `Moved the price ${percentSigned(n.impact_bp, 10_000)}`}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
