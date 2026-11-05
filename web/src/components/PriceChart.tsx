import { useMemo, useRef } from "react";
import { changeWords, clock, dayClock, rupees } from "../lib/format";
import type { MarketState } from "../lib/market";
import { extremes, Point, priceAxis, TradePoint, tradesUpTo, volumeSlices } from "../lib/series";
import { useWidth } from "../lib/useWidth";
import { SPEEDS, Status } from "../lib/useRun";

interface Props {
  symbol: string;
  trades: TradePoint[]; // every trade received so far
  state: MarketState; // the market at the moment on screen
  durationUs: number;
  preOpenUs: number;
  referencePrice: number;
  nowUs: number;
  following: boolean;
  status: Status;
  speed: number;
  biggest: { from: Point; to: Point } | null;
  onSeek: (timeUs: number) => void;
  onLive: () => void;
  onReplay: () => void;
  onPlayPause: () => void;
  onSpeed: (speed: number) => void;
  onAuction: () => void;
  onBiggest: () => void;
  practice?: boolean; // a live practice day: no scrubbing back, no jump buttons
}

const HEIGHT = 390;
const LEFT = 72;
const RIGHT = 16;
const TOP = 16;
const PRICE_BOTTOM = 286;
const VOLUME_TOP = 316;
const VOLUME_BOTTOM = 362;
const SLICES = 60;

const axisLabel = (paise: number) => (paise % 100 === 0 ? rupees(paise).slice(0, -3) : rupees(paise));

export function PriceChart(p: Props) {
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box);
  const narrow = width < 600; // on a phone: fewer words on the chart, the sentence under it says the rest
  const left = narrow ? 56 : LEFT;
  const plotWidth = Math.max(width - left - RIGHT, 100);
  const duration = Math.max(p.durationUs, 1);
  const x = (t: number) => left + Math.min(1, Math.max(0, t / duration)) * plotWidth;

  const axis = useMemo(
    () => priceAxis(p.trades.map((t) => t.price), p.referencePrice),
    [p.trades, p.trades.length, p.referencePrice],
  );
  const y = (price: number) => TOP + (PRICE_BOTTOM - TOP) * (1 - (price - axis.low) / (axis.high - axis.low));

  const cut = tradesUpTo(p.trades, p.nowUs);
  const past = p.trades.slice(0, cut);
  const future = p.trades.slice(Math.max(cut - 1, 0));
  const toPoints = (list: TradePoint[]) => list.map((t) => `${x(t.t).toFixed(1)},${y(t.price).toFixed(1)}`).join(" ");
  const high = extremes(p.trades, cut);

  const bars = useMemo(() => volumeSlices(p.trades, duration, SLICES), [p.trades, p.trades.length, duration]);
  const tallest = Math.max(1, ...bars);
  const barWidth = plotWidth / SLICES;

  const baseTick = duration > 20 * 60_000_000 ? 300_000_000 : 60_000_000;
  const tickEvery = baseTick * Math.max(1, Math.ceil(64 / ((plotWidth * baseTick) / duration)));
  const ticks: number[] = [];
  for (let t = 0; t <= duration; t += tickEvery) ticks.push(t);

  const now = past.length > 0 ? past[past.length - 1] : null;
  const cursorX = x(p.nowUs);
  const pillLeft = cursorX > width - 150;
  const playing = p.status === "playing";
  const canPause = p.status === "playing" || p.status === "paused";
  const showOpening = p.state.openingPrice !== null && p.nowUs >= p.preOpenUs;

  const caption =
    p.state.session === "CLOSED" && p.state.eventsApplied === 0
      ? "Waiting for the day to start."
      : now === null
        ? `${dayClock(p.nowUs)} into the day. Nothing has traded yet, because the market is still collecting orders before it opens.`
        : `${dayClock(p.nowUs)} into the day, the latest trade was at ${rupees(now.price)}: ${changeWords(
            now.price,
            p.referencePrice,
          ).toLowerCase()} from yesterday's close. So far ${p.state.trades.toLocaleString("en-IN")} trades, ${p.state.volume.toLocaleString("en-IN")} shares changed hands.`;

  return (
    <section className={`${p.practice ? "panel" : "card"} chart`} aria-labelledby="chart-title">
      <div className="chart-head">
        {p.practice ? (
          <h2 id="chart-title" className="chart-title">
            {p.symbol} through the day
            <span className="clock"> {clock(p.nowUs)} of {clock(duration)} · {p.state.trades.toLocaleString("en-IN")} trades</span>
          </h2>
        ) : (
          <div>
            <h2 id="chart-title">Price of {p.symbol} through the day</h2>
            <p className="muted lead">
              Every point on the line is a trade between one buyer and one seller. Press play to watch the day unfold, or
              drag along the chart to look at any moment.
            </p>
          </div>
        )}
        <div className="controls">
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
            {p.speed}×
          </button>
          {!p.practice && (
            <button className="btn" onClick={p.onAuction}>
              Jump to the opening
            </button>
          )}
          {!p.practice && (
            <button className="btn" onClick={p.onBiggest} disabled={!p.biggest}>
              Jump to the biggest move
            </button>
          )}
          {!p.practice && p.status === "done" && p.following && (
            <button className="btn primary" onClick={p.onReplay}>
              Watch this day again
            </button>
          )}
          {!p.practice && !p.following && (
            <button className="btn primary" onClick={p.onLive}>
              Back to the latest
            </button>
          )}
        </div>
      </div>

      <dl className="chart-stats" aria-label="Open, high and low so far">
        <div>
          <dt>Open</dt>
          <dd>{p.state.openingPrice === null || p.nowUs < p.preOpenUs ? "–" : rupees(p.state.openingPrice)}</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>{p.state.high === null ? "–" : rupees(p.state.high)}</dd>
        </div>
        <div>
          <dt>Low</dt>
          <dd>{p.state.low === null ? "–" : rupees(p.state.low)}</dd>
        </div>
        <div>
          <dt>Close, yesterday</dt>
          <dd>{rupees(p.referencePrice)}</dd>
        </div>
      </dl>

      <div className="chartbox" ref={box} style={{ height: HEIGHT }}>
        <svg
          role="img"
          aria-label={`Price chart. ${caption}`}
          width={width}
          height={HEIGHT}
        >
          {/* the part of the day before trading starts */}
          <rect x={left} y={TOP} width={x(p.preOpenUs) - left} height={VOLUME_BOTTOM - TOP} fill="var(--shade)" />
          {!narrow && (
            <text x={left + 8} y={TOP + 18} className="tick" style={{ paintOrder: "stroke", stroke: "var(--shade)", strokeWidth: 5 }}>
              Pre-open
            </text>
          )}

          {/* price grid and labels */}
          {axis.ticks.map((tick) => (
            <g key={tick}>
              <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="var(--row-line)" />
              <text x={left - 8} y={y(tick) + 4} textAnchor="end" className="tick">
                {axisLabel(tick)}
              </text>
            </g>
          ))}

          {/* yesterday's close */}
          <line
            x1={left}
            x2={left + plotWidth}
            y1={y(p.referencePrice)}
            y2={y(p.referencePrice)}
            stroke="var(--muted)"
            strokeWidth={1.5}
            strokeDasharray="6 4"
          />
          {cursorX < left + plotWidth - 200 && (
            <text x={left + plotWidth - 4} y={y(p.referencePrice) - 6} textAnchor="end" className="tick">
              Yesterday's close {rupees(p.referencePrice)}
            </text>
          )}

          {/* the opening auction */}
          <line x1={x(p.preOpenUs)} x2={x(p.preOpenUs)} y1={TOP} y2={VOLUME_BOTTOM} stroke="var(--ink)" strokeWidth={1.5} strokeDasharray="4 3" />
          {showOpening && p.state.openingPrice !== null && (
            <>
              <circle cx={x(p.preOpenUs)} cy={y(p.state.openingPrice)} r={5} fill="var(--ink)" />
            </>
          )}

          {/* the price line: solid up to the moment on screen, faint after it */}
          {future.length > 1 && <polyline fill="none" stroke="var(--line)" strokeWidth={2} points={toPoints(future)} />}
          {past.length > 1 && <polyline fill="none" stroke="var(--ink)" strokeWidth={2.5} strokeLinejoin="round" points={toPoints(past)} />}

          {/* the biggest move */}
          {p.biggest && (
            <g>
              <circle cx={x(p.biggest.to.t)} cy={y(p.biggest.to.price)} r={5} fill="var(--sell)" stroke="var(--ink)" />
            </g>
          )}

          {/* highest and lowest so far */}
          {high && high.high.price !== high.low.price && (
            <>
              <circle cx={x(high.high.t)} cy={y(high.high.price)} r={4} fill="var(--surface)" stroke="var(--ink)" strokeWidth={2} />
              <circle cx={x(high.low.t)} cy={y(high.low.price)} r={4} fill="var(--surface)" stroke="var(--ink)" strokeWidth={2} />
            </>
          )}

          {/* shares traded */}
          {!narrow && (
            <>
              <text x={left - 8} y={VOLUME_TOP + 14} textAnchor="end" className="tick">
                Shares
              </text>
              <text x={left - 8} y={VOLUME_TOP + 30} textAnchor="end" className="tick">
                traded
              </text>
            </>
          )}
          {bars.map((value, i) => {
            const barHeight = (value / tallest) * (VOLUME_BOTTOM - VOLUME_TOP);
            const slicePast = ((i + 1) * duration) / SLICES <= p.nowUs;
            return (
              <rect
                key={i}
                x={left + i * barWidth + 1}
                y={VOLUME_BOTTOM - barHeight}
                width={Math.max(barWidth - 2, 1)}
                height={barHeight}
                fill={slicePast ? "var(--buy)" : "var(--line)"}
              />
            );
          })}
          <line x1={left} x2={left + plotWidth} y1={VOLUME_BOTTOM} y2={VOLUME_BOTTOM} stroke="var(--ink)" />

          {/* time axis */}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={VOLUME_BOTTOM} y2={VOLUME_BOTTOM + 6} stroke="var(--muted)" />
              <text x={Math.min(x(t), left + plotWidth - 14)} y={VOLUME_BOTTOM + 22} textAnchor="middle" className="tick">
                {Math.round(t / 60_000_000)}{narrow ? "" : " min"}
              </text>
            </g>
          ))}

          {/* the moment on screen */}
          <line x1={cursorX} x2={cursorX} y1={TOP} y2={VOLUME_BOTTOM} stroke="var(--buy)" strokeWidth={3} />
          {now && (
            <>
              <circle cx={cursorX} cy={y(now.price)} r={7} fill="var(--you)" stroke="var(--ink)" strokeWidth={2} />
              <g transform={`translate(${pillLeft ? cursorX - 14 : cursorX + 14}, ${y(now.price)})`}>
                <rect x={pillLeft ? -92 : 0} y={-14} width={92} height={28} rx={14} fill="var(--ink)" />
                <text x={pillLeft ? -46 : 46} y={5} textAnchor="middle" fill="var(--surface)" fontWeight={700} fontSize={14}>
                  {rupees(now.price)}
                </text>
              </g>
            </>
          )}
        </svg>
        {!p.practice && (
        <input
          type="range"
          className="slider"
          style={{ left: left, width: plotWidth }}
          min={0}
          max={duration}
          step={1000}
          value={Math.min(p.nowUs, duration)}
          onChange={(e) => p.onSeek(Number(e.target.value))}
          aria-label="Move through the day"
          aria-valuetext={`${dayClock(p.nowUs)} into the day`}
        />
        )}
      </div>
      {p.practice ? (
        <p className="sr-only" aria-live="off">
          {caption}
        </p>
      ) : (
        <p className="caption" aria-live="polite">
          {caption}
        </p>
      )}
    </section>
  );
}
