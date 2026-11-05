import { money, rupees } from "../lib/format";
import type { Level, MarketState, Side } from "../lib/market";
import { lastTradeText } from "../lib/narrate";

const LEVELS = 5;
const MIN_BLOCK = 14;

interface Props {
  state: MarketState;
  followed: number | null;
  onFollow: (id: number | null) => void;
  symbol?: string; // the company, so the last trade can say which shares changed hands
  mine?: string; // the person's own account, so their orders stand out in the queue
}

export function Queue({ state, followed, onFollow, symbol, mine }: Props) {
  const asks = state.depth("SELL", LEVELS).reverse(); // worst price at the top, best next to the middle
  const bids = state.depth("BUY", LEVELS);
  const biggest = Math.max(1, ...asks.map((l) => l.quantity), ...bids.map((l) => l.quantity));
  const scale = Math.min(7, 200 / biggest);
  const bestBid = state.bestBid();
  const bestAsk = state.bestAsk();
  const gap =
    state.session === "PRE_OPEN"
      ? "Orders are being collected. Nothing trades until the opening auction."
      : state.session === "CLOSED" && state.eventsApplied === 0
        ? "Waiting for the day to start."
        : state.session === "CLOSED"
          ? "The market has closed. Orders still waiting have expired."
        : bestBid !== null && bestAsk !== null
          ? `Gap between the best buyer and best seller: ${rupees(bestAsk - bestBid)}`
          : "One side of the queue is empty.";

  const followedOrder = followed === null ? undefined : state.orders.get(followed);
  const note =
    followed === null
      ? "Tip: pause the replay, then click any block to follow that order and see how many shares are ahead of it."
      : followedOrder
        ? `Following order #${followed} from ${followedOrder.account}.`
        : `Order #${followed} is gone. It was filled or cancelled.`;

  const row = (level: Level, side: Side, best: boolean) => {
    const ahead = (id: number) => {
      let total = 0;
      for (const order of level.orders) {
        if (order.id === id) return total;
        total += order.remaining;
      }
      return null;
    };
    const label = followed !== null && ahead(followed) !== null ? aheadText(ahead(followed) as number) : "";
    const blocks = level.orders.map((order) => {
      const width = Math.max(MIN_BLOCK, order.remaining * scale);
      const pinned = order.id === followed;
      const yours = mine !== undefined && order.account === mine;
      return (
        <button
          key={order.id}
          className={`block ${side === "BUY" ? "buy" : "sell"}${pinned ? " pinned" : ""}${yours ? " mine" : ""}`}
          style={{ width }}
          onClick={() => onFollow(pinned ? null : order.id)}
          aria-pressed={pinned}
          aria-label={`${side === "BUY" ? "Buy" : "Sell"} order ${order.id} from ${yours ? "you" : order.account}, ${order.remaining} shares at ${rupees(level.price)}. ${pinned ? "Following." : "Select to follow."}`}
        >
          {yours ? (width >= 44 ? `You ${order.remaining}` : order.remaining) : width >= 28 ? order.remaining : ""}
        </button>
      );
    });
    return (
      <div className={`row${best ? ` best ${side === "BUY" ? "best-buy" : "best-sell"}` : ""}`} key={`${side}${level.price}`}>
        <div className="cell left">
          {side === "BUY" && (
            <>
              <span className="ahead">{label}</span>
              <div className="blocks reverse">{blocks}</div>
            </>
          )}
        </div>
        <div className={`pricecell${best ? " strong" : ""}`}>{money(level.price)}</div>
        <div className="cell right">
          {side === "SELL" && (
            <>
              <div className="blocks">{blocks}</div>
              <span className="ahead">{label}</span>
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <section className="card queue" aria-labelledby="queue-title">
      <h2 id="queue-title">Who is waiting to trade</h2>
      <p className="muted lead">
        Each block is one waiting order, and a wider block means more shares. The prices in the middle are the ones
        closest to a deal, and the order nearest the middle goes first.
      </p>
      <p className="lasttrade" aria-live="polite">
        {state.lastTrade === null ? "No trade yet." : <><b>Last trade:</b> {lastTradeText(state.lastTrade, symbol)}</>}
      </p>
      <div className="row head">
        <div className="buyer-title">Buyers, waiting to buy</div>
        <div className="pricecell">Price</div>
        <div className="seller-title">Sellers, waiting to sell</div>
      </div>
      <div className="ladder">
        {ghosts(LEVELS - asks.length, "a")}
        {asks.map((level, i) => row(level, "SELL", i === asks.length - 1))}
        <div className="gap">{gap}</div>
        {bids.map((level, i) => row(level, "BUY", i === 0))}
        {ghosts(LEVELS - bids.length, "b")}
        {asks.length === 0 && bids.length === 0 && state.session !== "CLOSED" && <div className="empty">Nobody is waiting in the queue yet.</div>}
      </div>
      <p className="muted small note" aria-live="polite">
        {note}
      </p>
    </section>
  );
}

/** Empty rows that keep the queue the same height however many prices are waiting, so the page does not jump. */
const ghosts = (count: number, key: string) =>
  Array.from({ length: Math.max(0, count) }, (_, i) => <div className="row ghost" aria-hidden="true" key={`${key}${i}`} />);

const aheadText = (shares: number) =>
  shares === 0 ? "First in line" : `${shares} ${shares === 1 ? "share is" : "shares are"} ahead`;
