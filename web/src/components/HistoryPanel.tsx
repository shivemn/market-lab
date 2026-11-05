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

/** Every practice day that was played, with each trade, kept in the database so it is still here tomorrow. */
export function HistoryPanel({ days, failed, preOpenUs, closeUs }: Props) {
  if (failed) return <p className="muted small" role="alert">Your saved days could not be loaded. Is the server running?</p>;
  if (days === null) return <p className="muted small">Loading your saved days…</p>;
  if (days.length === 0) {
    return <p className="muted small">Nothing saved yet. Each day you play to the close, or leave after trading, is kept here with every trade you made.</p>;
  }
  return (
    <div className="history">
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
