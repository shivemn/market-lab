import { useEffect, useMemo, useState } from "react";
import { BINS, binCentre, binLeft, boardFrame, buildBoard, CX, DX, FLOOR, H, PEG_TOP, ROW_GAP, ROWS, W, BAR_MAX } from "../lib/galton";
import { clock, money, rupees } from "../lib/format";
import { getWorldPaths, type WorldPaths } from "../lib/world";
import { Panel } from "../ui";
import { useFrameClock } from "../ui/motion";

interface Props {
  worldId: string;
  symbol: string;
  openAt: number;
  closeAt: number;
}

const circle = (x: number, y: number, r: number) => `M${(x - r).toFixed(1)} ${y.toFixed(1)}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`;

const PEGS = (() => {
  let d = "";
  for (let row = 0; row < ROWS; row++) for (let j = 0; j <= row; j++) d += circle(CX + (j - row / 2) * DX, PEG_TOP + row * ROW_GAP, 2.2);
  return d;
})();
const WALLS = Array.from({ length: BINS + 1 }, (_, w) => `M${binLeft(w).toFixed(1)} 182V${FLOOR}`).join("");

/**
 * Where the price could be at the close, as a Galton board: each of 200 simulated runs drops as a ball into the bin of
 * the price it really ended at. The runs come from the server and start at the last trade, never at the hidden value
 * the simulated traders see.
 */
export function PricePaths({ worldId, symbol, openAt, closeAt }: Props) {
  const [fan, setFan] = useState<WorldPaths | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    let live = true;
    setError(null);
    getWorldPaths(worldId, symbol)
      .then((reply) => live && setFan(reply))
      .catch((problem: unknown) => live && setError(problem instanceof Error ? problem.message : String(problem)));
    return () => {
      live = false;
    };
  }, [worldId, symbol, again]);
  const board = useMemo(
    () => (fan === null || fan.symbol !== symbol ? null : buildBoard(fan.paths, fan.start, fan.times[0] + fan.start)),
    [fan, symbol],
  );
  const { elapsed, still } = useFrameClock(board !== null && !paused, board);
  const done = board !== null && (still || elapsed >= board.total);
  const frame = board === null ? null : boardFrame(board, still ? Number.POSITIVE_INFINITY : elapsed);
  const step = board === null ? 0 : BAR_MAX / board.maxCount;
  const nowX = board === null ? CX : binLeft(0) + ((board.start - board.low) / (board.binWidth * BINS)) * BINS * DX;
  const from = fan === null ? "" : clock(fan.times[0], openAt, closeAt);
  const label =
    board === null || frame === null
      ? "Simulated runs of the price to the close."
      : `Galton board for ${symbol}: 200 simulated runs from ${from} to 15:30. The middle 90% end between ${rupees(board.p05)} and ${rupees(board.p95)}; ${Math.round((frame.above / Math.max(1, frame.landed)) * 100)}% of the runs shown end above ${rupees(board.start)}.`;
  return (
    <Panel
      id="paths-title"
      className="paths-panel"
      title={`Where ${symbol} could close`}
      meta={
        <span className="paths-controls">
          <button className="chip-btn" type="button" onClick={() => setAgain((n) => n + 1)} disabled={fan === null && error === null}>
            Run again
          </button>
          {!still && (
            <button className="chip-btn" type="button" aria-pressed={paused} onClick={() => setPaused((p) => !p)} disabled={done}>
              {paused ? "Play" : "Pause"}
            </button>
          )}
        </span>
      }
    >
      {error !== null ? (
        <p className="error">{error}</p>
      ) : board === null || frame === null ? (
        <p className="muted small paths-wait">Working out 200 possible paths…</p>
      ) : (
        <>
          <dl className="paths-stats">
            <div>
              <dt>Runs landed</dt>
              <dd>{frame.landed} / 200</dd>
            </div>
            <div>
              <dt>Middle 90% at 15:30</dt>
              <dd>
                {rupees(board.p05)} – {rupees(board.p95)}
              </dd>
            </div>
            <div>
              <dt>Above {from}</dt>
              <dd>{frame.landed === 0 ? "—" : `${Math.round((frame.above / frame.landed) * 100)}%`}</dd>
            </div>
          </dl>
          <div className="paths-box">
            <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
              <path className="g-walls" d={WALLS} />
              {frame.counts.map((n, bin) =>
                n === 0 ? null : (
                  <rect key={bin} className={`g-bar${frame.glow === bin ? " glow" : ""}`} x={binLeft(bin) + 3} y={FLOOR - n * step} width={DX - 6} height={n * step} />
                ),
              )}
              <line className="g-now" x1={nowX} x2={nowX} y1={178} y2={FLOOR} />
              <path className="g-pegs" d={PEGS} />
              <path className="g-balls" d={frame.balls.map((b) => circle(b.x, b.y, 3.2)).join("")} />
              {frame.newest && <path className="g-newest" d={circle(frame.newest.x, frame.newest.y, 3.6)} />}
              <line className="g-floor" x1={binLeft(0)} x2={binLeft(BINS)} y1={FLOOR} y2={FLOOR} />
              {[0, 2, 5, 8, 10].map((bin) => (
                <text key={bin} className="tick" x={binCentre(bin)} y={H + 2} textAnchor="middle">
                  {money(Math.round(board.low + (bin + 0.5) * board.binWidth)).replace(/\.\d\d$/, "")}
                </text>
              ))}
              <text className="tick strong" x={nowX + 4} y={174}>
                now {money(board.start)}
              </text>
              <text className="tick" x={4} y={12}>
                {from} · last trade
              </text>
            </svg>
          </div>
          <p className="muted small paths-note">
            Each ball is one simulated run from the last trade to the close, using only the model's settings (random drift
            plus rare jumps). The pegs show how many small random steps add up to a bell shape; the bin is where that run
            really ended. News that has not come out yet is not in the runs.
          </p>
        </>
      )}
    </Panel>
  );
}
