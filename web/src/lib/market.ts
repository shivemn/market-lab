// The market rebuilt from events alone. This is a TypeScript copy of src/marketlab/projection.py; the tests load
// web/src/fixtures/day.json (written by the Python code) and check both give exactly the same picture.

export type Side = "BUY" | "SELL";
export type Session = "CLOSED" | "PRE_OPEN" | "OPEN";

interface Base {
  seq: number;
  sim_time: number; // microseconds since the start of the day
}

export type MarketEvent =
  | (Base & { type: "SessionChanged"; session: Session })
  | (Base & {
      type: "OrderAccepted";
      order_id: number;
      account_id: string;
      symbol: string;
      side: Side;
      order_type: "LIMIT" | "MARKET";
      quantity: number;
      limit_price: number | null;
      tif: "DAY" | "IOC";
    })
  | (Base & { type: "OrderRejected"; order_id: number; reason: string })
  | (Base & {
      type: "OrderCancelled";
      order_id: number;
      quantity: number;
      reason: "USER" | "IOC_REMAINDER" | "MARKET_REMAINDER";
    })
  | (Base & {
      type: "OrderModified";
      order_id: number;
      new_quantity: number;
      new_price: number;
      remaining: number;
      lost_priority: boolean;
    })
  | (Base & { type: "OrderExpired"; order_id: number; quantity: number })
  | (Base & {
      type: "Trade";
      trade_id: number;
      symbol: string;
      price: number;
      quantity: number;
      buy_order_id: number;
      sell_order_id: number;
      buy_account_id: string;
      sell_account_id: string;
      aggressor_side: Side | null;
    })
  | (Base & {
      type: "AuctionResult";
      price: number | null;
      volume: number;
      opening_price: number;
      unmatched_buy: number;
      unmatched_sell: number;
    });

export interface RestingOrder {
  id: number;
  account: string;
  side: Side;
  price: number;
  remaining: number;
  priority: number; // smaller means earlier in the queue
}

export interface QueuedOrder {
  id: number;
  account: string;
  remaining: number;
}

export interface Level {
  price: number;
  quantity: number;
  orders: QueuedOrder[]; // front of the queue first
}

export class MarketState {
  session: Session = "CLOSED";
  orders = new Map<number, RestingOrder>();
  pendingMarket = new Map<number, number>();
  openingPrice: number | null = null;
  lastPrice: number | null = null;
  lastTrade: { price: number; quantity: number; aggressor: Side | null } | null = null;
  high: number | null = null;
  low: number | null = null;
  trades = 0;
  volume = 0;
  eventsApplied = 0;
  private priority = 0;

  apply(event: MarketEvent): void {
    this.eventsApplied += 1;
    switch (event.type) {
      case "SessionChanged":
        this.session = event.session;
        break;
      case "OrderAccepted":
        if (event.order_type === "LIMIT") {
          this.priority += 1;
          this.orders.set(event.order_id, {
            id: event.order_id,
            account: event.account_id,
            side: event.side,
            price: event.limit_price as number,
            remaining: event.quantity,
            priority: this.priority,
          });
        } else if (this.session === "PRE_OPEN") {
          this.pendingMarket.set(event.order_id, event.quantity);
        }
        break;
      case "OrderModified": {
        const order = this.orders.get(event.order_id);
        if (order) {
          order.price = event.new_price;
          order.remaining = event.remaining;
          if (event.lost_priority) {
            this.priority += 1;
            order.priority = this.priority;
          }
        }
        break;
      }
      case "Trade":
        this.trade(event);
        break;
      case "OrderCancelled":
      case "OrderExpired":
        this.orders.delete(event.order_id);
        this.pendingMarket.delete(event.order_id);
        break;
      case "AuctionResult":
        this.openingPrice = event.opening_price;
        break;
      case "OrderRejected":
        break;
    }
  }

  private trade(event: Extract<MarketEvent, { type: "Trade" }>): void {
    this.trades += 1;
    this.volume += event.quantity;
    this.lastPrice = event.price;
    this.lastTrade = { price: event.price, quantity: event.quantity, aggressor: event.aggressor_side };
    this.high = this.high === null ? event.price : Math.max(this.high, event.price);
    this.low = this.low === null ? event.price : Math.min(this.low, event.price);
    for (const id of [event.buy_order_id, event.sell_order_id]) {
      const order = this.orders.get(id);
      if (order) {
        order.remaining -= event.quantity;
        if (order.remaining <= 0) this.orders.delete(id);
        continue;
      }
      const waiting = this.pendingMarket.get(id);
      if (waiting !== undefined) {
        const left = waiting - event.quantity;
        if (left <= 0) this.pendingMarket.delete(id);
        else this.pendingMarket.set(id, left);
      }
    }
  }

  /** Price levels on one side, best price first. */
  depth(side: Side, levels?: number): Level[] {
    const byPrice = new Map<number, RestingOrder[]>();
    for (const order of this.orders.values()) {
      if (order.side !== side) continue;
      const list = byPrice.get(order.price);
      if (list) list.push(order);
      else byPrice.set(order.price, [order]);
    }
    const prices = [...byPrice.keys()].sort((a, b) => (side === "BUY" ? b - a : a - b));
    const views = prices.map((price) => {
      const queue = (byPrice.get(price) as RestingOrder[]).sort((a, b) => a.priority - b.priority);
      return {
        price,
        quantity: queue.reduce((sum, order) => sum + order.remaining, 0),
        orders: queue.map((o) => ({ id: o.id, account: o.account, remaining: o.remaining })),
      };
    });
    return levels === undefined ? views : views.slice(0, levels);
  }

  bestBid(): number | null {
    return this.depth("BUY", 1)[0]?.price ?? null;
  }

  bestAsk(): number | null {
    return this.depth("SELL", 1)[0]?.price ?? null;
  }
}

/** The market after the first `count` events. */
export function fold(events: readonly MarketEvent[], count: number = events.length): MarketState {
  const state = new MarketState();
  const stop = Math.min(count, events.length);
  for (let i = 0; i < stop; i++) state.apply(events[i]);
  return state;
}

/** The market as plain data, in the same shape as the server's /state endpoint (used by the tests). */
export function stateJson(state: MarketState) {
  return {
    at: state.eventsApplied,
    session: state.session,
    opening_price: state.openingPrice,
    last_price: state.lastPrice,
    high: state.high,
    low: state.low,
    trades: state.trades,
    volume: state.volume,
    best_bid: state.bestBid(),
    best_ask: state.bestAsk(),
    pending_market: [...state.pendingMarket.entries()].sort((a, b) => a[0] - b[0]),
    bids: state.depth("BUY"),
    asks: state.depth("SELL"),
  };
}
