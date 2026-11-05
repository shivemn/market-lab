import { describe, expect, it } from "vitest";
import { buildLadder, myActivity, recentTrades } from "./activity";
import { fold, MarketEvent } from "./market";

const ME = "you";
let seq = 0;
const base = (sim_time: number) => ({ seq: ++seq, sim_time });
const accepted = (id: number, account: string, side: "BUY" | "SELL", quantity: number, limit: number | null, t: number): MarketEvent => ({
  ...base(t),
  type: "OrderAccepted",
  order_id: id,
  account_id: account,
  symbol: "D",
  side,
  order_type: limit === null ? "MARKET" : "LIMIT",
  quantity,
  limit_price: limit,
  tif: "DAY",
});
const trade = (price: number, quantity: number, buyer: string, seller: string, t: number): MarketEvent => ({
  ...base(t),
  type: "Trade",
  trade_id: seq,
  symbol: "D",
  price,
  quantity,
  buy_order_id: 1_000_000_001,
  sell_order_id: 7,
  buy_account_id: buyer,
  sell_account_id: seller,
  aggressor_side: "BUY",
});

describe("my activity", () => {
  it("lists my order and what it did, newest first, and leaves other traders out", () => {
    seq = 0;
    const events = [
      accepted(1, "NT1", "SELL", 3, 250_100, 1_000_000),
      accepted(1_000_000_001, ME, "BUY", 5, null, 2_000_000),
      trade(250_100, 3, ME, "NT1", 2_000_001),
      trade(250_200, 2, ME, "MM1", 2_000_002),
      accepted(2, "NT2", "BUY", 1, 250_000, 3_000_000),
    ];
    const items = myActivity(events, [1, 4, 5], ME);
    expect(items.map((i) => i.kind)).toEqual(["filled", "placed"]);
    expect(items[0].text).toBe("Bought 5 shares at ₹2,501.40 on average.");
    expect(items[1].text).toBe("Buy 5 shares at the best price placed.");
  });
  it("says what happened when I cancel, and when the day ends on a waiting order", () => {
    seq = 0;
    const events: MarketEvent[] = [
      { ...base(5), type: "OrderCancelled", order_id: 1_000_000_001, quantity: 4, reason: "USER" },
      { ...base(9), type: "OrderExpired", order_id: 1_000_000_002, quantity: 1 },
      { ...base(9), type: "OrderCancelled", order_id: 3, quantity: 4, reason: "USER" },
    ];
    const items = myActivity(events, [1, 2, 3], ME);
    expect(items.map((i) => i.text)).toEqual([
      "1 share of your order expired at the close.",
      "You cancelled an order (4 shares had not traded).",
    ]);
  });
});

describe("the trade tape", () => {
  it("marks each trade up or down against the one before and flags mine", () => {
    seq = 0;
    const events = [trade(100, 1, "A", "B", 1), trade(105, 2, ME, "B", 2), trade(101, 1, "A", "B", 3)];
    const rows = recentTrades(events, 2, ME);
    expect(rows.map((r) => [r.price, r.dir, r.mine])).toEqual([
      [101, "down", false],
      [105, "up", true],
    ]);
  });
});

describe("the price ladder", () => {
  it("puts the best ask next to the best bid, sizes bars against the biggest level, and marks my orders", () => {
    seq = 0;
    const state = fold(
      [
        { ...base(0), type: "SessionChanged", session: "OPEN" } as MarketEvent,
        accepted(1, "NT1", "SELL", 4, 250_100, 1),
        accepted(2, "NT2", "SELL", 8, 250_200, 2),
        accepted(3, "NT3", "BUY", 2, 250_000, 3),
        accepted(1_000_000_001, ME, "BUY", 6, 249_900, 4),
      ],
      5,
    );
    const ladder = buildLadder(state, 5, [{ side: "BUY", limit_price: 249_900, remaining: 6 }]);
    expect(ladder.asks.map((r) => r.price)).toEqual([250_200, 250_100]);
    expect(ladder.bids.map((r) => r.price)).toEqual([250_000, 249_900]);
    expect(ladder.spread).toBe(100);
    expect(ladder.asks[0].share).toBe(1);
    expect(ladder.bids[1].mine).toBe(6);
    expect(ladder.bids[0].mine).toBe(0);
  });
});
