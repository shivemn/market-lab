import { describe, expect, it } from "vitest";
import { fold, type MarketEvent, type Side } from "./market";
import { previewOrder } from "./preview";

let seq = 0;
const open = (): MarketEvent => ({ type: "SessionChanged", seq: ++seq, sim_time: 0, session: "OPEN" });
const rest = (id: number, side: Side, price: number, quantity: number): MarketEvent => ({
  type: "OrderAccepted",
  seq: ++seq,
  sim_time: 0,
  order_id: id,
  account_id: "NT1",
  symbol: "DEMO1",
  side,
  order_type: "LIMIT",
  quantity,
  limit_price: price,
  tif: "DAY",
});

// Sellers: 10 at 2,500.10 and 30 at 2,500.20. Buyers: 20 at 2,499.90.
const market = () => fold([open(), rest(1, "SELL", 250_010, 10), rest(2, "SELL", 250_020, 30), rest(3, "BUY", 249_990, 20)]);

describe("previewOrder", () => {
  it("asks for a sensible quantity", () => {
    expect(previewOrder(market(), "BUY", 0, null)).toBe("Enter how many shares you want.");
    expect(previewOrder(market(), "BUY", 1.5, null)).toBe("Enter how many shares you want.");
  });

  it("says a closed market takes no orders, and a pre-open market makes you wait for the auction", () => {
    expect(previewOrder(fold([]), "BUY", 5, null)).toContain("closed");
    const pre = fold([{ type: "SessionChanged", seq: 1, sim_time: 0, session: "PRE_OPEN" }]);
    expect(previewOrder(pre, "BUY", 5, null)).toContain("opening auction");
  });

  it("walks the queue for a market buy and says what the average price would be", () => {
    // 10 at 2,500.10 and 5 at 2,500.20 = 250,010*10 + 250,020*5 = 3,750,200 paise for 15 shares = 250,013.33 -> 2,500.13
    expect(previewOrder(market(), "BUY", 15, null)).toBe(
      "You would buy all 15 shares right away at about ₹2,500.13 each, taking the best prices in the queue first.",
    );
  });

  it("warns when a market order is bigger than what the queue holds", () => {
    const text = previewOrder(market(), "BUY", 100, null);
    expect(text).toContain("Only 40 shares are for sale");
    expect(text).toContain("the rest would be cancelled");
  });

  it("says a market order cannot trade when the other side is empty", () => {
    const sellersOnly = fold([open(), rest(1, "SELL", 250_010, 10)]);
    expect(previewOrder(sellersOnly, "SELL", 5, null)).toBe("Nobody is buying right now, so this order would not trade.");
  });

  it("says a limit buy at or above the best asking price trades right away", () => {
    expect(previewOrder(market(), "BUY", 10, 250_010)).toContain("This would trade right away: you buy 10 shares at about ₹2,500.10");
  });

  it("splits a limit order that partly trades", () => {
    const text = previewOrder(market(), "BUY", 25, 250_010);
    expect(text).toBe("Part would trade right away: 10 shares at about ₹2,500.10 each. The other 15 would join the queue at ₹2,500.10.");
  });

  it("tells a resting buyer how many shares are ahead at that price", () => {
    expect(previewOrder(market(), "BUY", 5, 249_990)).toContain("20 shares already waiting at ₹2,499.90 would trade before yours");
    expect(previewOrder(market(), "BUY", 5, 249_950)).toContain("first in line");
  });

  it("works the same way for sellers", () => {
    expect(previewOrder(market(), "SELL", 5, 249_990)).toContain("This would trade right away: you sell 5 shares at about ₹2,499.90");
    expect(previewOrder(market(), "SELL", 5, 250_020)).toContain("30 shares already waiting at ₹2,500.20 would trade before yours");
  });
});
