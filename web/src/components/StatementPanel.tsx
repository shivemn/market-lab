import { clock, rupees, signed } from "../lib/format";
import type { Statement, StatementRow } from "../lib/practice";

const LINE_NAMES: Record<string, string> = {
  brokerage: "Broker's fee",
  stt: "Securities transaction tax",
  exchange: "Exchange charge",
  sebi: "SEBI fee",
  stamp: "Stamp duty",
  demat: "Demat fee",
  gst: "GST on fees",
};

function describeRow(row: StatementRow): string {
  if (row.kind === "buy" || row.kind === "sell") {
    const shares = Math.abs(row.shares_change);
    const each = Math.round(row.value / shares);
    return `${row.kind === "buy" ? "Bought" : "Sold"} ${shares} ${row.symbol} at ${rupees(each)}`;
  }
  return row.memo;
}

interface Props {
  statement: Statement | null;
  failed: boolean;
  lastPrice: number | null;
}

/** What trading did to the account, and what the charges took. Built by the server from the ledger alone. */
export function StatementPanel({ statement, failed, lastPrice }: Props) {
  if (statement === null) return <p className="muted small">{failed ? "The statement could not be loaded." : "Loading…"}</p>;
  const price = lastPrice ?? statement.price;
  const held = statement.holdings[statement.symbol] ?? 0;
  const gain = statement.money + held * price - statement.starting_money;
  const trades = statement.rows.filter((r) => r.kind === "buy" || r.kind === "sell");
  const lines = Object.entries(statement.charges_by_line).filter(([, amount]) => amount > 0);
  const percent = (statement.charges_basis_points / 100).toFixed(2);
  return (
    <div className="statement-wrap">
      {trades.length === 0 ? (
        <p className="muted small">No trades yet. After you trade, every charge shows here, line by line.</p>
      ) : (
        <div className="cost-grid">
          <dl className="mini">
            <div>
              <dt>Bought</dt>
              <dd>{rupees(statement.bought)}</dd>
            </div>
            <div>
              <dt>Sold</dt>
              <dd>{rupees(statement.sold)}</dd>
            </div>
            <div>
              <dt>From price moves</dt>
              <dd>{signed(gain + statement.total_charges)}</dd>
            </div>
            <div>
              <dt>Charges</dt>
              <dd>{signed(-statement.total_charges)}</dd>
            </div>
            <div className="total">
              <dt>Result after charges</dt>
              <dd>{signed(gain)}</dd>
            </div>
          </dl>
          <div>
            <h3 className="sub">Where the charges went ({percent}% of what you traded)</h3>
            <ul className="orders">
              {lines.map(([line, amount]) => (
                <li key={line}>
                  <span>{LINE_NAMES[line] ?? line}</span>
                  <b>{rupees(amount)}</b>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
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
                  <td>{row.kind === "start" || row.kind === "grant" ? "Start" : clock(row.at)}</td>
                  <td>{describeRow(row)}</td>
                  <td>{charged > 0 ? rupees(charged) : "–"}</td>
                  <td>{row.money_change === 0 ? "–" : signed(row.money_change)}</td>
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
    </div>
  );
}
