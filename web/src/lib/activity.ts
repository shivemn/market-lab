import { rupees } from "./format";
import type { MarketEvent, MarketState, Side } from "./market";

type Trade = Extract<MarketEvent, { type: "Trade" }>;

/** Orders placed by the person get ids above this, so they can be told apart from the simulated traders'. */
const USER_ORDER_BASE = 1_000_000_000;
const isMine = (orderId: number) => orderId > USER_ORDER_BASE;

export interface ActivityItem {
  key: number; // the sequence number of the first event the line is about
  at: number; // microseconds into the day
  kind: "placed" | "filled" | "cancelled" | "expired";
  text: string;
}

const shares = (n: number) => `${n} ${n === 1 ? "share" : "shares"}`;

/** "Bought 5 shares at ₹2,511.83 on average", from the trades one command caused. */
function fillText(trades: readonly Trade[], me: string): string {
  const parts: string[] = [];
  for (const [verb, mine] of [
    ["Bought", trades.filter((t) => t.buy_account_id === me)],
    ["Sold", trades.filter((t) => t.sell_account_id === me)],
  ] as const) {
    if (mine.length === 0) continue;
    const quantity = mine.reduce((sum, t) => sum + t.quantity, 0);
    const value = mine.reduce((sum, t) => sum + t.quantity * t.price, 0);
    const average = Math.round(value / quantity);
    const low = Math.min(...mine.map((t) => t.price));
    const high = Math.max(...mine.map((t) => t.price));
    parts.push(`${verb} ${shares(quantity)} at ${rupees(average)}${low === high ? "" : " on average"}`);
  }
  return `${parts.join(" and ")}.`;
}

/** Everything that happened to the person's own orders, one line per thing, newest first. */
export function myActivity(events: readonly MarketEvent[], ends: readonly number[], me: string): ActivityItem[] {
  const items: ActivityItem[] = [];
  let from = 0;
  for (const end of ends) {
    const group = events.slice(from, end);
    from = end;
    const trades = group.filter((e): e is Trade => e.type === "Trade" && (e.buy_account_id === me || e.sell_account_id === me));
    for (const e of group) {
      if (e.type === "OrderAccepted" && e.account_id === me) {
        const side = e.side === "BUY" ? "Buy" : "Sell";
        const price = e.limit_price === null ? "at the best price" : `at ${rupees(e.limit_price)}`;
        items.push({ key: e.seq, at: e.sim_time, kind: "placed", text: `${side} ${shares(e.quantity)} ${price} placed.` });
      } else if (e.type === "OrderCancelled" && isMine(e.order_id)) {
        const text =
          e.reason === "USER"
            ? `You cancelled an order (${shares(e.quantity)} had not traded).`
            : `${shares(e.quantity)} of your order found no match and was dropped.`;
        items.push({ key: e.seq, at: e.sim_time, kind: "cancelled", text });
      } else if (e.type === "OrderExpired" && isMine(e.order_id)) {
        items.push({ key: e.seq, at: e.sim_time, kind: "expired", text: `${shares(e.quantity)} of your order expired at the close.` });
      }
    }
    if (trades.length > 0) {
      items.push({ key: trades[0].seq, at: trades[trades.length - 1].sim_time, kind: "filled", text: fillText(trades, me) });
    }
  }
  return items.reverse();
}

export interface TapeRow {
  key: number;
  at: number;
  price: number;
  quantity: number;
  dir: "up" | "down" | "same";
  mine: boolean;
}

/** The latest trades, newest first, each marked up or down against the trade before it. */
export function recentTrades(events: readonly MarketEvent[], limit: number, me: string): TapeRow[] {
  const found: Trade[] = [];
  for (let i = events.length - 1; i >= 0 && found.length < limit + 1; i--) {
    const e = events[i];
    if (e.type === "Trade") found.push(e);
  }
  return found.slice(0, limit).map((t, i) => {
    const before = found[i + 1];
    return {
      key: t.seq,
      at: t.sim_time,
      price: t.price,
      quantity: t.quantity,
      dir: before === undefined || before.price === t.price ? "same" : t.price > before.price ? "up" : "down",
      mine: t.buy_account_id === me || t.sell_account_id === me,
    };
  });
}

export interface LadderRow {
  side: "ask" | "bid";
  price: number;
  quantity: number;
  mine: number; // shares of the person's own waiting orders at this price
  share: number; // 0 to 1: this level's size compared with the biggest level shown
}

export interface Ladder {
  asks: LadderRow[]; // highest price first, so the best ask sits next to the spread
  bids: LadderRow[]; // best bid first
  spread: number | null;
}

/** The queue as a price ladder: a few levels each side, with the person's own orders marked. */
export function buildLadder(
  state: MarketState,
  levels: number,
  mine: readonly { side: Side; limit_price: number | null; remaining: number }[],
): Ladder {
  const own = (side: Side, price: number) =>
    mine.filter((o) => o.side === side && o.limit_price === price).reduce((sum, o) => sum + o.remaining, 0);
  const asks = state.depth("SELL", levels);
  const bids = state.depth("BUY", levels);
  const biggest = Math.max(1, ...asks.map((l) => l.quantity), ...bids.map((l) => l.quantity));
  const row = (side: "ask" | "bid", level: { price: number; quantity: number }): LadderRow => ({
    side,
    price: level.price,
    quantity: level.quantity,
    mine: own(side === "ask" ? "SELL" : "BUY", level.price),
    share: level.quantity / biggest,
  });
  const bestAsk = asks[0]?.price;
  const bestBid = bids[0]?.price;
  return {
    asks: asks.map((l) => row("ask", l)).reverse(),
    bids: bids.map((l) => row("bid", l)),
    spread: bestAsk !== undefined && bestBid !== undefined ? bestAsk - bestBid : null,
  };
}
