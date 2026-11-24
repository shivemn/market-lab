import { useRef } from "react";
import { addSample, type EquityPoint } from "./equity";
import type { WorldSnapshot } from "./world";

/**
 * The account's worth through the day, one point for every snapshot the server sends (every step of the clock, every
 * order). Each point is the server's own figure, so the line ends exactly on "Worth now". A new day starts a new line.
 */
export function useEquity(snapshot: WorldSnapshot | null): EquityPoint[] {
  const kept = useRef<{ id: string; series: EquityPoint[] }>({ id: "", series: [] });
  if (snapshot === null) return [];
  if (kept.current.id !== snapshot.id) kept.current = { id: snapshot.id, series: [] };
  kept.current.series = addSample(kept.current.series, snapshot.now, snapshot.worth);
  return kept.current.series;
}
