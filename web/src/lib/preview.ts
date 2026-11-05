import { rupees } from "./format";
import type { MarketState, Side } from "./market";

function shares(n: number): string {
  return `${n} ${n === 1 ? "share" : "shares"}`;
}

/**
 * What an order would do if it were sent right now, in plain words. It only looks at the queue on screen. The server
 * has the last word (and adds the charges), so this never promises a price.
 *
 * `limit` is in paise, or null for "at the best price available".
 */
export function previewOrder(state: MarketState, side: Side, quantity: number, limit: number | null): string {
  if (!Number.isInteger(quantity) || quantity <= 0) return "Enter how many shares you want.";
  if (state.session === "CLOSED") return "The market is closed, so no orders can be placed.";
  const verb = side === "BUY" ? "buy" : "sell";
  const other = side === "BUY" ? "SELL" : "BUY";
  if (state.session === "PRE_OPEN") {
    return `The market has not opened yet. Your order waits for the opening auction, where everyone who trades gets the same price.`;
  }

  // Walk the other side of the queue, best price first, taking what this order could trade with right now.
  let left = quantity;
  let value = 0;
  for (const level of state.depth(other)) {
    if (limit !== null && (side === "BUY" ? level.price > limit : level.price < limit)) break;
    const take = Math.min(left, level.quantity);
    value += take * level.price;
    left -= take;
    if (left === 0) break;
  }
  const filled = quantity - left;
  const average = filled > 0 ? rupees(Math.round(value / filled)) : "";

  if (limit === null) {
    if (filled === 0) return `Nobody is ${side === "BUY" ? "selling" : "buying"} right now, so this order would not trade.`;
    if (left > 0) {
      return `Only ${shares(filled)} ${side === "BUY" ? "are for sale" : "are wanted"}. You would ${verb} ${filled} at about ${average} each and the rest would be cancelled.`;
    }
    return `You would ${verb} all ${shares(quantity)} right away at about ${average} each, taking the best prices in the queue first.`;
  }

  if (filled > 0 && left === 0) {
    return `This would trade right away: you ${verb} ${shares(quantity)} at about ${average} each, because ${
      side === "BUY" ? "sellers are asking" : "buyers are offering"
    } as good as your price or better.`;
  }
  if (filled > 0) {
    return `Part would trade right away: ${shares(filled)} at about ${average} each. The other ${left} would join the queue at ${rupees(limit)}.`;
  }
  const ahead = state.depth(side).find((level) => level.price === limit)?.quantity ?? 0;
  const place =
    ahead === 0
      ? `You would be first in line at ${rupees(limit)}.`
      : `${shares(ahead)} already waiting at ${rupees(limit)} would trade before yours.`;
  return `Nothing trades yet. Your order would join the queue. ${place}`;
}
