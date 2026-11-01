// What the opening auction did and why, worked out from the events alone. The exchange's own answer is the
// AuctionResult event; this file recomputes the answer from the orders (the same rules as src/marketlab/core/auction.py)
// and the tests check the two agree.

import type { MarketEvent } from "./market";

export interface Instrument {
  tick_size: number;
  reference_price: number;
  band_low: number;
  band_high: number;
}

export interface CurvePoint {
  price: number; // paise
  buy: number; // shares people would buy at this price (their limit is this price or higher, or no limit)
  sell: number; // shares people would sell at this price (their limit is this price or lower, or no limit)
  volume: number; // the most that could trade: the smaller of the two
}

export interface AuctionOrder {
  id: number;
  account: string;
  side: "BUY" | "SELL";
  quantity: number;
  limitPrice: number | null; // null means "at any price"
  filled: number;
  paid: number; // paise per share, the auction price, when anything was filled
  cancelledBefore: boolean;
  stays: boolean; // the unfilled part is still waiting in the queue after the auction
}

export interface AuctionReport {
  price: number | null; // what the exchange decided
  volume: number;
  openingPrice: number;
  unmatchedBuy: number;
  unmatchedSell: number;
  computedPrice: number | null; // what this file worked out; they must agree
  tiedPrices: number; // how many candidate prices allow the same largest volume
  curve: CurvePoint[];
  orders: AuctionOrder[];
}

export function auctionReport(events: readonly MarketEvent[], instrument: Instrument): AuctionReport | null {
  const resultAt = events.findIndex((e) => e.type === "AuctionResult");
  if (resultAt < 0) return null;
  const result = events[resultAt];
  if (result.type !== "AuctionResult") return null;

  const orders = new Map<number, AuctionOrder>();
  const tifs = new Map<number, string>();
  for (const event of events.slice(0, resultAt)) {
    if (event.type === "OrderAccepted") {
      orders.set(event.order_id, {
        id: event.order_id,
        account: event.account_id,
        side: event.side,
        quantity: event.quantity,
        limitPrice: event.limit_price,
        filled: 0,
        paid: 0,
        cancelledBefore: false,
        stays: false,
      });
      tifs.set(event.order_id, event.tif);
    } else if (event.type === "OrderCancelled") {
      const order = orders.get(event.order_id);
      if (order) order.cancelledBefore = true;
    } else if (event.type === "OrderModified") {
      const order = orders.get(event.order_id);
      if (order) {
        order.quantity = event.new_quantity;
        order.limitPrice = event.new_price;
      }
    }
  }

  // Trades of the auction itself come right after the result, before the market opens.
  for (const event of events.slice(resultAt + 1)) {
    if (event.type === "SessionChanged") break;
    if (event.type === "Trade") {
      for (const id of [event.buy_order_id, event.sell_order_id]) {
        const order = orders.get(id);
        if (order) {
          order.filled += event.quantity;
          order.paid = event.price;
        }
      }
    }
  }
  for (const order of orders.values()) {
    order.stays = !order.cancelledBefore && order.filled < order.quantity && order.limitPrice !== null && tifs.get(order.id) === "DAY";
  }

  const live = [...orders.values()].filter((o) => !o.cancelledBefore);
  const { curve, price: computedPrice, tied } = equilibrium(live, instrument);
  return {
    price: result.price,
    volume: result.volume,
    openingPrice: result.opening_price,
    unmatchedBuy: result.unmatched_buy,
    unmatchedSell: result.unmatched_sell,
    computedPrice,
    tiedPrices: tied,
    curve,
    orders: [...orders.values()],
  };
}

/** The same rules as the exchange: most shares, then least left over, then closest to yesterday's close, then lower. */
function equilibrium(
  live: readonly AuctionOrder[],
  instrument: Instrument,
): { curve: CurvePoint[]; price: number | null; tied: number } {
  const tick = instrument.tick_size;
  const candidates = new Set<number>([instrument.reference_price]);
  for (const order of live) {
    if (order.limitPrice === null) continue;
    for (const p of [order.limitPrice - tick, order.limitPrice, order.limitPrice + tick]) candidates.add(p);
  }
  const prices = [...candidates].filter((p) => p >= instrument.band_low && p <= instrument.band_high).sort((a, b) => a - b);

  const curve: CurvePoint[] = prices.map((price) => {
    let buy = 0;
    let sell = 0;
    for (const order of live) {
      if (order.side === "BUY" && (order.limitPrice === null || order.limitPrice >= price)) buy += order.quantity;
      if (order.side === "SELL" && (order.limitPrice === null || order.limitPrice <= price)) sell += order.quantity;
    }
    return { price, buy, sell, volume: Math.min(buy, sell) };
  });

  const most = Math.max(0, ...curve.map((c) => c.volume));
  if (most === 0) return { curve, price: null, tied: 0 };
  const best = curve.filter((c) => c.volume === most);
  const leftOver = (c: CurvePoint) => Math.abs(c.buy - c.sell);
  const lowest = Math.min(...best.map(leftOver));
  const tiedOnLeftOver = best.filter((c) => leftOver(c) === lowest);
  const nearest = Math.min(...tiedOnLeftOver.map((c) => Math.abs(c.price - instrument.reference_price)));
  const chosen = tiedOnLeftOver.filter((c) => Math.abs(c.price - instrument.reference_price) === nearest);
  return { curve, price: Math.min(...chosen.map((c) => c.price)), tied: best.length };
}
