import type { Portfolio } from "./practice";

/** Worth in paise: money (free and set aside) plus every share valued at `price`. */
export const worth = (p: Portfolio, price: number): number => p.cash + p.reserved + (p.shares + p.locked) * price;

export interface DayResult {
  startWorth: number;
  endWorth: number;
  result: number; // endWorth - startWorth
  charges: number; // paid during this day
  priceMoves: number; // result before charges
}

/**
 * How the day went. Shares held at the start are valued at the previous close, shares held now at the last price, so a
 * move in shares carried over from an earlier day counts too. `chargesToday` is what was paid in charges during the day.
 */
export function dayResult(start: Portfolio, now: Portfolio, previousClose: number, lastPrice: number | null, chargesToday: number): DayResult {
  const price = lastPrice ?? previousClose;
  const startWorth = worth(start, previousClose);
  const endWorth = worth(now, price);
  const result = endWorth - startWorth;
  return { startWorth, endWorth, result, charges: chargesToday, priceMoves: result + chargesToday };
}
