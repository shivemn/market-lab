import { useEffect, useState } from "react";
import { dayClock, rupees } from "../lib/format";
import { getStatement, Statement, StatementRow } from "../lib/practice";

const LINE_NAMES: Record<string, string> = {
  brokerage: "Broker's fee",
  stt: "Securities transaction tax",
  exchange: "Exchange charge",
  sebi: "SEBI fee",
  stamp: "Stamp duty",
  demat: "Demat fee",
  gst: "GST on fees",
};

interface Props {
  sessionId: string;
  /** Changes whenever the account changes, so the statement is fetched again. */
  stamp: string;
  /** The last traded price, so holdings can be valued without asking the server again on every price change. */
  lastPrice: number | null;
}

function describeRow(row: StatementRow): string {
  if (row.kind === "buy" || row.kind === "sell") {
    const shares = Math.abs(row.shares_change);
    const each = Math.round(row.value / shares);
    return `${row.kind === "buy" ? "Bought" : "Sold"} ${shares} ${row.symbol} at ${rupees(each)} a share`;
  }
  return row.memo;
}

export function StatementPanel({ sessionId, stamp, lastPrice }: Props) {
  const [statement, setStatement] = useState<Statement | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let current = true;
    getStatement(sessionId).then(
      (s) => {
        if (current) {
          setStatement(s);
          setFailed(false);
        }
      },
      () => {
        if (current) setFailed(true);
      },
    );
    return () => {
      current = false;
    };
  }, [sessionId, stamp]);

  if (statement === null) {
    return (
      <section className="card" aria-labelledby="statement-title">
        <h2 id="statement-title">What trading has cost you</h2>
        <p className="muted small">{failed ? "The statement could not be loaded." : "Loading…"}</p>
      </section>
    );
  }
  const price = lastPrice ?? statement.price;
  const held = statement.holdings[statement.symbol] ?? 0;
  const gain = statement.money + held * price - statement.starting_money;
  const trades = statement.rows.filter((r) => r.kind === "buy" || r.kind === "sell");
  const lines = Object.entries(statement.charges_by_line).filter(([, amount]) => amount > 0);
  const percent = (statement.charges_basis_points / 100).toFixed(2);
  return (
    <section className="card" aria-labelledby="statement-title">
      <h2 id="statement-title">What trading has cost you</h2>
      {trades.length === 0 ? (
        <p className="muted small">No trades yet. Once you trade, every charge appears here, line by line.</p>
      ) : (
        <>
          <dl className="folio">
            <div>
              <dt>Bought</dt>
              <dd>{rupees(statement.bought)}</dd>
            </div>
            <div>
              <dt>Sold</dt>
              <dd>{rupees(statement.sold)}</dd>
            </div>
            <div>
              <dt>Gain or loss from price moves</dt>
              <dd>{rupees(gain + statement.total_charges)}</dd>
            </div>
            <div>
              <dt>Charges paid</dt>
              <dd>{rupees(statement.total_charges)}</dd>
            </div>
            <div className="total">
              <dt>Your result after charges</dt>
              <dd>{rupees(gain)}</dd>
            </div>
          </dl>
          <p className="muted small">
            Charges took {percent}% of everything you traded. Shares you still hold are valued at {rupees(price)}, the
            last price.
          </p>
          <h3 className="sub">Where the charges went</h3>
          <ul className="orders">
            {lines.map(([line, amount]) => (
              <li key={line}>
                <span>{LINE_NAMES[line] ?? line}</span>
                <b>{rupees(amount)}</b>
              </li>
            ))}
          </ul>
        </>
      )}
      <h3 className="sub">Statement</h3>
      <div className="table-scroll" tabIndex={0}>
        <table className="statement">
          <caption className="sr-only">Every change to your money and shares, in order</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">What happened</th>
              <th scope="col">Charges</th>
              <th scope="col">Money change</th>
              <th scope="col">Money after</th>
            </tr>
          </thead>
          <tbody>
            {statement.rows.map((row, i) => {
              const charged = Object.values(row.charges).reduce((a, b) => a + b, 0);
              return (
                <tr key={i}>
                  <td>{row.kind === "start" || row.kind === "grant" ? "Start" : dayClock(row.at)}</td>
                  <td>{describeRow(row)}</td>
                  <td>{charged > 0 ? rupees(charged) : "–"}</td>
                  <td>{row.money_change === 0 ? "–" : rupees(row.money_change)}</td>
                  <td>{rupees(row.money_after)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {statement.problems.length > 0 && (
        <p className="error" role="alert">
          The books do not add up: {statement.problems.join("; ")}
        </p>
      )}
    </section>
  );
}
