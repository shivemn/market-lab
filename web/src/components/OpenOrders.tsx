import { rupees } from "../lib/format";
import type { WorldOpenOrder } from "../lib/world";
import { Panel } from "../ui";

export function OpenOrders({
  orders,
  onCancel,
}: {
  orders: readonly WorldOpenOrder[];
  onCancel: (symbol: string, orderId: number) => void;
}) {
  return (
    <Panel id="open-title" title="Your waiting orders" meta={<span className="count">{orders.length}</span>}>
      {orders.length === 0 ? (
        <p className="muted small">None. An order that cannot trade yet waits here, and you can cancel it.</p>
      ) : (
        <ul className="orders">
          {orders.map((o) => (
            <li key={`${o.symbol}${o.id}`}>
              <span>
                <b className={o.side === "BUY" ? "buy-text" : "sell-text"}>{o.side === "BUY" ? "Buy" : "Sell"}</b> {o.remaining}
                {o.remaining !== o.quantity ? ` of ${o.quantity}` : ""} {o.symbol} at{" "}
                {o.limit_price === null ? "any price" : rupees(o.limit_price)}
              </span>
              <button className="btn small-btn" onClick={() => onCancel(o.symbol, o.id)} aria-label={`Cancel order ${o.id} in ${o.symbol}`}>
                Cancel
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
