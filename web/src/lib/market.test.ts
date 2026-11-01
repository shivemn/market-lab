import { describe, expect, it } from "vitest";
import day from "../fixtures/day.json";
import { fold, MarketEvent, MarketState, stateJson } from "./market";

interface Case {
  name: string;
  events: MarketEvent[];
  ends: number[];
  states: ReturnType<typeof stateJson>[];
}

const cases = (day as unknown as { cases: Case[] }).cases;

describe("the TypeScript fold gives the same market as the Python fold", () => {
  for (const c of cases) {
    it(`${c.name}: every checked command boundary matches`, () => {
      const state = new MarketState();
      const expected = new Map(c.states.map((s) => [s.at, s]));
      let previous = 0;
      let checked = 0;
      for (const end of c.ends) {
        for (let i = previous; i < end; i++) state.apply(c.events[i]);
        previous = end;
        const want = expected.get(end);
        if (want) {
          expect(stateJson(state)).toEqual(want);
          checked += 1;
        }
      }
      expect(checked).toBe(c.states.length);
      expect(checked).toBeGreaterThan(5);
    });
  }

  it("folding the first N events equals applying them one by one", () => {
    const c = cases[0];
    const direct = fold(c.events, 14);
    const step = new MarketState();
    c.events.slice(0, 14).forEach((e) => step.apply(e));
    expect(stateJson(direct)).toEqual(stateJson(step));
  });

  it("the scripted day ends with an empty book and the right totals", () => {
    const state = fold(cases[0].events);
    expect(state.session).toBe("CLOSED");
    expect(state.orders.size).toBe(0);
    expect(state.volume).toBe(205);
    expect(state.trades).toBe(6);
  });
});
