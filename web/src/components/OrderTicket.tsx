import { useEffect, useMemo, useState } from "react";
import { money, rupees } from "../lib/format";
import type { MarketState, Side } from "../lib/market";
import { previewOrder } from "../lib/preview";
import { Help } from "./Help";

interface Props {
  state: MarketState;
  tickSize: number;
  disabled: boolean;
  refusal: string | null;
  /** A price the person clicked in the ladder; `nonce` changes on every click so the same price can be picked twice. */
  pick: { price: number; nonce: number } | null;
  onPlace: (side: Side, quantity: number, limitPrice: number | null) => Promise<boolean>;
  onClearRefusal: () => void;
}

/** Rupees typed by a person ("2500.05") to whole paise, or null if it is not a valid amount. */
export function toPaise(text: string): number | null {
  const clean = text.trim().replace(/,/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

const QUICK = [1, 5, 10, 50];

export function OrderTicket({ state, tickSize, disabled, refusal, pick, onPlace, onClearRefusal }: Props) {
  const [side, setSide] = useState<Side>("BUY");
  const [kind, setKind] = useState<"market" | "limit">("market");
  const [quantityText, setQuantityText] = useState("5");
  const [priceText, setPriceText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (pick === null) return;
    setKind("limit");
    setPriceText((pick.price / 100).toFixed(2));
    onClearRefusal();
  }, [pick?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const quantity = /^\d+$/.test(quantityText) ? Number(quantityText) : 0;
  const bid = state.bestBid();
  const ask = state.bestAsk();
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
  const setPrice = (paise: number | null) => paise !== null && setPriceText((paise / 100).toFixed(2));

  return (
    <section className="panel ticket" aria-labelledby="ticket-title">
      <div className="ptitle">
        <h2 id="ticket-title">Place an order</h2>
        <Help>
          "Best price now" trades straight away with whoever is waiting, at their prices. "Choose a price" waits in the queue
          until someone meets your price. Before the open, orders wait for the opening auction.
        </Help>
      </div>
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
      <div className="seg quiet" role="group" aria-label="How to price it">
        <button type="button" className={kind === "market" ? "on" : ""} aria-pressed={kind === "market"} onClick={() => setKind("market")}>
          Best price now
        </button>
        <button type="button" className={kind === "limit" ? "on" : ""} aria-pressed={kind === "limit"} onClick={() => setKind("limit")}>
          Choose a price
        </button>
      </div>
      <div className="field">
        <label htmlFor="qty">Shares</label>
        <input id="qty" inputMode="numeric" value={quantityText} onChange={(e) => setQuantityText(e.target.value.replace(/[^\d]/g, ""))} />
        <div className="chips">
          {QUICK.map((n) => (
            <button key={n} type="button" className="chip-btn" onClick={() => setQuantityText(String(n))}>
              {n}
            </button>
          ))}
        </div>
      </div>
      {kind === "limit" && (
        <div className="field">
          <label htmlFor="px">Price per share, ₹</label>
          <input id="px" inputMode="decimal" value={priceText} placeholder="2500.00" onChange={(e) => setPriceText(e.target.value)} />
          <div className="chips">
            <button type="button" className="chip-btn" disabled={bid === null} onClick={() => setPrice(bid)}>
              Best buyer {bid === null ? "–" : money(bid)}
            </button>
            <button type="button" className="chip-btn" disabled={ask === null} onClick={() => setPrice(ask)}>
              Best seller {ask === null ? "–" : money(ask)}
            </button>
          </div>
        </div>
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
