import { describe, expect, it } from "vitest";
import day from "../fixtures/day.json";
import { narrate, who } from "./narrate";
import type { MarketEvent } from "./market";

const scripted = (day as unknown as { cases: { events: MarketEvent[]; ends: number[] }[] }).cases[0];

describe("narrate", () => {
  it("describes the opening auction in plain words", () => {
    const openEnd = scripted.ends[7]; // pre-open, six orders/cancels, then the opening step
    const lines = narrate(scripted.events, scripted.ends, openEnd, 1);
    expect(lines).toEqual(["The opening auction matched 130 shares at ₹2,500.00. Everyone who traded got that same price."]);
  });

  it("returns the newest first and respects the limit", () => {
    const lines = narrate(scripted.events, scripted.ends, scripted.events.length, 3);
    expect(lines).toHaveLength(3);
    expect(lines[0]).toContain("expired");
  });

  it("explains a trade by who reached across", () => {
    const upto = scripted.ends[13]; // after the immediate-or-cancel sell
    const [line] = narrate(scripted.events, scripted.ends, upto, 1);
    expect(line).toBe("20 shares changed hands at ₹2,499.50. A seller accepted the buyer's price.");
  });

  it("names traders by what they do, and says 1 share, not 1 shares", () => {
    const lines = narrate(scripted.events, scripted.ends, scripted.events.length, 30).join("\n");
    expect(lines).not.toMatch(/\b1 shares\b/);
    expect(lines).not.toMatch(/\b[A-Z]{2}\d+ (joined|placed)/);
  });

  it("says nothing before anything has happened", () => {
    expect(narrate(scripted.events, scripted.ends, 0)).toEqual([]);
  });

  it("only looks at finished commands at or before the position", () => {
    const lines = narrate(scripted.events, scripted.ends, scripted.ends[1], 5);
    expect(lines).toHaveLength(2);
  });
});

describe("who", () => {
  it("turns account ids into plain names", () => {
    expect(who("MM2")).toBe("A market maker");
    expect(who("NT17")).toBe("A casual trader");
    expect(who("VT1")).toBe("A value trader");
    expect(who("Z9")).toBe("A trader");
  });
});

describe("narrate for a person trading", () => {
  const base = { seq: 1, sim_time: 0 };
  const trade = (buyer: string, seller: string, price: number, quantity: number): MarketEvent => ({
    ...base,
    type: "Trade",
    trade_id: 1,
    symbol: "DEMO1",
    price,
    quantity,
    buy_order_id: 1,
    sell_order_id: 2,
    buy_account_id: buyer,
    sell_account_id: seller,
    aggressor_side: "BUY",
  });

  it("says what happened to you, not just to the market", () => {
    const events = [trade("you", "NT3", 250_005, 12)];
    expect(narrate(events, [1], 1, 1, "you")).toEqual(["Your order traded: you bought 12 shares at ₹2,500.05."]);
    expect(narrate([trade("NT3", "you", 250_005, 1)], [1], 1, 1, "you")).toEqual(["Your order traded: you sold 1 share at ₹2,500.05."]);
  });

  it("gives an average when your order trades at several prices", () => {
    const events = [trade("you", "A", 250_000, 10), trade("you", "B", 250_010, 10)];
    expect(narrate(events, [2], 2, 1, "you")[0]).toBe(
      "Your order traded: you bought 20 shares at ₹2,500.05 on average (from ₹2,500.00 to ₹2,500.10).",
    );
  });

  it("describes other people's trades as before", () => {
    expect(narrate([trade("A", "B", 250_000, 5)], [1], 1, 1, "you")[0]).toBe("5 shares changed hands at ₹2,500.00. A buyer paid the seller's price.");
  });

  it("names you when you join the queue", () => {
    const joined: MarketEvent = {
      ...base,
      type: "OrderAccepted",
      order_id: 9,
      account_id: "you",
      symbol: "DEMO1",
      side: "BUY",
      order_type: "LIMIT",
      quantity: 10,
      limit_price: 249_000,
      tif: "DAY",
    };
    expect(narrate([joined], [1], 1, 1, "you")).toEqual(["You joined the queue to buy 10 shares at ₹2,490.00."]);
  });
});

import { lastTradeText, shares as sharesText } from "./narrate";

describe("naming the company", () => {
  it("says which company's shares changed hands", () => {
    expect(sharesText(13, "UDHAAR")).toBe("13 UDHAAR shares");
    expect(sharesText(1, "UDHAAR")).toBe("1 UDHAAR share");
    expect(sharesText(2)).toBe("2 shares");
  });
  it("describes the last trade in one line", () => {
    expect(lastTradeText({ price: 164235, quantity: 13, aggressor: "BUY" }, "UDHAAR")).toBe(
      "13 UDHAAR shares changed hands at ₹1,642.35 (a buyer paid the seller's price)",
    );
  });
});
