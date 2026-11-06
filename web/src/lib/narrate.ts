import { rupees } from "./format";
import type { MarketEvent } from "./market";

export interface LogLine {
  id: number; // stable: the position of the command in the day, so a line keeps its identity as newer ones arrive
  at: number; // microseconds into the day
  text: string;
}

/** The plain-language sentence for each command that finished before `count` events. Newest first. */
export function narrateLog(
  events: readonly MarketEvent[],
  ends: readonly number[],
  count: number,
  limit = 4,
  me?: string,
  symbol?: string,
): LogLine[] {
  const lines: LogLine[] = [];
  let upper = ends.findIndex((end) => end > count);
  if (upper === -1) upper = ends.length;
  for (let i = upper - 1; i >= 0 && lines.length < limit; i--) {
    const group = events.slice(i === 0 ? 0 : ends[i - 1], ends[i]);
    if (group.length > 0) lines.push({ id: i, at: group[0].sim_time, text: sentence(group, me, symbol) });
  }
  return lines;
}

/** Just the sentences, newest first. */
export function narrate(
  events: readonly MarketEvent[],
  ends: readonly number[],
  count: number,
  limit = 4,
  me?: string,
  symbol?: string,
): string[] {
  return narrateLog(events, ends, count, limit, me, symbol).map((line) => line.text);
}

/** "MM2" is a market maker, "NT4" a casual trader, "VT1" a value trader. Anything else is just "A trader". */
export function who(account: string, me?: string): string {
  if (me !== undefined && account === me) return "You";
  if (account.startsWith("MM")) return "A market maker";
  if (account.startsWith("NT")) return "A casual trader";
  if (account.startsWith("VT")) return "A value trader";
  return "A trader";
}

/** "13 UDHAAR shares", or "13 shares" when no company is given. */
export function shares(n: number, symbol?: string): string {
  return `${n} ${symbol ? `${symbol} ` : ""}${n === 1 ? "share" : "shares"}`;
}

/** The latest trade in one line: "13 UDHAAR shares changed hands at ₹1,642.35 (a buyer paid the seller's price)". */
export function lastTradeText(
  trade: { price: number; quantity: number; aggressor: "BUY" | "SELL" | null },
  symbol?: string,
): string {
  const how =
    trade.aggressor === "BUY" ? " (a buyer paid the seller's price)" : trade.aggressor === "SELL" ? " (a seller took the buyer's price)" : "";
  return `${shares(trade.quantity, symbol)} changed hands at ${rupees(trade.price)}${how}`;
}

function sentence(group: readonly MarketEvent[], me?: string, symbol?: string): string {
  const first = group[0];
  const trades = group.filter((e): e is Extract<MarketEvent, { type: "Trade" }> => e.type === "Trade");
  const mine = me === undefined ? [] : trades.filter((t) => t.buy_account_id === me || t.sell_account_id === me);
  if (mine.length > 0) return myTradeSentence(mine, me as string, symbol);
  switch (first.type) {
    case "SessionChanged":
      if (first.session === "PRE_OPEN") return "The market opened for orders. Nothing trades until the opening auction.";
      if (first.session === "OPEN") return "The market is open for trading.";
      return "The market closed. Orders still waiting have expired.";
    case "AuctionResult":
      if (first.price === null) {
        return `The opening auction found no price where buyers and sellers agree, so the day opens at ${rupees(first.opening_price)}.`;
      }
      return `The opening auction matched ${shares(first.volume, symbol)} at ${rupees(first.price)}. Everyone who traded got that same price.`;
    case "OrderAccepted": {
      if (trades.length > 0) return tradeSentence(trades, symbol);
      const side = first.side === "BUY" ? "buy" : "sell";
      if (first.limit_price === null) {
        return `${who(first.account_id, me)} placed an order to ${side} ${shares(first.quantity, symbol)} at any price. It waits for the opening auction.`;
      }
      return `${who(first.account_id, me)} joined the queue to ${side} ${shares(first.quantity, symbol)} at ${rupees(first.limit_price)}.`;
    }
    case "OrderRejected":
      return `An order was turned down by the exchange (${first.reason.toLowerCase().replace(/_/g, " ")}).`;
    case "OrderCancelled":
      return `A waiting order for ${shares(first.quantity, symbol)} was cancelled.`;
    case "OrderModified":
      return `An order was changed to ${shares(first.new_quantity, symbol)} at ${rupees(first.new_price)}${
        first.lost_priority ? " and moved to the back of its queue" : " and kept its place in the queue"
      }.`;
    case "Trade":
      return tradeSentence(trades, symbol);
    case "OrderExpired":
      return "An order expired.";
  }
}

function tradeSentence(trades: readonly Extract<MarketEvent, { type: "Trade" }>[], symbol?: string): string {
  const total = trades.reduce((sum, t) => sum + t.quantity, 0);
  const prices = trades.map((t) => t.price);
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const where = low === high ? `at ${rupees(low)}` : `between ${rupees(low)} and ${rupees(high)}`;
  const who =
    trades[0].aggressor_side === "BUY"
      ? "A buyer paid the seller's price."
      : trades[0].aggressor_side === "SELL"
        ? "A seller accepted the buyer's price."
        : "";
  return `${shares(total, symbol)} changed hands ${where}. ${who}`.trim();
}

/** "Your order traded: you bought 12 shares at ₹2,500.05." Says what happened to the person, not to the market. */
function myTradeSentence(trades: readonly Extract<MarketEvent, { type: "Trade" }>[], me: string, symbol?: string): string {
  const bought = trades.filter((t) => t.buy_account_id === me);
  const sold = trades.filter((t) => t.sell_account_id === me);
  const part = (list: typeof trades, verb: string): string => {
    const total = list.reduce((sum, t) => sum + t.quantity, 0);
    const value = list.reduce((sum, t) => sum + t.quantity * t.price, 0);
    const prices = list.map((t) => t.price);
    const low = Math.min(...prices);
    const high = Math.max(...prices);
    const where = low === high ? `at ${rupees(low)}` : `at ${rupees(Math.round(value / total))} on average (from ${rupees(low)} to ${rupees(high)})`;
    return `you ${verb} ${shares(total, symbol)} ${where}`;
  };
  const parts = [bought.length > 0 ? part(bought, "bought") : "", sold.length > 0 ? part(sold, "sold") : ""].filter(Boolean);
  return `Your order traded: ${parts.join(" and ")}.`;
}
