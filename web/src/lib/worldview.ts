import type { IndexKind, WorldSnapshot } from "./world";

/** How the day has gone for the whole account, worked out from two snapshots of the world. */
export interface WorldDay {
  startWorth: number;
  endWorth: number;
  result: number; // endWorth - startWorth
  charges: number; // paid during this day
  priceMoves: number; // result before charges
  youPercent: number; // result as a share of the worth at the start, in percent
}

export function worldDay(first: WorldSnapshot, now: WorldSnapshot): WorldDay {
  const result = now.worth - first.worth;
  const charges = now.total_charges - first.total_charges;
  return {
    startWorth: first.worth,
    endWorth: now.worth,
    result,
    charges,
    priceMoves: result + charges,
    youPercent: first.worth === 0 ? 0 : (result / first.worth) * 100,
  };
}

/** The index's change today in percent. */
export const indexPercent = (snapshot: WorldSnapshot, kind: IndexKind): number => {
  const view = snapshot.indices[kind];
  return view.open === 0 ? 0 : (view.change / view.open) * 100;
};

export interface Comparison {
  you: number;
  index: number;
  gap: number; // you - index, in percentage points
  words: string;
}

/** You against the index, in plain words. Holding only cash counts as a choice: it falls behind a rising market. */
export function compare(youPercent: number, indexPct: number, indexName: string): Comparison {
  const gap = youPercent - indexPct;
  const pts = Math.abs(gap).toFixed(2);
  const words =
    Math.abs(gap) < 0.005 ? `Level with ${indexName}` : gap > 0 ? `Ahead of ${indexName} by ${pts}%` : `Behind ${indexName} by ${pts}%`;
  return { you: youPercent, index: indexPct, gap, words };
}

export const sign = (n: number): string => (Math.abs(n) < 0.005 ? "0.00%" : `${n > 0 ? "+" : "−"}${Math.abs(n).toFixed(2)}%`);

/** What the day's clock says, from the world's time. */
export function sessionAt(now: number, openAt: number, closeAt: number): "PRE_OPEN" | "OPEN" | "CLOSED" {
  if (now < openAt) return "PRE_OPEN";
  return now < closeAt ? "OPEN" : "CLOSED";
}

export const INDEX_TEXT: Record<IndexKind, { name: string; how: string }> = {
  cap: {
    name: "By company size",
    how: "Big companies move this index more. Each company counts in proportion to its share price times the number of shares open to the public. Nifty 50 and Sensex work this way.",
  },
  equal: {
    name: "Every company the same",
    how: "Every company counts equally, however big. A 1% rise in the smallest firm moves the index as much as a 1% rise in the largest.",
  },
  price: {
    name: "Dearer shares count more",
    how: "A company with a more expensive share counts for more, whatever its size. The Dow Jones works this way, which is why one pricey share can sway it.",
  },
};
