import { describe, expect, it } from "vitest";
import { biggestMove, extremes, indexSeries, lastEndAtOrBefore, Point, priceAxis, tradesUpTo, TradePoint, volumeSlices } from "./series";

const s = (t: number, price: number): Point => ({ t: t * 1_000_000, price });

describe("biggestMove", () => {
  it("finds the largest change inside the window", () => {
    const points = [s(0, 100), s(5, 110), s(8, 90), s(30, 200), s(31, 200)];
    const move = biggestMove(points, 10_000_000);
    expect(move?.from.price).toBe(110);
    expect(move?.to.price).toBe(90);
  });
  it("ignores changes slower than the window", () => {
    expect(biggestMove([s(0, 100), s(60, 500)], 10_000_000)).toBeNull();
  });
  it("is null with fewer than two points", () => {
    expect(biggestMove([s(0, 1)], 10_000_000)).toBeNull();
    expect(biggestMove([], 10_000_000)).toBeNull();
  });
});

describe("lastEndAtOrBefore", () => {
  const times = [10, 20, 20, 35];
  it("finds the last command at or before a time", () => {
    expect(lastEndAtOrBefore(times, 5)).toBe(-1);
    expect(lastEndAtOrBefore(times, 10)).toBe(0);
    expect(lastEndAtOrBefore(times, 20)).toBe(2);
    expect(lastEndAtOrBefore(times, 34)).toBe(2);
    expect(lastEndAtOrBefore(times, 1000)).toBe(3);
    expect(lastEndAtOrBefore([], 5)).toBe(-1);
  });
});

const trade = (t: number, price: number, quantity = 1): TradePoint => ({ t: t * 1_000_000, price, quantity });

describe("volumeSlices", () => {
  it("adds up the shares traded in each slice of the day", () => {
    const trades = [trade(1, 100, 5), trade(2, 100, 7), trade(9, 100, 3), trade(10, 100, 4)];
    expect(volumeSlices(trades, 10_000_000, 2)).toEqual([12, 7]);
  });
  it("puts a trade at the very end into the last slice", () => {
    expect(volumeSlices([trade(10, 1, 9)], 10_000_000, 5)).toEqual([0, 0, 0, 0, 9]);
  });
});

describe("tradesUpTo and extremes", () => {
  const trades = [trade(1, 100), trade(2, 130), trade(3, 90), trade(4, 110)];
  it("counts the trades at or before a time", () => {
    expect(tradesUpTo(trades, 0)).toBe(0);
    expect(tradesUpTo(trades, 2_000_000)).toBe(2);
    expect(tradesUpTo(trades, 99_000_000)).toBe(4);
  });
  it("finds the highest and lowest of the first few trades", () => {
    expect(extremes(trades, 0)).toBeNull();
    const two = extremes(trades, 2);
    expect([two?.high.price, two?.low.price]).toEqual([130, 100]);
    const four = extremes(trades, 4);
    expect([four?.high.price, four?.low.price]).toEqual([130, 90]);
  });
});

describe("priceAxis", () => {
  it("always includes the reference price and every price", () => {
    const axis = priceAxis([249_000, 251_500], 250_000);
    expect(axis.low).toBeLessThan(249_000);
    expect(axis.high).toBeGreaterThan(251_500);
  });
  it("is not zoomed in too far when the price barely moves", () => {
    const axis = priceAxis([250_000, 250_005], 250_000);
    expect(axis.high - axis.low).toBeGreaterThanOrEqual(250_000 * 0.004);
  });
  it("puts lines on round rupee amounts", () => {
    const axis = priceAxis([248_100, 251_900], 250_000);
    expect(axis.ticks.length).toBeGreaterThanOrEqual(3);
    for (const tick of axis.ticks) expect(tick % 100).toBe(0);
  });
});

describe("indexSeries", () => {
  const trade = (_symbol: string, t: number, price: number) =>
    ({ type: "Trade", sim_time: t * 1_000_000, price, quantity: 1 }) as never;
  const factors = { A: 2, B: 1 }; // A counts twice as much per paise as B
  const closes = { A: 100, B: 300 }; // the index opens at 2*100 + 1*300 = 500

  it("moves by factor x the change in the company that just traded, the others holding their last price", () => {
    const events = { A: [trade("A", 1, 110), trade("A", 5, 120)], B: [trade("B", 3, 290)] };
    const line = indexSeries(events, factors, closes, 1);
    expect(line.map((p) => [p.t / 1_000_000, p.price])).toEqual([
      [1, 520], // A 110: 220 + 300
      [3, 510], // B 290: 220 + 290
      [5, 530], // A 120: 240 + 290
    ]);
  });
  it("keeps only the last point in each bucket", () => {
    const events = { A: [trade("A", 1, 110), trade("A", 1.5, 130)], B: [] };
    const line = indexSeries(events, factors, closes, 10_000_000);
    expect(line).toHaveLength(1);
    expect(line[0].price).toBe(560);
  });
  it("is empty before anything has traded, and ignores companies outside the index", () => {
    expect(indexSeries({ A: [], B: [] }, factors, closes, 1)).toEqual([]);
    expect(indexSeries({ Z: [trade("Z", 1, 5)] }, factors, closes, 1)).toEqual([]);
  });
});
