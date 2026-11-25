import { describe, expect, it } from "vitest";
import { BINS, boardFrame, buildBoard, FLIGHT_MS, ROWS } from "./galton";

const paths = Array.from({ length: 200 }, (_, i) => [100_000, 100_000 + ((i * 37) % 200) * 10 - 1_000]);

describe("buildBoard", () => {
  const board = buildBoard(paths, 100_000, 7);
  it("lands every run in the bin of its own end price, with exactly that many right bounces", () => {
    for (const run of board.runs) {
      expect(run.moves).toHaveLength(ROWS);
      expect(run.moves.reduce((a, b) => a + b, 0)).toBe(run.bin);
      const lo = board.low + run.bin * board.binWidth;
      if (run.bin > 0 && run.bin < BINS - 1) {
        expect(run.end).toBeGreaterThanOrEqual(lo);
        expect(run.end).toBeLessThan(lo + board.binWidth);
      }
    }
  });
  it("is the same for the same input and seed", () => {
    expect(buildBoard(paths, 100_000, 7)).toEqual(board);
  });
  it("orders the middle 90% range", () => {
    expect(board.p05).toBeLessThanOrEqual(board.p50);
    expect(board.p50).toBeLessThanOrEqual(board.p95);
  });
  it("copes with every run ending at the same price", () => {
    const flat = buildBoard([[500, 500], [500, 500]], 500);
    expect(flat.runs.every((r) => r.bin >= 0 && r.bin < BINS)).toBe(true);
  });
});

describe("boardFrame", () => {
  const board = buildBoard(paths, 100_000, 7);
  it("starts empty and ends with every ball in its bin", () => {
    expect(boardFrame(board, -1).landed).toBe(0);
    const done = boardFrame(board, board.total + 1);
    expect(done.landed).toBe(200);
    expect(done.balls).toHaveLength(0);
    const expected = new Array(BINS).fill(0);
    for (const r of board.runs) expected[r.bin] += 1;
    expect(done.counts).toEqual(expected);
    expect(done.above).toBe(paths.filter((p) => p[1] > 100_000).length);
  });
  it("counts only the balls that have finished falling", () => {
    const mid = boardFrame(board, board.runs[10].spawn + FLIGHT_MS);
    expect(mid.landed).toBe(11);
    expect(mid.counts.reduce((a, b) => a + b, 0)).toBe(11);
  });
});
