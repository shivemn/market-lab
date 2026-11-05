import type { RunSummary } from "../lib/api";
import { changeShort, rupees } from "../lib/format";
import type { MarketState } from "../lib/market";
import { ThemeSwitch } from "./ThemeSwitch";

const SESSION_WORDS = { CLOSED: "Closed", PRE_OPEN: "Before the open", OPEN: "Open" } as const;

export function Header({ state, summary }: { state: MarketState; summary: Pick<RunSummary, "instrument"> | null }) {
  const reference = summary?.instrument.reference_price ?? null;
  const price = state.lastPrice ?? state.openingPrice ?? reference;
  const change = price !== null && reference !== null ? changeShort(price, reference) : null;
  return (
    <header className="top">
      <div className="brand">
        <div className="brand-name">Market Lab</div>
        <div className="muted small">Simulated money, made-up company</div>
      </div>
      <div className="quote">
        <span className="symbol">{summary?.instrument.symbol ?? "DEMO1"}</span>
        <span className="price" aria-live="off">
          {price === null ? "…" : rupees(price)}
        </span>
        {change && <span className={`change ${change.dir}`}>{change.text}</span>}
        {reference !== null && <span className="muted small">since yesterday's close of {rupees(reference)}</span>}
      </div>
      <div className="top-right">
        <span className={`chip chip-${state.session.toLowerCase()}`}>{SESSION_WORDS[state.session]}</span>
        <ThemeSwitch />
      </div>
    </header>
  );
}
