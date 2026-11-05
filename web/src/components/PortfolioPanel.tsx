import { rupees } from "../lib/format";
import type { Portfolio } from "../lib/practice";

interface Props {
  portfolio: Portfolio;
  start: Portfolio | null;
  lastPrice: number | null;
  symbol: string;
  onCancel: (orderId: number) => void;
}

const worth = (p: Portfolio, price: number | null) => p.cash + p.reserved + (price === null ? 0 : (p.shares + p.locked) * price);

export function PortfolioPanel({ portfolio, start, lastPrice, symbol, onCancel }: Props) {
  const held = portfolio.shares + portfolio.locked;
  const total = worth(portfolio, lastPrice);
  const change = start === null ? null : total - worth(start, lastPrice);
  return (
    <section className="card" aria-labelledby="folio-title">
      <h2 id="folio-title">Your account</h2>
      <dl className="folio">
        <div>
          <dt>Cash you can use</dt>
          <dd>{rupees(portfolio.cash)}</dd>
        </div>
        <div>
          <dt>Set aside for open orders</dt>
          <dd>{rupees(portfolio.reserved)}</dd>
        </div>
        <div>
          <dt>{symbol} shares</dt>
          <dd>
            {held}
            {portfolio.locked > 0 && <span className="muted small"> ({portfolio.locked} locked in sell orders)</span>}
          </dd>
        </div>
        <div className="total">
          <dt>Worth now</dt>
          <dd>{rupees(total)}</dd>
        </div>
      </dl>
      {change !== null && (
        <p className="muted small">
          {change === 0
            ? "No change since you started this day."
            : `${change > 0 ? "Up" : "Down"} ${rupees(Math.abs(change))} since you started this day, with shares valued at the last price and all charges paid.`}
        </p>
      )}
      <h3 className="sub">Your open orders</h3>
      {portfolio.open_orders.length === 0 ? (
        <p className="muted small">None. Orders that are waiting in the queue show here, and you can cancel them.</p>
      ) : (
        <ul className="orders">
          {portfolio.open_orders.map((o) => (
            <li key={o.id}>
              <span>
                <b className={o.side === "BUY" ? "buy-text" : "sell-text"}>{o.side === "BUY" ? "Buy" : "Sell"}</b> {o.remaining}
                {o.remaining !== o.quantity ? ` of ${o.quantity}` : ""} at {o.limit_price === null ? "any price" : rupees(o.limit_price)}
              </span>
              <button className="btn" onClick={() => onCancel(o.id)} aria-label={`Cancel order ${o.id}`}>
                Cancel
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
