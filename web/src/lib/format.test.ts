import { describe, expect, it } from "vitest";
import { changeWords, dayClock, money, rupees } from "./format";

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
