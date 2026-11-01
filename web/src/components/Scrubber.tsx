import { useRef } from "react";
import { dayClock } from "../lib/format";
import { Point } from "../lib/series";
import { useWidth } from "../lib/useWidth";
import { SPEEDS, Status } from "../lib/useRun";

interface Props {
  series: Point[];
  durationUs: number;
  preOpenUs: number;
  referencePrice: number;
  nowUs: number; // the time of the moment on screen
  count: number; // events on screen
  total: number; // events received so far
  following: boolean;
  status: Status;
  speed: number;
  biggest: { from: Point; to: Point } | null;
  onSeek: (timeUs: number) => void;
  onLive: () => void;
  onPlayPause: () => void;
  onSpeed: (speed: number) => void;
  onAuction: () => void;
  onBiggest: () => void;
}

const HEIGHT = 112;
const PLOT = 76;

export function Scrubber(p: Props) {
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box);
  const duration = Math.max(p.durationUs, 1);
  const x = (t: number) => Math.min(width, Math.max(0, (t / duration) * width));
  const prices = [...p.series.map((pt) => pt.price), p.referencePrice];
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const y = (price: number) => 8 + (PLOT - 16) * (1 - (price - low) / Math.max(high - low, 1));
  const line = p.series.map((pt) => `${x(pt.t).toFixed(1)},${y(pt.price).toFixed(1)}`).join(" ");
  const tickEvery = duration > 20 * 60_000_000 ? 300_000_000 : 60_000_000;
  const ticks: number[] = [];
  for (let t = 0; t <= duration; t += tickEvery) ticks.push(t);
  const cursorX = x(p.nowUs);
  const hereLeft = cursorX > width - 110;
  const playing = p.status === "playing";
  const canPause = p.status === "playing" || p.status === "paused";

  return (
    <section className="card scrubber" aria-labelledby="replay-title">
      <div className="controls">
        <h2 id="replay-title">Replay the day</h2>
        <button className="round" onClick={p.onPlayPause} disabled={!canPause} aria-label={playing ? "Pause" : "Play"}>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
            {playing ? (
              <path d="M3 2h4v12H3zM9 2h4v12H9z" fill="currentColor" />
            ) : (
              <path d="M4 2 L14 8 L4 14 Z" fill="currentColor" />
            )}
          </svg>
        </button>
        <button
          className="btn"
          onClick={() => p.onSpeed(SPEEDS[(SPEEDS.indexOf(p.speed) + 1) % SPEEDS.length])}
          aria-label={`Playback speed ${p.speed} times. Select to change.`}
        >
          Speed {p.speed}×
        </button>
        <button className="btn" onClick={p.onAuction}>
          Go to the opening auction
        </button>
        <button className="btn" onClick={p.onBiggest} disabled={!p.biggest}>
          Go to the biggest price move
        </button>
        {!p.following && (
          <button className="btn primary" onClick={p.onLive}>
            Back to the latest moment
          </button>
        )}
        <div className="muted where">
          {p.count === 0
            ? "Waiting for the day to start."
            : `You are looking at ${dayClock(p.nowUs)} into the day (event ${p.count.toLocaleString("en-IN")} of ${(
                p.total
              ).toLocaleString("en-IN")} so far).`}
        </div>
      </div>

      <div className="strip" ref={box}>
        <svg
          role="img"
          aria-label="The day's price as a line, with the pre-open period shaded, the opening auction, the biggest price move, and a marker for the moment on screen"
          width={width}
          height={HEIGHT}
        >
          <rect x={0} y={4} width={x(p.preOpenUs)} height={PLOT} fill="var(--shade)" />
          {p.series.length > 1 && <polyline fill="none" stroke="var(--ink)" strokeWidth={2} points={line} />}
          <line x1={x(p.preOpenUs)} x2={x(p.preOpenUs)} y1={2} y2={PLOT + 4} stroke="var(--ink)" strokeWidth={2} strokeDasharray="4 3" />
          {p.biggest && (
            <>
              <line x1={x(p.biggest.to.t)} x2={x(p.biggest.to.t)} y1={2} y2={PLOT + 4} stroke="var(--sell)" strokeWidth={2} />
              <circle cx={x(p.biggest.to.t)} cy={y(p.biggest.to.price)} r={5} fill="var(--sell)" />
            </>
          )}
          <line x1={cursorX} x2={cursorX} y1={0} y2={PLOT + 4} stroke="var(--buy)" strokeWidth={3} />
          <line x1={0} x2={width} y1={PLOT + 4} y2={PLOT + 4} stroke="var(--ink)" />
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={PLOT + 4} y2={PLOT + 10} stroke="var(--muted)" />
              <text x={Math.min(x(t) + 3, width - 42)} y={PLOT + 24} className="tick">
                {Math.round(t / 60_000_000)}:00
              </text>
            </g>
          ))}
          <text x={6} y={22} className="tick">Before the open</text>
          <text x={x(p.preOpenUs) + 6} y={16} className="tick strong">Opening auction</text>
          {p.biggest && (
            <text x={x(p.biggest.to.t) + 8} y={30} className="tick sell">Biggest move</text>
          )}
          <text x={hereLeft ? cursorX - 8 : cursorX + 8} y={PLOT - 6} textAnchor={hereLeft ? "end" : "start"} className="tick here">
            You are here
          </text>
        </svg>
        <input
          type="range"
          className="slider"
          min={0}
          max={duration}
          step={1000}
          value={Math.min(p.nowUs, duration)}
          onChange={(e) => p.onSeek(Number(e.target.value))}
          aria-label="Move through the day"
          aria-valuetext={`${dayClock(p.nowUs)} into the day`}
        />
      </div>
    </section>
  );
}
