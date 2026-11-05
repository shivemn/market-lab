import type { RunSummary } from "../lib/api";
import { changeWords, rupees } from "../lib/format";
import type { MarketState } from "../lib/market";

const SESSION_WORDS = { CLOSED: "Market is closed", PRE_OPEN: "Before the open", OPEN: "Market is open" } as const;

export function Header({ state, summary }: { state: MarketState; summary: Pick<RunSummary, "instrument"> | null }) {
  const reference = summary?.instrument.reference_price ?? null;
  const price = state.lastPrice ?? state.openingPrice ?? reference;
  return (
    <header className="top">
      <div className="brand">
        <div className="brand-name">Market Lab</div>
        <div className="muted small">Practice market. Simulated money only.</div>
      </div>
      <div className="quote">
        <div>
          <div className="symbol">{summary?.instrument.symbol ?? "DEMO1"}</div>
          <div className="muted small">Demo Industries Ltd, a made-up company</div>
        </div>
        <div className="price" aria-live="off">
          {price === null ? "…" : rupees(price)}
        </div>
        {price !== null && reference !== null && (
          <div className="muted change">{changeWords(price, reference)} from yesterday's close of {rupees(reference)}</div>
        )}
      </div>
      <div className={`chip chip-${state.session.toLowerCase()}`}>{SESSION_WORDS[state.session]}</div>
    </header>
  );
}
