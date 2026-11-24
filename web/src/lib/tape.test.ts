import { describe, expect, it } from "vitest";
import type { MarketEvent } from "./market";
import { latestTrades } from "./tape";

let seq = 0;
const trade = (symbol: string, t: number, price: number, buyer = "a", seller = "b"): MarketEvent => ({
  type: "Trade", seq: ++seq, sim_time: t, trade_id: seq, symbol, price, quantity: 3,
  buy_order_id: 1, sell_order_id: 2, buy_account_id: buyer, sell_account_id: seller, aggressor_side: "BUY",
});
const other = (t: number): MarketEvent => ({ type: "OrderCancelled", seq: ++seq, sim_time: t, order_id: 1, quantity: 1, reason: "USER" } as MarketEvent);

describe("latestTrades", () => {
  it("merges companies newest first and marks the direction against the same company's previous trade", () => {
    const events = {
      A: [trade("A", 1, 100), other(2), trade("A", 5, 105), trade("A", 9, 105)],
      B: [trade("B", 3, 50), trade("B", 7, 49, "me", "mm")],
    };
    const items = latestTrades(events, "me");
    expect(items.map((i) => `${i.symbol}@${i.at}:${i.move}`)).toEqual(["A@9:same", "B@7:down", "A@5:up", "B@3:first", "A@1:first"]);
    expect(items.find((i) => i.symbol === "B" && i.at === 7)?.mine).toBe(true);
    expect(items.filter((i) => i.mine)).toHaveLength(1);
  });
  it("keeps only the latest few, and knows the oldest one shown is not the day's first", () => {
    const list = Array.from({ length: 10 }, (_, k) => trade("A", k, 100 + k));
    const items = latestTrades({ A: list }, "", 3);
    expect(items.map((i) => i.at)).toEqual([9, 8, 7]);
    expect(items.every((i) => i.move === "up")).toBe(true);
  });
  it("is empty before anything trades", () => {
    expect(latestTrades({ A: [other(1)] }, "me")).toEqual([]);
  });
});
