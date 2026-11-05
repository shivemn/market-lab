import { buildLadder, LadderRow } from "../lib/activity";
import { money, rupees } from "../lib/format";
import type { MarketState } from "../lib/market";
import { lastTradeText } from "../lib/narrate";
import type { WorldOpenOrder } from "../lib/world";
import { Help } from "./Help";

interface Props {
  state: MarketState;
  mine: readonly WorldOpenOrder[];
  symbol?: string;
  levels?: number;
  onPick: (price: number) => void;
}

function Row({ row, onPick }: { row: LadderRow; onPick: (price: number) => void }) {
  return (
    <button
      type="button"
      className={`lrow ${row.side}`}
      onClick={() => onPick(row.price)}
      aria-label={`${row.quantity} shares ${row.side === "ask" ? "for sale" : "wanted"} at ${rupees(row.price)}${
        row.mine > 0 ? `, ${row.mine} of them yours` : ""
      }. Use this price.`}
    >
      <span className="bar" style={{ width: `${Math.max(row.share, 0.04) * 100}%` }} aria-hidden="true" />
      <span className="mark">{row.mine > 0 && <b className="you-tag">You {row.mine}</b>}</span>
      <span className="size">{row.quantity}</span>
      <span className="px">{money(row.price)}</span>
    </button>
  );
}

/** Empty rows keep the ladder the same height however many prices are waiting, so nothing below it moves. */
const ghost = (count: number, key: string) =>
  Array.from({ length: Math.max(0, count) }, (_, i) => <div className="lrow ghost" aria-hidden="true" key={`${key}${i}`} />);

/** Who is waiting to trade, as a price ladder: sellers above, buyers below, the gap in between. */
export function Ladder({ state, mine, symbol, levels = 6, onPick }: Props) {
  const ladder = buildLadder(state, levels, mine);
  const empty = ladder.asks.length === 0 && ladder.bids.length === 0;
  return (
    <section className="panel ladder" aria-labelledby="ladder-title">
      <div className="ptitle">
        <h2 id="ladder-title">Waiting to trade</h2>
        <Help>
          Sellers wait above and buyers below. A trade happens when someone is willing to meet the other side's price.
          The bar is how many shares wait at that price. Click a price to use it in your order.
        </Help>
      </div>
      <p className="lasttrade" aria-live="polite">
        {state.lastTrade === null ? "No trade yet." : <><b>Last trade:</b> {lastTradeText(state.lastTrade, symbol)}</>}
      </p>
      {empty ? (
        <p className="muted small">
          {state.session === "CLOSED" && state.eventsApplied > 1
            ? "The market is closed, so nobody is waiting to trade. Orders left over at the close expire."
            : "Nobody is waiting yet. Orders appear here as traders send them."}
        </p>
      ) : (
        <div className="lad">
          <div className="lhead" aria-hidden="true">
            <span />
            <span>Shares</span>
            <span>Price ₹</span>
          </div>
          <div className="side-label ask-label">Sellers</div>
          {ghost(levels - ladder.asks.length, "a")}
          {ladder.asks.map((row) => (
            <Row key={`a${row.price}`} row={row} onPick={onPick} />
          ))}
          <div className="spread">{ladder.spread === null ? "No price gap yet" : `Gap ${rupees(ladder.spread)}`}</div>
          {ladder.bids.map((row) => (
            <Row key={`b${row.price}`} row={row} onPick={onPick} />
          ))}
          {ghost(levels - ladder.bids.length, "b")}
          <div className="side-label bid-label">Buyers</div>
        </div>
      )}
    </section>
  );
}
