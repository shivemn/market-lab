import { describe, expect, it } from "vitest";
import { compare, sessionAt, sign, worldDay } from "./worldview";
import type { WorldSnapshot } from "./world";

const snap = (worth: number, charges: number) => ({ worth, total_charges: charges }) as WorldSnapshot;

describe("worldDay", () => {
  it("splits the day's result into price moves and charges", () => {
    const day = worldDay(snap(10_000_000, 0), snap(10_043_575, 1_200));
    expect(day.result).toBe(43_575);
    expect(day.charges).toBe(1_200);
    expect(day.priceMoves).toBe(44_775);
    expect(day.youPercent).toBeCloseTo(0.43575, 5);
  });
  it("counts only the charges paid during this day", () => {
    expect(worldDay(snap(10_000_000, 500), snap(9_999_000, 700)).charges).toBe(200);
  });
});

describe("compare", () => {
  it("says ahead, behind or level in words", () => {
    expect(compare(0.44, 0.31, "Shifty 12").words).toBe("Ahead of Shifty 12 by 0.13%");
    expect(compare(0, 0.31, "Shifty 12").words).toBe("Behind Shifty 12 by 0.31%");
    expect(compare(0.3, 0.301, "Shifty 12").words).toBe("Level with Shifty 12");
  });
});

describe("sign and sessionAt", () => {
  it("signs percentages without relying on colour", () => {
    expect(sign(0.44)).toBe("+0.44%");
    expect(sign(-1.2)).toBe("−1.20%");
    expect(sign(0.001)).toBe("0.00%");
  });
  it("tells the session from the clock", () => {
    expect(sessionAt(0, 60, 660)).toBe("PRE_OPEN");
    expect(sessionAt(60, 60, 660)).toBe("OPEN");
    expect(sessionAt(660, 60, 660)).toBe("CLOSED");
  });
});
