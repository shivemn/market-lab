import type { MarketEvent } from "./market";

export interface TapeItem {
  key: string;
  at: number; // microseconds into the day
  symbol: string;
  price: number; // paise
  quantity: number;
  /** Against the trade before it in the same company: "up", "down" or "same"; "first" for the day's first trade. */
  move: "up" | "down" | "same" | "first";
  mine: boolean;
}

/**
 * The latest trades across every company, newest first. Each company's list is read from its end, so this costs the
 * same however long the day has run.
 */
export function latestTrades(events: Readonly<Record<string, readonly MarketEvent[]>>, owner: string, limit = 30): TapeItem[] {
  const all: TapeItem[] = [];
  for (const [symbol, list] of Object.entries(events)) {
    const found: Extract<MarketEvent, { type: "Trade" }>[] = [];
    for (let i = list.length - 1; i >= 0 && found.length <= limit; i--) {
      const e = list[i];
      if (e.type === "Trade") found.push(e);
    }
    for (let k = 0; k < Math.min(found.length, limit); k++) {
      const e = found[k];
      const before = found[k + 1];
      const move = before === undefined ? "first" : e.price > before.price ? "up" : e.price < before.price ? "down" : "same";
      all.push({
        key: `${symbol}:${e.seq}`,
        at: e.sim_time,
        symbol,
        price: e.price,
        quantity: e.quantity,
        move,
        mine: owner !== "" && (e.buy_account_id === owner || e.sell_account_id === owner),
      });
    }
  }
  return all.sort((a, b) => b.at - a.at || (a.key < b.key ? 1 : -1)).slice(0, limit);
}
