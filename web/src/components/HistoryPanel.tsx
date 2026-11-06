import { clock, money, rupees, signed } from "../lib/format";
import type { SavedDay } from "../lib/history";
import { percentSigned } from "../lib/format";

interface Props {
  days: SavedDay[] | null;
  failed: boolean;
  preOpenUs: number;
  closeUs: number;
}

const when = (stamp: string): string => {
  const date = new Date(stamp.replace(" ", "T") + "Z");
  return Number.isNaN(date.getTime())
    ? stamp
    : date.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
};

/** Your worth at the close of each day, oldest to newest. */
function WorthLine({ days }: { days: SavedDay[] }) {
  const ordered = [...days].reverse();
  const values = ordered.map((d) => d.end_worth);
  const low = Math.min(...values, ordered[0].start_worth);
  const high = Math.max(...values, ordered[0].start_worth);
  const W = 560;
  const H = 120;
  const pad = 12;
  const y = (v: number) => (high === low ? H / 2 : pad + (1 - (v - low) / (high - low)) * (H - 2 * pad));
  const x = (i: number) => (ordered.length === 1 ? W / 2 : pad + (i / (ordered.length - 1)) * (W - 2 * pad));
  const path = ordered.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(d.end_worth).toFixed(1)}`).join(" ");
  return (
    <figure className="worth-line">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Your worth after each of ${ordered.length} days, from ${rupees(ordered[0].start_worth)} to ${rupees(values[values.length - 1])}`}>
        <line x1={pad} x2={W - pad} y1={y(ordered[0].start_worth)} y2={y(ordered[0].start_worth)} stroke="var(--muted)" strokeDasharray="3 4" />
        <path d={path} fill="none" stroke="var(--buy)" strokeWidth={2} />
        {ordered.map((d, i) => (
          <circle key={d.id} cx={x(i)} cy={y(d.end_worth)} r={3.5} fill="var(--buy)">
            <title>{`${when(d.played_at)}: ${rupees(d.end_worth)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="muted small">Your worth at the close of each day. The dashed line is where you started.</figcaption>
    </figure>
  );
}

/** The numbers that add up over many days. */
function Totals({ days }: { days: SavedDay[] }) {
  const finished = days.filter((d) => d.finished);
  const trades = days.reduce((sum, d) => sum + d.fills.length, 0);
  const charges = days.reduce((sum, d) => sum + d.charges, 0);
  const rated = finished.filter((d) => d.index["cap"]);
  const ahead = rated.filter((d) => d.result / d.start_worth > d.index["cap"].change / d.index["cap"].open).length;
  const first = days[days.length - 1];
  const last = days[0];
  return (
    <dl className="totals">
      <div>
        <dt>Days played</dt>
        <dd>{days.length}</dd>
      </div>
      <div>
        <dt>Worth now</dt>
        <dd>{rupees(last.end_worth)}</dd>
        <small className="muted">{signed(last.end_worth - first.start_worth)} since you began</small>
      </div>
      <div>
        <dt>Days ahead of the index</dt>
        <dd>
          {ahead} of {rated.length}
        </dd>
      </div>
      <div>
        <dt>Trades</dt>
        <dd>{trades}</dd>
      </div>
      <div>
        <dt>Taxes and charges paid</dt>
        <dd>{rupees(charges)}</dd>
      </div>
    </dl>
  );
}

/** Every practice day that was played, with each trade, kept in the database so it is still here tomorrow. */
export function HistoryPanel({ days, failed, preOpenUs, closeUs }: Props) {
  if (failed) return <p className="muted small" role="alert">Your saved days could not be loaded. Is the server running?</p>;
  if (days === null) return <p className="muted small">Loading your saved days…</p>;
  if (days.length === 0) {
    return <p className="muted small">Nothing saved yet. Each day you play to the close, or leave after trading, is kept here with every trade you made.</p>;
  }
  return (
    <div className="history">
      <Totals days={days} />
      <WorthLine days={days} />
      <p className="muted small">
        Saved in the database file on this computer, so it is still here after you close the page or restart the server. Newest first.
      </p>
      {days.map((day) => {
        const index = day.index["cap"];
        return (
          <details key={day.id} className="past-day">
            <summary>
              <span className="pd-when">{when(day.played_at)}</span>
              <span>Day {day.seed}</span>
              <span className={day.result > 0 ? "up" : day.result < 0 ? "down" : ""}>
                {signed(day.result)} ({percentSigned(day.result, day.start_worth)})
              </span>
              <span className="muted">
                {day.fills.length} {day.fills.length === 1 ? "trade" : "trades"}
                {day.finished ? "" : ", left early"}
              </span>
            </summary>
            <p className="small muted">
              Started with {rupees(day.start_worth)}, ended with {rupees(day.end_worth)}. Charges and taxes: {rupees(day.charges)}.
              {index ? ` The Shifty 12 moved ${percentSigned(index.change, index.open)}.` : ""}
            </p>
            {day.companies.length > 0 && (
              <p className="small">
                {day.companies.map((c) => `${c.symbol} ${signed(c.today)}`).join(" · ")}
              </p>
            )}
            {day.news && day.news.length > 0 && (
              <ul className="small past-news">
                {day.news.map((n, i) => (
                  <li key={i}>
                    <span className="muted">{clock(n.at, preOpenUs, closeUs)}</span> {n.headline}
                    {n.impact_bp !== null && <span className="muted"> ({percentSigned(n.impact_bp, 10_000)})</span>}
                  </li>
                ))}
              </ul>
            )}
            {day.fills.length === 0 ? (
              <p className="muted small">You did not trade that day.</p>
            ) : (
              <table className="tape fills">
                <thead>
                  <tr>
                    <th scope="col">Time</th>
                    <th scope="col">Company</th>
                    <th scope="col">What</th>
                    <th scope="col">Shares</th>
                    <th scope="col">Price ₹</th>
                  </tr>
                </thead>
                <tbody>
                  {day.fills.map((f, i) => (
                    <tr key={i}>
                      <td>{clock(f.at, preOpenUs, closeUs)}</td>
                      <td>{f.symbol}</td>
                      <td>{f.side === "BUY" ? "Bought" : "Sold"}</td>
                      <td>{f.quantity}</td>
                      <td>{money(f.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </details>
        );
      })}
    </div>
  );
}
