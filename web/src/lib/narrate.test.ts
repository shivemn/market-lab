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
