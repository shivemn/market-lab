import { describe, expect, it } from "vitest";
import type { MarketEvent } from "./market";
import { addSample, equityExtremes, myFillTimes, worthAt, type EquityPoint } from "./equity";

const trade = (t: number, buyer: string, seller: string): MarketEvent => ({
  type: "Trade", seq: t, sim_time: t, trade_id: t, symbol: "X", price: 100, quantity: 1,
  buy_order_id: 1, sell_order_id: 2, buy_account_id: buyer, sell_account_id: seller, aggressor_side: null,
});

describe("addSample", () => {
  it("keeps the latest worth as the last point, exactly", () => {
    let s: EquityPoint[] = [];
    for (const [t, w] of [[0, 10_000_000], [5, 10_001_234], [9, 9_998_765]]) s = addSample(s, t, w);
    expect(s.at(-1)).toEqual({ t: 9, worth: 9_998_765 });
    expect(s).toHaveLength(3);
  });
  it("replaces a second report for the same moment", () => {
    const s = addSample(addSample([{ t: 0, worth: 100 }], 4, 120), 4, 117);
    expect(s).toEqual([{ t: 0, worth: 100 }, { t: 4, worth: 117 }]);
  });
  it("returns the same list when nothing changed", () => {
    const s = [{ t: 4, worth: 120 }];
    expect(addSample(s, 4, 120)).toBe(s);
  });
  it("starts again when a report comes from an earlier moment (a new day)", () => {
    expect(addSample([{ t: 10, worth: 5 }], 0, 7)).toEqual([{ t: 0, worth: 7 }]);
  });
});

describe("equityExtremes and worthAt", () => {
  const s = [{ t: 0, worth: 100 }, { t: 10, worth: 90 }, { t: 20, worth: 130 }, { t: 30, worth: 120 }];
  it("finds the low and the high", () => {
    expect(equityExtremes(s)).toEqual({ low: { t: 10, worth: 90 }, high: { t: 20, worth: 130 } });
    expect(equityExtremes([])).toBeNull();
  });
  it("reads the worth in force at a moment", () => {
    expect(worthAt(s, 15)).toBe(90);
    expect(worthAt(s, 20)).toBe(130);
    expect(worthAt(s, 99)).toBe(120);
    expect(worthAt(s, -5)).toBe(100);
    expect(worthAt([], 3)).toBeNull();
  });
});

describe("myFillTimes", () => {
  it("lists only this person's trades, oldest first, across companies", () => {
    const events = { A: [trade(30, "me", "mm"), trade(10, "x", "y")], B: [trade(20, "mm", "me")] };
    expect(myFillTimes(events, "me")).toEqual([20, 30]);
    expect(myFillTimes(events, "")).toEqual([]);
  });
});
