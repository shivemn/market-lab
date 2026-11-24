import type { MarketEvent } from "./market";

/** The account's worth (paise) at a moment of the day (microseconds). */
export interface EquityPoint {
  t: number;
  worth: number;
}

/**
 * Add the worth the server reported at a moment. A second report for the same moment replaces the first (an order sent
 * while the day is paused can change the worth by its charges), and a report from an earlier moment starts again,
 * because a new day has begun. The last point is always exactly the latest worth the server sent.
 */
export function addSample(series: readonly EquityPoint[], t: number, worth: number): EquityPoint[] {
  const last = series[series.length - 1];
  if (last === undefined || t < last.t) return [{ t, worth }];
  if (t === last.t) return last.worth === worth ? (series as EquityPoint[]) : [...series.slice(0, -1), { t, worth }];
  return [...series, { t, worth }];
}

/** The lowest and highest worth so far, and the moments they happened. */
export function equityExtremes(series: readonly EquityPoint[]): { low: EquityPoint; high: EquityPoint } | null {
  if (series.length === 0) return null;
  let low = series[0];
  let high = series[0];
  for (const p of series) {
    if (p.worth < low.worth) low = p;
    if (p.worth > high.worth) high = p;
  }
  return { low, high };
}

/** The moments at which one of this person's orders traded, across every company, oldest first. */
export function myFillTimes(events: Readonly<Record<string, readonly MarketEvent[]>>, owner: string): number[] {
  const times: number[] = [];
  if (owner === "") return times;
  for (const list of Object.values(events)) {
    for (const e of list) {
      if (e.type === "Trade" && (e.buy_account_id === owner || e.sell_account_id === owner)) times.push(e.sim_time);
    }
  }
  return times.sort((a, b) => a - b);
}

/** The worth at a moment: the last sample at or before it (the first sample if the moment is earlier still). */
export function worthAt(series: readonly EquityPoint[], t: number): number | null {
  if (series.length === 0) return null;
  let lo = 0;
  let hi = series.length - 1;
  if (t < series[0].t) return series[0].worth;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (series[mid].t <= t) lo = mid;
    else hi = mid - 1;
  }
  return series[lo].worth;
}
