import { useRef } from "react";
import { percentSigned, rupees, signed } from "../lib/format";
import type { WorldSnapshot } from "../lib/world";

interface Props {
  snapshot: WorldSnapshot;
  selected: string;
  onSelect: (symbol: string) => void;
  /** A tiny line of each company's price so far (see lib/spark.ts), drawn along the foot of its tile. */
  lines?: Record<string, { d: string; refY: number }>;
}

/** All twelve companies, grouped by sector. Pick one to trade it. */
export function MarketBoard({ snapshot, selected, onSelect, lines }: Props) {
  // each price flashes once, green or red, when it changes (the key on the number restarts the animation)
  const seen = useRef<Record<string, { price: number; dir: "up" | "down" | "" }>>({});
  return (
    <section className="board" aria-label="Companies">
      {snapshot.sectors.map((sector) => {
        const view = snapshot.indices.sectors[sector.key];
        const dir = view.change === 0 ? "flat" : view.change > 0 ? "up" : "down";
        return (
          <div className="sector" key={sector.key}>
            <div className="sector-head">
              <h3>{sector.label}</h3>
              <span className={`chg ${dir}`}>{percentSigned(view.change, view.open)}</span>
            </div>
            {snapshot.companies
              .filter((c) => c.sector === sector.key)
              .map((c) => {
                const price = snapshot.prices[c.symbol];
                const previous = c.instrument.reference_price;
                const diff = price - previous;
                const move = diff === 0 ? "flat" : diff > 0 ? "up" : "down";
                const hold = snapshot.portfolio.holdings[c.symbol];
                const held = hold.shares + hold.locked;
                const today = snapshot.positions[c.symbol]?.today ?? 0;
                const was = seen.current[c.symbol];
                if (was === undefined) seen.current[c.symbol] = { price, dir: "" };
                else if (was.price !== price) seen.current[c.symbol] = { price, dir: price > was.price ? "up" : "down" };
                const flash = seen.current[c.symbol].dir;
                const line = lines?.[c.symbol];
                return (
                  <button
                    key={c.symbol}
                    type="button"
                    className={`tile ${c.symbol === selected ? "sel" : ""}`}
                    aria-pressed={c.symbol === selected}
                    onClick={() => onSelect(c.symbol)}
                    aria-label={`${c.name}, ${c.symbol}, ${rupees(price)}, ${diff === 0 ? "unchanged" : diff > 0 ? "up" : "down"} today${held > 0 ? `. You hold ${held} shares.` : ""}`}
                  >
                    <span className="t1">
                      <b>{c.symbol}</b>
                      <span key={price} className={`num${flash ? ` flash-${flash}` : ""}`}>
                        {rupees(price)}
                      </span>
                    </span>
                    <span className="t2">
                      <span className="nm">{c.name}</span>
                      <span className={`chg ${move}`}>
                        {move === "flat" ? "–" : `${diff > 0 ? "▲" : "▼"} ${percentSigned(diff, previous).replace(/^[+−]/, "")}`}
                      </span>
                    </span>
                    <span className="t3">{held > 0 ? `You hold ${held} · ${signed(today)} today` : ""}</span>
                    {line && line.d && (
                      <svg className={`spark ${move}`} viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">
                        <line x1="0" x2="100" y1={line.refY} y2={line.refY} />
                        <path d={line.d} />
                      </svg>
                    )}
                  </button>
                );
              })}
          </div>
        );
      })}
    </section>
  );
}
