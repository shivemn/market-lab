import { useMemo, useState } from "react";
import { rupees } from "../lib/format";
import type { MarketState, Side } from "../lib/market";
import { previewOrder } from "../lib/preview";

interface Props {
  state: MarketState;
  tickSize: number;
  disabled: boolean;
  refusal: string | null;
  onPlace: (side: Side, quantity: number, limitPrice: number | null) => Promise<boolean>;
  onClearRefusal: () => void;
}

/** Rupees typed by a person ("2500.05") to whole paise, or null if it is not a valid amount. */
export function toPaise(text: string): number | null {
  const clean = text.trim().replace(/,/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

export function OrderTicket({ state, tickSize, disabled, refusal, onPlace, onClearRefusal }: Props) {
  const [side, setSide] = useState<Side>("BUY");
  const [kind, setKind] = useState<"market" | "limit">("limit");
  const [quantityText, setQuantityText] = useState("10");
  const [priceText, setPriceText] = useState("");
  const [busy, setBusy] = useState(false);

  const quantity = /^\d+$/.test(quantityText) ? Number(quantityText) : 0;
  const bestOwn = side === "BUY" ? state.bestBid() : state.bestAsk();
  const price = kind === "limit" ? toPaise(priceText) : null;
  const priceProblem =
    kind !== "limit"
      ? null
      : price === null
        ? "Type a price in rupees, for example 2500.05."
        : price % tickSize !== 0
          ? `Prices move in steps of ${rupees(tickSize)}. Try ${rupees(Math.round(price / tickSize) * tickSize)}.`
          : null;

  const preview = useMemo(
    () => (priceProblem ? priceProblem : previewOrder(state, side, quantity, kind === "limit" ? price : null)),
    [state, side, quantity, kind, price, priceProblem, state.eventsApplied],
  );

  const send = async () => {
    setBusy(true);
    try {
      await onPlace(side, quantity, kind === "limit" ? price : null);
    } finally {
      setBusy(false);
    }
  };

  const ready = quantity > 0 && !priceProblem && !disabled && !busy;

  return (
    <section className="card ticket" aria-labelledby="ticket-title">
      <h2 id="ticket-title">Place an order</h2>
      <div className="seg" role="group" aria-label="Buy or sell">
        {(["BUY", "SELL"] as const).map((s) => (
          <button
            key={s}
            type="button"
            className={`${s === "BUY" ? "buy" : "sell"}${side === s ? " on" : ""}`}
            aria-pressed={side === s}
            onClick={() => {
              setSide(s);
              onClearRefusal();
            }}
          >
            {s === "BUY" ? "Buy" : "Sell"}
          </button>
        ))}
      </div>
      <div className="seg" role="group" aria-label="How to price it">
        <button type="button" className={kind === "limit" ? "on" : ""} aria-pressed={kind === "limit"} onClick={() => setKind("limit")}>
          Choose a price
        </button>
        <button type="button" className={kind === "market" ? "on" : ""} aria-pressed={kind === "market"} onClick={() => setKind("market")}>
          Best price now
        </button>
      </div>
      <label className="field">
        Number of shares
        <input inputMode="numeric" value={quantityText} onChange={(e) => setQuantityText(e.target.value.replace(/[^\d]/g, ""))} />
      </label>
      {kind === "limit" && (
        <label className="field">
          Your price per share, in rupees
          <div className="inline">
            <input
              inputMode="decimal"
              value={priceText}
              placeholder={bestOwn === null ? "2500.00" : (bestOwn / 100).toFixed(2)}
              onChange={(e) => setPriceText(e.target.value)}
            />
            <button
              type="button"
              className="btn"
              disabled={bestOwn === null}
              onClick={() => bestOwn !== null && setPriceText((bestOwn / 100).toFixed(2))}
              title="Use the best price in your own side of the queue"
            >
              Use best {side === "BUY" ? "buyer" : "seller"} price
            </button>
          </div>
        </label>
      )}
      <p className="preview" aria-live="polite">
        {preview}
      </p>
      <button className={`btn big ${side === "BUY" ? "primary" : "sellbtn"}`} disabled={!ready} onClick={() => void send()}>
        {busy ? "Sending…" : `${side === "BUY" ? "Buy" : "Sell"} ${quantity > 0 ? quantity : ""} ${quantity === 1 ? "share" : "shares"}`}
      </button>
      {refusal && (
        <p className="error" role="alert">
          {refusal}
        </p>
      )}
    </section>
  );
}
