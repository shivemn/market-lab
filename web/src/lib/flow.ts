import type { MarketEvent } from "./market";

export type TraderKind = "mm" | "value" | "noise" | "you" | "other";

/** What kind of trader an account is, from its name: market makers are MM1.., value traders VT1.., casual traders NT1.. */
export function kindOf(id: string, owner: string): TraderKind {
  if (owner !== "" && id === owner) return "you";
  if (/^MM\d+$/.test(id)) return "mm";
  if (/^VT\d+$/.test(id)) return "value";
  if (/^NT\d+$/.test(id)) return "noise";
  return "other";
}

export interface FlowNode {
  id: string;
  kind: TraderKind;
  shares: number; // traded today, either side
  p: [number, number, number]; // a place in 3D: market makers in the middle, casual traders on the outside
}

export interface FlowEdge {
  a: number;
  b: number;
  shares: number;
  mine: boolean;
}

export interface FlowTrade {
  seq: number;
  from: number; // the seller's node
  to: number; // the buyer's node
  mine: boolean;
}

export interface Flow {
  nodes: FlowNode[];
  edges: FlowEdge[];
  trades: FlowTrade[];
  shares: number;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10_000) / 10_000;
}

const RING = { mm: 60, value: 185, other: 240, noise: 300 } as const;
const HEIGHT = { mm: 30, value: 110, other: 150, noise: 190 } as const;

function place(kind: TraderKind, index: number, count: number, id: string): [number, number, number] {
  if (kind === "you") return [140, 58, 118];
  const r = RING[kind] * (kind === "mm" ? 1 : 0.92 + hash(id + "r") * 0.16);
  const a = (index / Math.max(1, count)) * Math.PI * 2 + (kind === "value" ? 0.3 : kind === "noise" ? 0.1 : 0.7) + hash(id) * 0.25;
  return [Math.cos(a) * r, (hash(id + "y") - 0.5) * HEIGHT[kind], Math.sin(a) * r];
}

/** Who traded with whom in one company today, from its events. The layout depends only on who took part. */
export function buildFlow(events: readonly MarketEvent[], owner: string): Flow {
  const index = new Map<string, number>();
  const ids: string[] = [];
  const pairs = new Map<string, FlowEdge>();
  const shares = new Map<string, number>();
  const raw: { seq: number; seller: string; buyer: string; qty: number }[] = [];
  for (const e of events) {
    if (e.type !== "Trade") continue;
    raw.push({ seq: e.seq, seller: e.sell_account_id, buyer: e.buy_account_id, qty: e.quantity });
    for (const id of [e.sell_account_id, e.buy_account_id]) {
      if (!index.has(id)) {
        index.set(id, -1);
        ids.push(id);
      }
      shares.set(id, (shares.get(id) ?? 0) + e.quantity);
    }
  }
  ids.sort();
  const byKind = new Map<TraderKind, string[]>();
  for (const id of ids) {
    const k = kindOf(id, owner);
    byKind.set(k, [...(byKind.get(k) ?? []), id]);
  }
  const nodes: FlowNode[] = ids.map((id, i) => {
    index.set(id, i);
    const kind = kindOf(id, owner);
    const group = byKind.get(kind) ?? [id];
    return { id, kind, shares: shares.get(id) ?? 0, p: place(kind, group.indexOf(id), group.length, id) };
  });
  let total = 0;
  const trades: FlowTrade[] = raw.map((t) => {
    const from = index.get(t.seller) ?? 0;
    const to = index.get(t.buyer) ?? 0;
    const key = from < to ? `${from}:${to}` : `${to}:${from}`;
    const mine = owner !== "" && (t.seller === owner || t.buyer === owner);
    const edge = pairs.get(key) ?? { a: Math.min(from, to), b: Math.max(from, to), shares: 0, mine };
    edge.shares += t.qty;
    pairs.set(key, edge);
    total += t.qty;
    return { seq: t.seq, from, to, mine };
  });
  return { nodes, edges: [...pairs.values()], trades, shares: total };
}

/** A point in 3D seen from a camera turned by `angle` around the upright axis and tilted down a little. */
export function project(p: readonly [number, number, number], angle: number, tilt = 0.38): { x: number; y: number; z: number; s: number } {
  const ca = Math.cos(angle);
  const sa = Math.sin(angle);
  const x1 = p[0] * ca + p[2] * sa;
  const z1 = -p[0] * sa + p[2] * ca;
  const y2 = p[1] * Math.cos(tilt) - z1 * Math.sin(tilt);
  const z2 = p[1] * Math.sin(tilt) + z1 * Math.cos(tilt);
  const s = 1100 / (1100 + z2);
  return { x: 500 + x1 * s, y: 135 + y2 * s * 0.6, z: z2, s };
}
