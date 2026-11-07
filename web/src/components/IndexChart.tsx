import { useMemo, useRef } from "react";
import { clock, percentSigned, points, pointsSigned } from "../lib/format";
import { Point, priceAxis } from "../lib/series";
import { useWidth } from "../lib/useWidth";
import { IndexKind, INDEX_KINDS } from "../lib/world";
import { INDEX_TEXT } from "../lib/worldview";

interface Props {
  name: string; // "Shifty 12"
  kind: IndexKind;
  onKind: (kind: IndexKind) => void;
  line: Point[]; // the level after each trade, in hundredths of a point
  open: number; // where the index started the day (yesterday's close), hundredths
  level: number; // where it is now, hundredths (exact, from the server)
  nowUs: number;
  durationUs: number;
  preOpenUs: number;
  news: { at: number; silent: boolean; headline: string }[];
}

const HEIGHT = 230;
const LEFT = 72;
const RIGHT = 16;
const TOP = 14;
const BOTTOM = 192;

/** The whole market at a glance: the index through the day, drawn like a company's price. */
export function IndexChart({ name, kind, onKind, line, open, level, nowUs, durationUs, preOpenUs, news }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box);
  const narrow = width < 600;
  const left = narrow ? 56 : LEFT;
  const plotWidth = Math.max(width - left - RIGHT, 100);
  const duration = Math.max(durationUs, 1);
  const x = (t: number) => left + Math.min(1, Math.max(0, t / duration)) * plotWidth;

  const axis = useMemo(() => priceAxis(line.map((p) => p.price), open), [line, line.length, open]);
  const y = (value: number) => TOP + (BOTTOM - TOP) * (1 - (value - axis.low) / (axis.high - axis.low));
  const path = line.map((p) => `${x(p.t).toFixed(1)},${y(p.price).toFixed(1)}`).join(" ");
  const last = line.length > 0 ? line[line.length - 1] : null;

  const ticks: { t: number; label: string }[] = [{ t: preOpenUs, label: "9:15" }];
  for (let hour = 10; hour <= 15; hour += narrow ? 2 : 1) {
    ticks.push({ t: preOpenUs + ((hour * 60 - 555) / 375) * (duration - preOpenUs), label: `${hour}:00` });
  }
  ticks.push({ t: duration, label: "15:30" });

  const change = level - open;
  const direction = change === 0 ? "flat" : change > 0 ? "up" : "down";
  const cursorX = x(nowUs);
  const axisLabel = (hundredths: number) => (hundredths % 100 === 0 ? points(hundredths).slice(0, -3) : points(hundredths));
  const caption =
    last === null
      ? `${name} has not moved yet. It opens at ${points(open)}, yesterday's close.`
      : `${name} at ${clock(nowUs, preOpenUs, duration)} is ${points(level)}, ${
          change === 0 ? "unchanged" : `${pointsSigned(change)} points (${percentSigned(change, open)})`
        } from yesterday's close of ${points(open)}.`;

  return (
    <section className="panel chart index-chart" aria-labelledby="index-chart-title">
      <div className="chart-head">
        <h2 id="index-chart-title" className="chart-title">
          {name} through the day
          <span className="clock">
            {" "}
            {points(level)} <span className={`change ${direction}`}>{change === 0 ? "unchanged" : `${direction === "up" ? "▲" : "▼"} ${pointsSigned(change)} (${percentSigned(change, open)})`}</span>
          </span>
        </h2>
        <div className="seg quiet" role="group" aria-label="How the index is worked out">
          {INDEX_KINDS.map((k) => (
            <button key={k} type="button" className={k === kind ? "on" : ""} aria-pressed={k === kind} onClick={() => onKind(k)}>
              {INDEX_TEXT[k].name}
            </button>
          ))}
        </div>
      </div>
      <div className="chartbox" ref={box} style={{ height: HEIGHT }}>
        <svg role="img" aria-label={`Index chart. ${caption}`} width={width} height={HEIGHT}>
          {news.map((n, i) => (
            <g key={i} className={`news-mark${n.silent ? " silent" : ""}`}>
              <title>{n.headline}</title>
              <line x1={x(n.at)} x2={x(n.at)} y1={TOP + 18} y2={BOTTOM} strokeDasharray="2 4" />
              <path d={`M${x(n.at)} ${TOP + 3} l6 8 l-6 8 l-6 -8 z`} />
            </g>
          ))}
          <rect x={left} y={TOP} width={x(preOpenUs) - left} height={BOTTOM - TOP} fill="var(--shade)" />
          {axis.ticks.map((tick) => (
            <g key={tick}>
              <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="var(--row-line)" />
              <text x={left - 8} y={y(tick) + 4} textAnchor="end" className="tick">
                {axisLabel(tick)}
              </text>
            </g>
          ))}
          <line x1={left} x2={left + plotWidth} y1={y(open)} y2={y(open)} stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="6 4" />
          {cursorX < left + plotWidth - 220 && (
            <text x={left + plotWidth - 4} y={y(open) - 6} textAnchor="end" className="tick">
              Yesterday's close {points(open)}
            </text>
          )}
          <line x1={x(preOpenUs)} x2={x(preOpenUs)} y1={TOP} y2={BOTTOM} stroke="var(--ink)" strokeWidth={1.5} strokeDasharray="4 3" />
          {line.length > 1 && (
            <>
              <defs>
                <linearGradient id="index-area" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--price-line)" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="var(--price-line)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <polygon fill="url(#index-area)" points={`${x(line[0].t).toFixed(1)},${BOTTOM} ${path} ${x(line[line.length - 1].t).toFixed(1)},${BOTTOM}`} />
              <polyline fill="none" stroke="var(--price-line)" strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" points={path} />
            </>
          )}
          <line x1={left} x2={left + plotWidth} y1={BOTTOM} y2={BOTTOM} stroke="var(--ink)" />
          {ticks.map(({ t, label }) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={BOTTOM} y2={BOTTOM + 6} stroke="var(--muted)" />
              <text x={Math.min(x(t), left + plotWidth - 14)} y={BOTTOM + 22} textAnchor="middle" className="tick">
                {label}
              </text>
            </g>
          ))}
          <line x1={cursorX} x2={cursorX} y1={TOP} y2={BOTTOM} stroke="var(--buy)" strokeWidth={3} />
          {last && <circle cx={cursorX} cy={y(last.price)} r={6} fill="var(--you)" stroke="var(--ink)" strokeWidth={2} />}
        </svg>
      </div>
      <p className="sr-only" aria-live="off">
        {caption}
      </p>
    </section>
  );
}
