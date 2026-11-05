import { describe, expect, it } from "vitest";
import { changeShort, changeWords, clock, dayClock, money, rupees, signed } from "./format";

describe("money", () => {
  it("groups digits the Indian way", () => {
    expect(money(10_000_000)).toBe("1,00,000.00");
    expect(money(249_470)).toBe("2,494.70");
    expect(money(5)).toBe("0.05");
    expect(money(123_456_789)).toBe("12,34,567.89");
    expect(money(99_999)).toBe("999.99");
    expect(money(100_000)).toBe("1,000.00");
    expect(money(0)).toBe("0.00");
  });
  it("handles negatives", () => {
    expect(money(-249_470)).toBe("-2,494.70");
  });
  it("adds the rupee sign", () => {
    expect(rupees(250_000)).toBe("₹2,500.00");
  });
});

describe("dayClock", () => {
  it("says minutes and seconds", () => {
    expect(dayClock(393_176_000)).toBe("6 min 33 s");
    expect(dayClock(59_999_999)).toBe("59 s");
    expect(dayClock(0)).toBe("0 s");
  });
});

describe("changeWords", () => {
  it("uses words, not just colour", () => {
    expect(changeWords(249_470, 250_000)).toBe("Down ₹5.30 (0.21%)");
    expect(changeWords(250_500, 250_000)).toBe("Up ₹5.00 (0.20%)");
    expect(changeWords(250_000, 250_000)).toBe("Unchanged");
  });
});


describe("short forms for the new screens", () => {
  it("signs a result with words that do not depend on colour", () => {
    expect(signed(1230)).toBe("+₹12.30");
    expect(signed(-400)).toBe("−₹4.00");
    expect(signed(0)).toBe("₹0.00");
  });
  it("writes the time into the day as minutes and seconds", () => {
    expect(clock(0)).toBe("9:00");
    expect(clock(60_000_000)).toBe("9:15");
    expect(clock(660_000_000)).toBe("15:30");
    expect(clock(225_000_000)).toBe("10:58");
    expect(clock(61_900_000)).toBe("9:16");
  });
  it("shows the change from the close with an arrow", () => {
    expect(changeShort(251_190, 250_000)).toEqual({ dir: "up", text: "▲ ₹11.90 (0.48%)" });
    expect(changeShort(249_350, 250_000).dir).toBe("down");
    expect(changeShort(250_000, 250_000)).toEqual({ dir: "flat", text: "unchanged" });
  });
});

describe("index numbers", () => {
  it("shows hundredths of a point with Indian grouping and a sign", async () => {
    const { points, pointsSigned, percentSigned } = await import("./format");
    expect(points(101_235)).toBe("1,012.35");
    expect(points(10_000_000)).toBe("1,00,000.00");
    expect(pointsSigned(1_235)).toBe("+12.35");
    expect(pointsSigned(-310)).toBe("−3.10");
    expect(pointsSigned(0)).toBe("0.00");
    expect(percentSigned(1_200, 100_000)).toBe("+1.20%");
    expect(percentSigned(-500, 100_000)).toBe("−0.50%");
    expect(percentSigned(0, 100_000)).toBe("0.00%");
  });
});
