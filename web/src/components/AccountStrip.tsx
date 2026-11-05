import { rupees, signed } from "../lib/format";
import { dayResult, worth } from "../lib/dayresult";
import type { Portfolio, Statement } from "../lib/practice";

interface Props {
  portfolio: Portfolio;
  start: Portfolio | null;
  statement: Statement | null;
  lastPrice: number | null;
  previousClose: number;
  symbol: string;
}

/** The numbers a person checks after every trade, always in view. */
export function AccountStrip({ portfolio, start, statement, lastPrice, previousClose, symbol }: Props) {
  const held = portfolio.shares + portfolio.locked;
  const result = start === null ? 0 : dayResult(start, portfolio, previousClose, lastPrice, 0).result;
  const direction = result > 0 ? "up" : result < 0 ? "down" : "flat";
  return (
    <section className="strip" aria-label="Your account">
      <div className="stat lead">
        <span className="k">Worth now</span>
        <span className="v big">{rupees(worth(portfolio, lastPrice ?? previousClose))}</span>
      </div>
      <div className="stat">
        <span className="k">Result today</span>
        <span className={`v ${direction}`}>{signed(result)}</span>
      </div>
      <div className="stat">
        <span className="k">Cash to use</span>
        <span className="v">{rupees(portfolio.cash)}</span>
      </div>
      {portfolio.reserved > 0 && (
        <div className="stat">
          <span className="k">Held for orders</span>
          <span className="v">{rupees(portfolio.reserved)}</span>
        </div>
      )}
      <div className="stat">
        <span className="k">{symbol} shares</span>
        <span className="v">
          {held}
          {portfolio.locked > 0 && <span className="muted small"> ({portfolio.locked} in sell orders)</span>}
        </span>
      </div>
      <div className="stat">
        <span className="k">Charges paid</span>
        <span className="v">{statement === null ? "…" : rupees(statement.total_charges)}</span>
      </div>
    </section>
  );
}
