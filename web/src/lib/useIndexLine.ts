import { useMemo } from "react";
import { indexSeries, Point } from "./series";
import type { MarketEvent } from "./market";
import type { IndexKind, WorldSnapshot, WorldStart } from "./world";

/** The chosen index drawn through the day: its level after each trade in any company (see `indexSeries`). */
export function useIndexLine(
  events: Readonly<Record<string, readonly MarketEvent[]>>,
  version: number,
  factors: WorldStart["index_factors"] | null,
  snapshot: WorldSnapshot | null,
  kind: IndexKind,
): Point[] {
  return useMemo(() => {
    const f = factors?.[kind];
    if (!f || !snapshot) return [];
    const closes = Object.fromEntries(snapshot.companies.map((c) => [c.symbol, c.instrument.reference_price]));
    return indexSeries(events, f, closes, Math.max(1, Math.floor(snapshot.close_at / 600)));
    // `events` is one array that grows in place; `version` is what changes when it does
  }, [version, kind, factors, snapshot?.id]); // eslint-disable-line react-hooks/exhaustive-deps
}
