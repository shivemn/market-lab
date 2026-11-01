import { describe, expect, it } from "vitest";
import day from "../fixtures/day.json";
import { auctionReport, Instrument } from "./auction";
import type { MarketEvent } from "./market";

const cases = (day as unknown as { cases: { name: string; events: MarketEvent[] }[] }).cases;
// The instrument both fixture days use: reference ₹2,500.00, tick ₹0.05, band 10 percent.
const demo: Instrument = { tick_size: 5, reference_price: 250_000, band_low: 225_000, band_high: 275_000 };

describe("auctionReport on the hand-worked day", () => {
  const report = auctionReport(cases[0].events, demo);
  it("finds 130 shares at ₹2,500.00, the same as the exchange", () => {
    expect(report).not.toBeNull();
    expect(report?.price).toBe(250_000);
    expect(report?.volume).toBe(130);
    expect(report?.computedPrice).toBe(250_000);
    expect(report?.unmatchedSell).toBe(70);
  });
  it("shows the buyer and seller totals that were worked out by hand", () => {
    const at = (price: number) => report?.curve.find((c) => c.price === price);
    expect([at(249_950)?.buy, at(249_950)?.sell]).toEqual([130, 80]);
    expect([at(250_000)?.buy, at(250_000)?.sell]).toEqual([130, 200]);
    expect([at(250_100)?.buy, at(250_100)?.sell]).toEqual([130, 200]);
    expect([at(250_105)?.buy, at(250_105)?.sell]).toEqual([30, 200]);
  });
  it("says who got what, including the cancelled order and the order still waiting", () => {
    const byId = new Map(report?.orders.map((o) => [o.id, o]));
    expect(byId.get(1)).toMatchObject({ filled: 100, paid: 250_000, limitPrice: 250_100 });
    expect(byId.get(5)).toMatchObject({ filled: 30, limitPrice: null });
    expect(byId.get(3)).toMatchObject({ filled: 80 });
    expect(byId.get(4)).toMatchObject({ filled: 50, stays: true });
    expect(byId.get(2)?.cancelledBefore).toBe(true);
  });
  it("sees that two prices tie for the most shares and the closing price breaks the tie", () => {
    expect(report?.tiedPrices).toBeGreaterThan(1);
  });
});

describe("auctionReport agrees with the exchange on forty different mornings", () => {
  const mornings = (day as unknown as {
    auctions: { seed: number; events: MarketEvent[]; price: number | null; volume: number }[];
  }).auctions;
  it("has the mornings", () => expect(mornings.length).toBe(40));
  it("finds the same price and volume as the exchange every time", () => {
    let traded = 0;
    for (const morning of mornings) {
      const report = auctionReport(morning.events, demo);
      expect(report?.computedPrice, `seed ${morning.seed}`).toBe(morning.price);
      if (morning.price !== null) {
        traded += 1;
        expect(report?.curve.find((c) => c.price === morning.price)?.volume, `seed ${morning.seed}`).toBe(morning.volume);
      }
    }
    expect(traded).toBeGreaterThan(10); // most mornings must really trade, or this check proves little
  });
});

describe("auctionReport agrees with the exchange on a simulated day", () => {
  const sim = cases[1];
  it("computes the same price and volume as the AuctionResult event", () => {
    const report = auctionReport(sim.events, demo);
    expect(report).not.toBeNull();
    expect(report?.computedPrice).toBe(report?.price);
    if (report && report.price !== null) {
      expect(report.curve.find((c) => c.price === report.price)?.volume).toBe(report.volume);
    }
  });
  it("returns null before any auction happened", () => {
    expect(auctionReport(sim.events.slice(0, 3), demo)).toBeNull();
  });
});
