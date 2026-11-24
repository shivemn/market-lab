import { clock, money } from "../lib/format";
import type { TapeItem } from "../lib/tape";

const MARK = { up: "▲", down: "▼", same: "=", first: "·" } as const;
const WORD = { up: "up", down: "down", same: "unchanged", first: "first trade" } as const;

/** The latest trades across all twelve companies, newest at the left. Your own trades are marked. */
export function TapeStrip({ items, openAt, closeAt }: { items: readonly TapeItem[]; openAt: number; closeAt: number }) {
  return (
    <section className="tape-strip" aria-label="Latest trades in all companies">
      <span className="tape-label">Tape</span>
      {items.length === 0 ? (
        <span className="tape-empty muted">No trades yet. They appear here, newest first, once the market opens.</span>
      ) : (
        <ol className="tape-list">
          {items.map((t) => (
            <li key={t.key} className={`tape-item${t.mine ? " mine" : ""}`}>
              <span className="tape-t">{clock(t.at, openAt, closeAt)}</span> <b>{t.symbol}</b> {t.quantity} @ {money(t.price)}{" "}
              <span className={`tape-move ${t.move}`} aria-label={WORD[t.move]}>
                {MARK[t.move]}
              </span>
              {t.mine && <span className="you-tag">you</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
