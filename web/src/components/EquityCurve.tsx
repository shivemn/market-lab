import { useRef } from "react";
import { equityExtremes, worthAt, type EquityPoint } from "../lib/equity";
import { clock, rupees, signed } from "../lib/format";
import { useWidth } from "../lib/useWidth";
import { Panel } from "../ui";

interface Props {
  series: readonly EquityPoint[];
  /** What the account was worth when the day began. */
  start: number;
  openAt: number;
  closeAt: number;
  /** Moments when one of your orders traded. */
  fills: readonly number[];
}

const H = 170;
const TOP = 14;
const BOTTOM = 26;

/** Your account's worth through the day, drawn from the server's own figure at every step, so it ends on "Worth now". */
export function EquityCurve({ series, start, openAt, closeAt, fills }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box, 600);
  const last = series[series.length - 1];
  const ext = equityExtremes(series);
  const values = series.map((p) => p.worth).concat(start);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const room = Math.max((hi - lo) * 0.18, 5_000); // at least ₹50 of room, so a flat line does not hug the edge
  lo -= room;
  hi += room;
  const left = 4;
  const right = 4;
  const x = (t: number) => left + (Math.max(0, Math.min(t, closeAt)) / closeAt) * (width - left - right);
  const y = (w: number) => TOP + ((hi - w) / (hi - lo)) * (H - TOP - BOTTOM);
  const line = series.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.worth).toFixed(1)}`).join(" ");
  const base = y(start);
  const area = last ? `${line} L${x(last.t).toFixed(1)} ${base.toFixed(1)} L${x(series[0].t).toFixed(1)} ${base.toFixed(1)} Z` : "";
  const dir = !last || last.worth === start ? "flat" : last.worth > start ? "up" : "down";
  const shown = fills.filter((t) => last && t <= last.t);
  const label = last
    ? `Your account from 9:00 to ${clock(last.t, openAt, closeAt)}: started at ${rupees(start)}, now ${rupees(last.worth)}` +
      (ext ? `, lowest ${rupees(ext.low.worth)}, highest ${rupees(ext.high.worth)}` : "") +
      `, ${shown.length} ${shown.length === 1 ? "fill" : "fills"}.`
    : "Your account through the day. Nothing yet.";
  return (
    <Panel
      id="equity-title"
      className="equity-panel"
      title="Your account through the day"
      meta={
        ext && series.length > 1 ? (
          <span className="eq-meta">
            low {rupees(ext.low.worth)} · high {rupees(ext.high.worth)}
          </span>
        ) : null
      }
    >
      <div className="eq-head">
        <span className="eq-now">{last ? rupees(last.worth) : rupees(start)}</span>
        <span className={`change ${dir}`}>{last ? `${signed(last.worth - start)} today` : "no change yet"}</span>
      </div>
      <div className="chartbox eq-box" ref={box}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={label}>
          <line className="eq-base" x1={left} x2={width - right} y1={base} y2={base} />
          {area && <path className={`eq-area ${dir}`} d={area} />}
          {series.length > 1 && <path className="eq-line" d={line} />}
          {shown.map((t, i) => {
            const w = worthAt(series, t);
            return w === null ? null : <circle key={`${t}-${i}`} className="eq-fill" cx={x(t)} cy={y(w)} r={3.5} />;
          })}
          {last && <circle className="eq-dot" cx={x(last.t)} cy={y(last.worth)} r={3} />}
          <text className="tick" x={left + 2} y={base - 6}>
            start {rupees(start)}
          </text>
          {x(openAt) - left >= 64 && (
            <text className="tick" x={left} y={H - 6}>
              9:00
            </text>
          )}
          <text className="tick" x={x(openAt)} y={H - 6} textAnchor="middle">
            9:15
          </text>
          <text className="tick" x={width - right} y={H - 6} textAnchor="end">
            15:30
          </text>
        </svg>
      </div>
      <p className="muted small eq-note">
        {series.length > 1
          ? "Each dot is one of your trades. Shares are valued at their last price, with charges already taken off."
          : "Press play and your worth is drawn here as the day runs, one point for every step."}
      </p>
    </Panel>
  );
}
