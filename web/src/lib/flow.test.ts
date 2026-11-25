import { describe, expect, it } from "vitest";
import type { MarketEvent } from "./market";
import { buildFlow, kindOf, project } from "./flow";

let seq = 0;
const trade = (seller: string, buyer: string, qty: number): MarketEvent => ({
  type: "Trade", seq: ++seq, sim_time: seq, trade_id: seq, symbol: "X", price: 100, quantity: qty,
  buy_order_id: 1, sell_order_id: 2, buy_account_id: buyer, sell_account_id: seller, aggressor_side: "BUY",
});

describe("kindOf", () => {
  it("reads the kind of trader from the account name", () => {
    expect(kindOf("MM1", "shi")).toBe("mm");
    expect(kindOf("VT2", "shi")).toBe("value");
    expect(kindOf("NT13", "shi")).toBe("noise");
    expect(kindOf("shi", "shi")).toBe("you");
    expect(kindOf("someone", "")).toBe("other");
  });
});

describe("buildFlow", () => {
  const events = [trade("NT1", "MM1", 5), trade("MM1", "NT1", 3), trade("MM2", "shi", 2), trade("VT1", "MM2", 10)];
  const flow = buildFlow(events, "shi");
  it("has one node per trader and one edge per pair, adding shares both ways", () => {
    expect(flow.nodes.map((n) => n.id)).toEqual(["MM1", "MM2", "NT1", "VT1", "shi"]);
    const mm1 = flow.nodes.findIndex((n) => n.id === "MM1");
    const nt1 = flow.nodes.findIndex((n) => n.id === "NT1");
    const pair = flow.edges.find((e) => (e.a === mm1 && e.b === nt1) || (e.a === nt1 && e.b === mm1));
    expect(pair?.shares).toBe(8);
    expect(flow.edges).toHaveLength(3);
    expect(flow.shares).toBe(20);
  });
  it("sends each trade from the seller to the buyer and marks yours", () => {
    const mine = flow.trades.filter((t) => t.mine);
    expect(mine).toHaveLength(1);
    expect(flow.nodes[mine[0].to].id).toBe("shi");
    expect(flow.nodes[mine[0].from].id).toBe("MM2");
  });
  it("puts the same traders in the same places every time", () => {
    expect(buildFlow(events, "shi").nodes).toEqual(flow.nodes);
  });
  it("is empty before anything trades", () => {
    expect(buildFlow([], "shi")).toEqual({ nodes: [], edges: [], trades: [], shares: 0 });
  });
});

describe("project", () => {
  it("draws nearer points bigger", () => {
    const near = project([0, 0, -200], 0);
    const far = project([0, 0, 200], 0);
    expect(near.s).toBeGreaterThan(far.s);
  });
});
