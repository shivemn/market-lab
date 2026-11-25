import { useEffect, useMemo, useRef, useState } from "react";
import { buildFlow, project, type FlowNode } from "../lib/flow";
import type { MarketEvent } from "../lib/market";
import { Panel } from "../ui";
import { useFrameClock } from "../ui/motion";

interface Props {
  events: readonly MarketEvent[];
  version: number;
  symbol: string;
  owner: string;
  /** Only turn and send dots while the day is moving. */
  playing: boolean;
}

const TRAVEL_MS = 1100;
const MAX_DOTS = 40;
const LABELLED = new Set(["mm", "value", "you"]);

const circle = (x: number, y: number, r: number) => `M${(x - r).toFixed(1)} ${y.toFixed(1)}a${r.toFixed(1)} ${r.toFixed(1)} 0 1 0 ${(2 * r).toFixed(1)} 0a${r.toFixed(1)} ${r.toFixed(1)} 0 1 0 ${(-2 * r).toFixed(1)} 0Z`;
const radius = (n: FlowNode, s: number) => (3.5 + Math.sqrt(n.shares) * 0.42) * s;
const band = (z: number) => (z > 110 ? 0 : z > -110 ? 1 : 2);

/**
 * Who traded with whom in one company, in 3D. Market makers sit in the middle, value traders around them, casual
 * traders outside. The network turns slowly to show depth, and every new trade sends a dot from the seller to the buyer.
 */
export function FlowNetwork({ events, version, symbol, owner, playing }: Props) {
  const flow = useMemo(() => buildFlow(events, owner), [version, symbol, owner]); // eslint-disable-line react-hooks/exhaustive-deps
  const [paused, setPaused] = useState(false);
  const { elapsed, still } = useFrameClock(playing && !paused && flow.nodes.length > 0, symbol);
  // dots: only for trades that arrive while this panel is on screen, never for the day's history
  const seen = useRef<{ symbol: string; seq: number; started: Map<number, number> }>({ symbol: "", seq: Number.MAX_SAFE_INTEGER, started: new Map() });
  const lastSeq = flow.trades.length > 0 ? flow.trades[flow.trades.length - 1].seq : 0;
  if (seen.current.symbol !== symbol) seen.current = { symbol, seq: lastSeq, started: new Map() };
  useEffect(() => {
    const s = seen.current;
    for (const t of flow.trades) if (t.seq > s.seq && !s.started.has(t.seq)) s.started.set(t.seq, elapsed);
    s.seq = Math.max(s.seq, lastSeq);
    if (s.started.size > MAX_DOTS) for (const key of [...s.started.keys()].slice(0, s.started.size - MAX_DOTS)) s.started.delete(key);
  }, [lastSeq]); // eslint-disable-line react-hooks/exhaustive-deps

  const angle = still ? 0.6 : 0.6 + elapsed * 0.00016;
  const P = flow.nodes.map((n) => project(n.p, angle));
  const bands = [0, 1, 2].map(() => ({ light: "", heavy: "", mine: "", noise: "", value: "", mm: "", you: "", other: "" }));
  const heavyFrom = Math.max(30, ...flow.edges.map((e) => e.shares)) * 0.5;
  for (const e of flow.edges) {
    const a = P[e.a];
    const b = P[e.b];
    const seg = `M${a.x.toFixed(1)} ${a.y.toFixed(1)}L${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
    const bd = bands[band((a.z + b.z) / 2)];
    if (e.mine) bd.mine += seg;
    else if (e.shares >= heavyFrom) bd.heavy += seg;
    else bd.light += seg;
  }
  flow.nodes.forEach((n, i) => {
    bands[band(P[i].z)][n.kind] += circle(P[i].x, P[i].y, radius(n, P[i].s));
  });
  let dots = "";
  let myDots = "";
  const byseq = new Map(flow.trades.map((t) => [t.seq, t]));
  for (const [seqNo, start] of seen.current.started) {
    const f = (elapsed - start) / TRAVEL_MS;
    if (f < 0 || f > 1 || still) continue;
    const t = byseq.get(seqNo);
    if (!t) continue;
    const g = f * f * (3 - 2 * f);
    const A = flow.nodes[t.from].p;
    const B = flow.nodes[t.to].p;
    const p = project([A[0] + (B[0] - A[0]) * g, A[1] + (B[1] - A[1]) * g, A[2] + (B[2] - A[2]) * g], angle);
    if (t.mine) myDots += circle(p.x, p.y, 4 * p.s);
    else dots += circle(p.x, p.y, 2.4 * p.s);
  }
  const mineCount = flow.trades.filter((t) => t.mine).length;
  const counts = { mm: 0, value: 0, noise: 0 };
  for (const n of flow.nodes) if (n.kind in counts) counts[n.kind as keyof typeof counts] += 1;
  const label =
    flow.nodes.length === 0
      ? `No trades in ${symbol} yet.`
      : `Network of the ${flow.nodes.length} traders in ${symbol}: ${counts.mm} market makers in the middle trade with almost everyone, ${counts.value} value traders and ${counts.noise} casual traders around them.${mineCount > 0 ? ` You traded ${mineCount} times.` : ""}`;
  return (
    <Panel
      id="flow-title"
      className="flow-panel"
      title={`Who trades with whom in ${symbol}`}
      meta={
        <span className="paths-controls">
          <span className="eq-meta">
            {flow.nodes.length} traders · {flow.trades.length.toLocaleString("en-IN")} trades
          </span>
          {!still && (
            <button className="chip-btn" type="button" aria-pressed={paused} onClick={() => setPaused((p) => !p)}>
              {paused ? "Turn" : "Hold still"}
            </button>
          )}
        </span>
      }
    >
      <ul className="flow-key">
        <li><i className="k-mm" /> Market makers</li>
        <li><i className="k-value" /> Value traders</li>
        <li><i className="k-noise" /> Casual traders</li>
        {owner !== "" && <li><i className="k-you" /> You</li>}
      </ul>
      {flow.nodes.length === 0 ? (
        <p className="muted small">No trades yet. Once the market opens, every trader who buys or sells appears here.</p>
      ) : (
        <div className="flow-box">
          <svg viewBox="0 0 1000 310" role="img" aria-label={label}>
            {bands.map((b, i) => (
              <g key={i} opacity={[0.32, 0.66, 1][i]}>
                <path className="f-light" d={b.light} />
                <path className="f-heavy" d={b.heavy} />
                <path className="f-mine" d={b.mine} />
                <path className="f-noise" d={b.noise} />
                <path className="f-other" d={b.other} />
                <path className="f-value" d={b.value} />
                <path className="f-mm" d={b.mm} />
                <path className="f-you" d={b.you} />
              </g>
            ))}
            <path className="f-dot" d={dots} />
            <path className="f-mydot" d={myDots} />
            {flow.nodes.map((n, i) =>
              LABELLED.has(n.kind) ? (
                <text key={n.id} className={`tick f-label${n.kind === "you" ? " you" : ""}`} x={P[i].x} y={P[i].y + radius(n, P[i].s) + 12} textAnchor="middle" opacity={[0.45, 0.8, 1][band(P[i].z)]}>
                  {n.kind === "you" ? "you" : n.id}
                </text>
              ) : null,
            )}
          </svg>
        </div>
      )}
      <p className="muted small">
        A line is shares that changed hands between two traders; the darker lines carry the most. While the day runs, each
        new trade travels as a dot from the seller to the buyer{owner !== "" ? ", and yours are orange" : ""}. The turning
        only shows depth.
      </p>
    </Panel>
  );
}
