import { rupees } from "../lib/format";
import type { OpenOrder } from "../lib/practice";

export function OpenOrders({ orders, onCancel }: { orders: readonly OpenOrder[]; onCancel: (orderId: number) => void }) {
  return (
    <section className="panel" aria-labelledby="open-title">
      <div className="ptitle">
        <h2 id="open-title">Your waiting orders</h2>
        <span className="count">{orders.length}</span>
      </div>
      {orders.length === 0 ? (
        <p className="muted small">None. An order that cannot trade yet waits here, and you can cancel it.</p>
      ) : (
        <ul className="orders">
          {orders.map((o) => (
            <li key={o.id}>
              <span>
                <b className={o.side === "BUY" ? "buy-text" : "sell-text"}>{o.side === "BUY" ? "Buy" : "Sell"}</b> {o.remaining}
                {o.remaining !== o.quantity ? ` of ${o.quantity}` : ""} at {o.limit_price === null ? "any price" : rupees(o.limit_price)}
              </span>
              <button className="btn small-btn" onClick={() => onCancel(o.id)} aria-label={`Cancel order ${o.id}`}>
                Cancel
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
