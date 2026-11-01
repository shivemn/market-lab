import { useMemo, useRef } from "react";
import { AuctionOrder, auctionReport, AuctionReport, Instrument } from "../lib/auction";
import { rupees } from "../lib/format";
import type { MarketEvent } from "../lib/market";
import { who } from "../lib/narrate";
import { useWidth } from "../lib/useWidth";

interface Props {
  events: readonly MarketEvent[];
  version: number;
  instrument: Instrument | null;
  onBack: () => void;
}

export function AuctionView({ events, version, instrument, onBack }: Props) {
  const report = useMemo(
    () => (instrument ? auctionReport(events, instrument) : null),
    // `events` is one growing array, so `version` is what says it changed
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version, instrument],
  );
  if (!instrument || !report) {
    return (
      <section className="card">
        <h2>The opening auction has not happened yet</h2>
        <p className="muted lead">
          Before the market opens, everyone's orders are collected and nothing trades. At the opening, the exchange picks
          one price for all of them. In this simulated day that is one minute in.
        </p>
        <div>
          <button className="btn primary" onClick={onBack}>
            Go back to the day
          </button>
        </div>
      </section>
    );
  }
  return (
    <div className="auction">
      <Explainer report={report} instrument={instrument} />
      <div className="auction-right">
        <CurveChart report={report} instrument={instrument} />
        <WhoGotWhat report={report} />
      </div>
    </div>
  );
}

function Explainer({ report, instrument }: { report: AuctionReport; instrument: Instrument }) {
  const live = report.orders.filter((o) => !o.cancelledBefore);
  const buys = live.filter((o) => o.side === "BUY");
  const sells = live.filter((o) => o.side === "SELL");
  const sum = (list: AuctionOrder[]) => list.reduce((n, o) => n + o.quantity, 0);
  const traded = report.price !== null;
  return (
    <section className="card explainer" aria-labelledby="why-title">
      <h2 id="why-title" className="big-title">
        {traded ? `Why the day opens at ${rupees(report.price as number)}` : "Why the day opens at yesterday's close"}
      </h2>
      <p className="muted lead">
        Before the market opens, everyone's orders are collected and nothing trades. Then the exchange picks one price and
        settles everything at once.
      </p>
      <ol className="steps">
        <li>
          <b>Count the buyers and sellers.</b> {buys.length} orders wanted to buy {sum(buys).toLocaleString("en-IN")} shares.{" "}
          {sells.length} orders offered {sum(sells).toLocaleString("en-IN")} shares.
        </li>
        <li>
          <b>Work out, at every price, how many shares could trade.</b> Cheaper prices attract more buyers. Dearer prices
          attract more sellers. The most that can trade is the smaller of the two.
        </li>
        {traded ? (
          <li>
            <b>Pick the price where the most shares can trade.</b> At {rupees(report.price as number)}, {report.volume} shares
            change hands.
            {report.tiedPrices > 1 &&
              ` ${report.tiedPrices} prices allow that many, so the exchange takes the one that leaves the fewest shares unsold, then the one closest to yesterday's close of ${rupees(instrument.reference_price)}.`}
          </li>
        ) : (
          <li>
            <b>No price works.</b> Nobody who wanted to buy would pay what the sellers asked, so nothing trades and the day
            opens at yesterday's close.
          </li>
        )}
        {traded && (
          <li>
            <b>Everyone trades at that one price.</b> A buyer who was ready to pay more still pays{" "}
            {rupees(report.price as number)}. A seller who asked for less still gets it.
          </li>
        )}
      </ol>
      {traded && (report.unmatchedBuy > 0 || report.unmatchedSell > 0) && (
        <p className="callout">
          {report.unmatchedSell > 0 && `${report.unmatchedSell} shares of sell orders were left over. `}
          {report.unmatchedBuy > 0 && `${report.unmatchedBuy} shares of buy orders were left over. `}
          They stay in the queue when the market opens, if the order allows it.
        </p>
      )}
    </section>
  );
}

const HEIGHT = 380;
const LEFT = 64;
const RIGHT = 24;
const TOP = 20;
const BOTTOM = 50;

function niceTicks(low: number, high: number): number[] {
  const steps = [5, 10, 25, 50, 100, 200, 500, 1000];
  const wanted = (high - low) / 6;
  const step = steps.find((s) => s >= wanted) ?? 1000;
  const ticks: number[] = [];
  for (let v = Math.ceil(low / step) * step; v <= high; v += step) ticks.push(v);
  return ticks;
}

function CurveChart({ report, instrument }: { report: AuctionReport; instrument: Instrument }) {
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box);
  const plotWidth = Math.max(width - LEFT - RIGHT, 100);
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const prices = report.curve.map((c) => c.price);
  const low0 = Math.min(...prices, instrument.reference_price);
  const high0 = Math.max(...prices, instrument.reference_price);
  const pad = Math.max((high0 - low0) * 0.1, instrument.tick_size * 4);
  // Zoom in on the interesting part: within about ₹2 of the answer (or of yesterday's close when nothing traded).
  const centre = report.price ?? instrument.reference_price;
  const low = Math.max(low0 - pad, centre - 200);
  const high = Math.min(high0 + pad, centre + 200);
  const top = Math.max(1, ...report.curve.map((c) => Math.max(c.buy, c.sell))) * 1.12;
  const x = (price: number) => LEFT + ((price - low) / (high - low)) * plotWidth;
  const y = (shares: number) => TOP + plotHeight * (1 - shares / top);
  const curve = report.curve;
  const first = curve[0];
  const last = curve[curve.length - 1];
  const edge = (pick: (c: (typeof curve)[number]) => number) =>
    [`${x(low)},${y(pick(first))}`, ...curve.map((c) => `${x(c.price)},${y(pick(c))}`), `${x(high)},${y(pick(last))}`].join(" ");
  const area = `${x(low)},${y(0)} ${edge((c) => c.volume)} ${x(high)},${y(0)}`;
  const shareTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round((top / 1.12) * f));
  const eqX = report.price === null ? null : x(report.price);
  const refX = x(instrument.reference_price);
  const labelLeft = eqX !== null && eqX > LEFT + plotWidth * 0.62;

  return (
    <section className="card" aria-labelledby="curve-title">
      <h2 id="curve-title">Shares that buyers and sellers would trade, at each price</h2>
      <div ref={box} style={{ width: "100%" }}>
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={
            report.price === null
              ? "Chart of buyers and sellers at each price. The lines never overlap, so nothing trades."
              : `Chart of buyers and sellers at each price. The most shares that can trade, ${report.volume}, is at ${rupees(report.price)}.`
          }
        >
          {shareTicks.map((t) => (
            <g key={t}>
              <line x1={LEFT} x2={LEFT + plotWidth} y1={y(t)} y2={y(t)} stroke="var(--row-line)" />
              <text x={LEFT - 8} y={y(t) + 4} textAnchor="end" className="tick">
                {t}
              </text>
            </g>
          ))}
          <text x={LEFT - 8} y={12} textAnchor="end" className="tick strong">
            Shares
          </text>
          <clipPath id="plot-clip">
            <rect x={LEFT} y={TOP} width={plotWidth} height={plotHeight} />
          </clipPath>
          <g clipPath="url(#plot-clip)">
            <polygon points={area} fill="var(--trade-fill)" />
          <polyline points={edge((c) => c.buy)} fill="none" stroke="var(--buy)" strokeWidth={3.5} strokeLinejoin="round" />
          <polyline points={edge((c) => c.sell)} fill="none" stroke="var(--sell)" strokeWidth={3.5} strokeLinejoin="round" />
          </g>
          <line x1={LEFT} x2={LEFT + plotWidth} y1={y(0)} y2={y(0)} stroke="var(--ink)" />
          {niceTicks(low, high).map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(0) + 6} stroke="var(--muted)" />
              <text x={x(t)} y={y(0) + 22} textAnchor="middle" className="tick">
                {rupees(t)}
              </text>
            </g>
          ))}
          <text x={LEFT + plotWidth} y={HEIGHT - 6} textAnchor="end" className="tick strong">
            Price
          </text>

          <line x1={refX} x2={refX} y1={TOP} y2={y(0)} stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="3 4" />
          {eqX !== null && report.price !== null && (
            <>
              <line x1={eqX} x2={eqX} y1={TOP} y2={y(0)} stroke="var(--ink)" strokeWidth={2} strokeDasharray="6 4" />
              <circle cx={eqX} cy={y(report.volume)} r={8} fill="var(--you)" stroke="var(--ink)" strokeWidth={2.5} />
              <text
                x={labelLeft ? eqX - 14 : eqX + 14}
                y={y(report.volume) - 14}
                textAnchor={labelLeft ? "end" : "start"}
                className="tick strong big"
              >
                {report.volume} shares trade at {rupees(report.price)}
              </text>
            </>
          )}
          <text
            x={eqX !== null && Math.abs(refX - eqX) < 130 && refX <= eqX ? refX - 6 : refX + 6}
            textAnchor={eqX !== null && Math.abs(refX - eqX) < 130 && refX <= eqX ? "end" : "start"}
            y={TOP + 12}
            className="tick"
          >
            Yesterday's close
          </text>
          <text x={LEFT + 8} y={y(first.buy) - 10} className="tick buy-text">
            Buyers
          </text>
          <text x={LEFT + plotWidth - 8} y={y(last.sell) - 10} textAnchor="end" className="tick sell">
            Sellers
          </text>
        </svg>
      </div>
      <p className="muted small legend">
        <span className="swatch" style={{ background: "var(--buy)" }} /> Buyers: shares they would buy at this price (cheaper
        means more). <span className="swatch" style={{ background: "var(--sell)" }} /> Sellers: shares they would sell at this
        price (dearer means more). <span className="swatch" style={{ background: "var(--trade-fill)" }} /> The most that could
        trade.
      </p>
    </section>
  );
}

function describeAsk(o: AuctionOrder): string {
  const verb = o.side === "BUY" ? "Buy" : "Sell";
  if (o.limitPrice === null) return `${verb} ${o.quantity} at any price`;
  return `${verb} ${o.quantity}, ${o.side === "BUY" ? "paying up to" : "asking at least"} ${rupees(o.limitPrice)}`;
}

function describeResult(o: AuctionOrder, price: number | null): string {
  const verb = o.side === "BUY" ? "Bought" : "Sold";
  if (o.cancelledBefore) return "Cancelled before the auction ran";
  if (o.filled === 0) {
    if (price === null || o.limitPrice === null) return "No trade";
    const reason =
      o.side === "BUY" ? (o.limitPrice < price ? "their price was too low" : "") : o.limitPrice > price ? "their price was too high" : "";
    return `No trade${reason ? `: ${reason}` : ""}${o.stays ? ". Still waiting in the queue" : ""}`;
  }
  const where = `${verb} ${o.filled} at ${rupees(o.paid)}`;
  let extra = "";
  if (o.limitPrice !== null && o.limitPrice !== o.paid) {
    const gain = Math.abs(o.limitPrice - o.paid) * o.filled;
    extra =
      o.side === "BUY"
        ? `, saving ${rupees(gain)} compared with the most they were ready to pay`
        : `, earning ${rupees(gain)} more than the least they would accept`;
  }
  const partial = o.filled < o.quantity ? `. The other ${o.quantity - o.filled} ${o.stays ? "are still waiting in the queue" : "were cancelled"}` : "";
  return where + extra + partial;
}

const ROWS = 12;

function WhoGotWhat({ report }: { report: AuctionReport }) {
  // Market makers cancel and replace their quotes constantly, so most orders never reach the auction. Show the ones that did.
  const live = report.orders.filter((o) => !o.cancelledBefore);
  const cancelled = report.orders.length - live.length;
  const rows = [...live].sort((a, b) => b.filled - a.filled || b.quantity - a.quantity).slice(0, ROWS);
  const more = live.length - rows.length;
  return (
    <section className="card" aria-labelledby="who-title">
      <h2 id="who-title">Who got what</h2>
      <table className="who">
        <thead>
          <tr>
            <th scope="col">Trader</th>
            <th scope="col">What they asked for</th>
            <th scope="col">What happened</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id}>
              <th scope="row" className={o.side === "BUY" ? "buy-text" : "sell"}>
                {who(o.account)} <span className="muted small">({o.account})</span>
              </th>
              <td>{describeAsk(o)}</td>
              <td>{describeResult(o, report.price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        {more > 0 && `${rows.length} of the ${live.length} orders that reached the auction are shown, the ones that traded most first. `}
        {cancelled > 0 &&
          `${cancelled} more orders were cancelled before the auction ran. Market makers keep cancelling and re-posting their prices all the time.`}
      </p>
    </section>
  );
}
