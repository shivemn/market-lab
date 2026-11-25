import { describe, expect, it } from "vitest";
import type { MarketEvent } from "./market";
import { sparkLine } from "./spark";

const t = (at: number, price: number): MarketEvent => ({
  type: "Trade", seq: at, sim_time: at, trade_id: at, symbol: "X", price, quantity: 1,
  buy_order_id: 1, sell_order_id: 2, buy_account_id: "a", sell_account_id: "b", aggressor_side: null,
});

describe("sparkLine", () => {
  it("draws up to now only, holding the last price through quiet slices", () => {
    const { d } = sparkLine([t(10, 110), t(55, 90)], 100, 100, 60, 10);
    expect(d.split("L")).toHaveLength(7); // slices 0..6
    expect(d.startsWith("M0.0")).toBe(true);
  });
  it("puts yesterday's close inside the box", () => {
    const { refY } = sparkLine([t(10, 120)], 100, 100, 50, 10);
    expect(refY).toBeGreaterThanOrEqual(2);
    expect(refY).toBeLessThanOrEqual(18);
  });
  it("is empty before there are two slices to join", () => {
    expect(sparkLine([], 100, 100, 0, 10).d).toBe("");
  });
});
