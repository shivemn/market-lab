import type { MarketEvent } from "./market";

/**
 * A tiny line of one company's price through the day so far, for its tile on the board: the last trade in each of
 * `buckets` equal slices of the day, drawn in a 100 by 20 box. Yesterday's close is the dashed level (`refY`).
 */
export function sparkLine(events: readonly MarketEvent[], closeAt: number, reference: number, now: number, buckets = 60): { d: string; refY: number } {
  const last = new Array<number | null>(buckets).fill(null);
  for (const e of events) {
    if (e.type !== "Trade") continue;
    const b = Math.min(buckets - 1, Math.floor((e.sim_time / closeAt) * buckets));
    last[b] = e.price;
  }
  const upto = Math.min(buckets - 1, Math.floor((Math.min(now, closeAt) / closeAt) * buckets));
  const prices: number[] = [];
  let price = reference;
  for (let b = 0; b <= upto; b++) {
    price = last[b] ?? price;
    prices.push(price);
  }
  const lo = Math.min(reference, ...prices);
  const hi = Math.max(reference, ...prices);
  const span = hi - lo || 1;
  const y = (p: number) => 18 - ((p - lo) / span) * 16;
  const x = (b: number) => (b / (buckets - 1)) * 100;
  const d = prices.length < 2 ? "" : prices.map((p, b) => `${b ? "L" : "M"}${x(b).toFixed(1)} ${y(p).toFixed(1)}`).join("");
  return { d, refY: Number(y(reference).toFixed(1)) };
}
