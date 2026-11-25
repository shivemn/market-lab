/**
 * The Galton board on the Practice screen. Each simulated run (from the server) drops as a ball through ten rows of
 * pegs into the bin of the price where it really ended. The bounces only show how many small random steps add up to a
 * bell shape; which bin a ball lands in is always its own run's result.
 */

export const ROWS = 10;
export const BINS = ROWS + 1;
export const SPAWN_MS = 85; // one ball every this many milliseconds
export const ROW_MS = 90; // time to fall from one row of pegs to the next
export const DROP_MS = 320; // time to fall from the last row into the bin
export const FLIGHT_MS = ROWS * ROW_MS + DROP_MS;

/** Drawing space: a 520 by 330 box. */
export const W = 520;
export const H = 330;
export const CX = W / 2;
export const DX = 36; // distance between pegs, and the width of a bin
export const PEG_TOP = 22;
export const ROW_GAP = 15;
export const FLOOR = 322;
export const BAR_MAX = 140;

export interface Run {
  bin: number;
  moves: number[]; // 1 = right, 0 = left, one per row; exactly `bin` of them are 1
  spawn: number; // ms after the start
  end: number; // paise
}

export interface Board {
  start: number;
  low: number; // paise at the left edge of bin 0
  binWidth: number; // paise per bin
  runs: Run[];
  maxCount: number;
  p05: number;
  p50: number;
  p95: number;
  total: number; // ms until the last ball has landed
}

function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const quantile = (sorted: readonly number[], f: number) => sorted[Math.min(sorted.length - 1, Math.floor(f * sorted.length))];

/** Sort each run's end price into a bin and give it a path of bounces that lands there. The same input gives the same board. */
export function buildBoard(paths: readonly (readonly number[])[], start: number, seed = 1): Board {
  const ends = paths.map((p) => p[p.length - 1]);
  const sorted = [...ends].sort((a, b) => a - b);
  let low = quantile(sorted, 0.01) ?? start;
  let high = quantile(sorted, 0.99) ?? start;
  if (high - low < BINS) {
    low = Math.min(low, start) - BINS;
    high = Math.max(high, start) + BINS;
  }
  const binWidth = (high - low) / BINS;
  const rand = prng(seed);
  const counts = new Array<number>(BINS).fill(0);
  const runs = ends.map((end, i) => {
    const bin = Math.max(0, Math.min(BINS - 1, Math.floor((end - low) / binWidth)));
    counts[bin] += 1;
    const moves = Array.from({ length: ROWS }, (_, k): number => (k < bin ? 1 : 0));
    for (let j = moves.length - 1; j > 0; j--) {
      const k = Math.floor(rand() * (j + 1));
      [moves[j], moves[k]] = [moves[k], moves[j]];
    }
    return { bin, moves, spawn: i * SPAWN_MS, end };
  });
  return {
    start,
    low,
    binWidth,
    runs,
    maxCount: Math.max(1, ...counts),
    p05: quantile(sorted, 0.05) ?? start,
    p50: quantile(sorted, 0.5) ?? start,
    p95: quantile(sorted, 0.95) ?? start,
    total: runs.length === 0 ? 0 : runs[runs.length - 1].spawn + FLIGHT_MS,
  };
}

export const binCentre = (bin: number) => CX + (bin - (BINS - 1) / 2) * DX;
export const binLeft = (bin: number) => CX + (bin - BINS / 2) * DX;

export interface Frame {
  counts: number[];
  landed: number;
  above: number; // of the landed runs, how many ended above the starting price
  balls: { x: number; y: number }[];
  newest: { x: number; y: number } | null;
  /** The bin the latest ball fell into, while it is still glowing. */
  glow: number | null;
}

/** Where everything is `ms` after the balls start falling. */
export function boardFrame(board: Board, ms: number): Frame {
  const counts = new Array<number>(BINS).fill(0);
  let landed = 0;
  let above = 0;
  let lastLanded: Run | null = null;
  const flying: [Run, number][] = [];
  for (const run of board.runs) {
    const tau = ms - run.spawn;
    if (tau < 0) break;
    if (tau >= FLIGHT_MS) {
      counts[run.bin] += 1;
      landed += 1;
      if (run.end > board.start) above += 1;
      lastLanded = run;
    } else flying.push([run, tau]);
  }
  const step = BAR_MAX / board.maxCount;
  const balls = flying.map(([run, tau]) => {
    if (tau < ROWS * ROW_MS) {
      const k = Math.floor(tau / ROW_MS);
      const f = (tau - k * ROW_MS) / ROW_MS;
      let rights = 0;
      for (let m = 0; m < k; m++) rights += run.moves[m];
      const x0 = CX + (rights - k / 2) * DX;
      const x1 = CX + (rights + run.moves[k] - (k + 1) / 2) * DX;
      return { x: x0 + (x1 - x0) * f, y: PEG_TOP + k * ROW_GAP - 6 + ROW_GAP * f - Math.sin(Math.PI * f) * 5 };
    }
    const g = (tau - ROWS * ROW_MS) / DROP_MS;
    const yEnd = FLOOR - counts[run.bin] * step - 4;
    const yStart = PEG_TOP + ROWS * ROW_GAP - 6;
    return { x: binCentre(run.bin), y: yStart + (yEnd - yStart) * g * g };
  });
  const newest = balls.length > 0 ? balls[balls.length - 1] : null;
  const glow = lastLanded !== null && ms - lastLanded.spawn - FLIGHT_MS < 260 ? lastLanded.bin : null;
  return { counts, landed, above, balls: balls.slice(0, -1), newest, glow };
}
