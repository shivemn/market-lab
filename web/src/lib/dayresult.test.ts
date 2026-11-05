import { describe, expect, it } from "vitest";
import { dayResult } from "./dayresult";
import type { Portfolio } from "./practice";

const folio = (cash: number, shares: number, reserved = 0, locked = 0): Portfolio => ({ cash, reserved, shares, locked, open_orders: [] });

describe("how the day went", () => {
  it("splits a loss into price moves and charges, with the numbers from a real practice day", () => {
    // bought 10 at ₹2,500.10 paying ₹53.29 in charges; last price ₹2,490.20; the day opened with ₹1,00,000
    const r = dayResult(folio(10_000_000, 0), folio(7_494_571, 10), 250_000, 249_020, 5_329);
    expect(r.endWorth).toBe(9_984_771);
    expect(r.result).toBe(-15_229);
    expect(r.charges).toBe(5_329);
    expect(r.priceMoves).toBe(-9_900);
  });
  it("counts the move in shares carried over from an earlier day", () => {
    // 10 shares held at the start, valued at the close of 2,500; the day ends at 2,490 with no trades
    const r = dayResult(folio(7_500_000, 10), folio(7_500_000, 10), 250_000, 249_000, 0);
    expect(r.startWorth).toBe(10_000_000);
    expect(r.result).toBe(-10_000);
    expect(r.priceMoves).toBe(-10_000);
  });
  it("uses the previous close when nothing has traded, so an untouched day is a zero", () => {
    const r = dayResult(folio(10_000_000, 0), folio(10_000_000, 0), 250_000, null, 0);
    expect(r.result).toBe(0);
  });
  it("treats money set aside and locked shares as still yours", () => {
    const r = dayResult(folio(10_000_000, 0), folio(9_000_000, 0, 1_000_000), 250_000, 250_000, 0);
    expect(r.result).toBe(0);
  });
});
