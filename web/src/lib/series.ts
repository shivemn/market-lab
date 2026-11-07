import type { MarketEvent } from "./market";

export interface Point {
  t: number; // microseconds since the start of the day
  price: number; // paise
}

/** The last trade price in each time bucket, oldest first. Used to draw the day's price line. */
export function priceSeries(events: readonly MarketEvent[], bucketUs: number): Point[] {
  const points: Point[] = [];
  let bucket = -1;
  for (const event of events) {
    if (event.type !== "Trade") continue;
    const index = Math.floor(event.sim_time / bucketUs);
    if (index === bucket) points[points.length - 1] = { t: event.sim_time, price: event.price };
    else {
      points.push({ t: event.sim_time, price: event.price });
      bucket = index;
    }
  }
  return points;
}

/** The biggest price change between two points no further apart than `windowUs`. */
export function biggestMove(points: readonly Point[], windowUs: number): { from: Point; to: Point } | null {
  let best: { from: Point; to: Point } | null = null;
  let size = 0;
  for (let j = 1; j < points.length; j++) {
    for (let i = j - 1; i >= 0 && points[j].t - points[i].t <= windowUs; i--) {
      const change = Math.abs(points[j].price - points[i].price);
      if (change > size) {
        size = change;
        best = { from: points[i], to: points[j] };
      }
    }
  }
  return best;
}

/** The time of the last event of each command. */
export function endTimes(events: readonly MarketEvent[], ends: readonly number[]): number[] {
  return ends.map((end) => events[end - 1].sim_time);
}

/** Index of the last command that finished at or before time `t`, or -1 if none had. */
export function lastEndAtOrBefore(times: readonly number[], t: number): number {
  let low = 0;
  let high = times.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (times[middle] <= t) {
      found = middle;
      low = middle + 1;
    } else high = middle - 1;
  }
  return found;
}

export interface TradePoint extends Point {
  quantity: number;
}

/** Every trade, oldest first: when, at what price, and how many shares. */
export function tradeSeries(events: readonly MarketEvent[]): TradePoint[] {
  const trades: TradePoint[] = [];
  for (const event of events) {
    if (event.type === "Trade") trades.push({ t: event.sim_time, price: event.price, quantity: event.quantity });
  }
  return trades;
}

/** Shares traded in each equal slice of the day. `slices` bars cover 0..durationUs. */
export function volumeSlices(trades: readonly TradePoint[], durationUs: number, slices: number): number[] {
  const bars = new Array<number>(slices).fill(0);
  const size = Math.max(durationUs, 1) / slices;
  for (const trade of trades) {
    const index = Math.min(slices - 1, Math.max(0, Math.floor(trade.t / size)));
    bars[index] += trade.quantity;
  }
  return bars;
}

/** The index of the first trade after time `t` (so trades before it are `[0, index)`). */
export function tradesUpTo(trades: readonly TradePoint[], t: number): number {
  let low = 0;
  let high = trades.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (trades[middle].t <= t) low = middle + 1;
    else high = middle;
  }
  return low;
}

/** The highest and lowest price among the first `count` trades, or null if there are none. */
export function extremes(trades: readonly TradePoint[], count: number): { high: TradePoint; low: TradePoint } | null {
  if (count <= 0) return null;
  let high = trades[0];
  let low = trades[0];
  for (let i = 1; i < count; i++) {
    if (trades[i].price > high.price) high = trades[i];
    if (trades[i].price < low.price) low = trades[i];
  }
  return { high, low };
}

/**
 * A price axis that fits the data: round-number lines in paise, a little room above and below, and never so
 * zoomed in that a one-tick wobble looks like a crash (at least 0.4% of the reference price tall).
 */
export function priceAxis(prices: readonly number[], reference: number): { low: number; high: number; ticks: number[] } {
  let low = Math.min(reference, ...prices);
  let high = Math.max(reference, ...prices);
  const minimumSpan = reference * 0.004;
  if (high - low < minimumSpan) {
    const middle = (high + low) / 2;
    low = middle - minimumSpan / 2;
    high = middle + minimumSpan / 2;
  }
  const pad = (high - low) * 0.12;
  low -= pad;
  high += pad;
  const rupeeSteps = [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
  const wanted = (high - low) / 100 / 5; // about five lines, in rupees
  const step = (rupeeSteps.find((candidate) => candidate >= wanted) ?? 1000) * 100;
  const ticks: number[] = [];
  for (let value = Math.ceil(low / step) * step; value <= high; value += step) ticks.push(value);
  return { low, high, ticks };
}

/**
 * An index drawn through the day: its level (hundredths of a point) after each trade in any of its companies.
 * Level = the sum of (latest price x factor). A company that has not traded yet counts at yesterday's close, so
 * the line starts from where the index opened. When many trades land in one bucket only the last is kept.
 */
export function indexSeries(
  events: Readonly<Record<string, readonly MarketEvent[]>>,
  factors: Readonly<Record<string, number>>,
  closes: Readonly<Record<string, number>>,
  bucketUs: number,
): Point[] {
  const trades: { symbol: string; t: number; price: number }[] = [];
  for (const [symbol, list] of Object.entries(events)) {
    if (!(symbol in factors)) continue;
    for (const event of list) if (event.type === "Trade") trades.push({ symbol, t: event.sim_time, price: event.price });
  }
  trades.sort((a, b) => a.t - b.t); // stable: trades at the same instant keep their order
  const price: Record<string, number> = { ...closes };
  let level = 0;
  for (const symbol of Object.keys(factors)) level += factors[symbol] * (price[symbol] ?? 0);
  const points: Point[] = [];
  let bucket = -1;
  for (const trade of trades) {
    level += factors[trade.symbol] * (trade.price - (price[trade.symbol] ?? 0));
    price[trade.symbol] = trade.price;
    const index = Math.floor(trade.t / bucketUs);
    const point = { t: trade.t, price: level };
    if (index === bucket) points[points.length - 1] = point;
    else {
      points.push(point);
      bucket = index;
    }
  }
  return points;
}

/** The highest and lowest level of an index line, rounded to whole hundredths (the line itself is a drawing in floats). */
export function lineRange(line: readonly Point[]): { high: number; low: number } | null {
  if (line.length === 0) return null;
  let high = line[0].price;
  let low = line[0].price;
  for (const p of line) {
    if (p.price > high) high = p.price;
    if (p.price < low) low = p.price;
  }
  return { high: Math.round(high), low: Math.round(low) };
}
