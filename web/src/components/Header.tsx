import type { RunSummary } from "../lib/api";
import { changeShort, rupees } from "../lib/format";
import type { MarketState } from "../lib/market";
import { Delta, StatusBar } from "../ui";

export function Header({
  state,
  summary,
  clock,
}: {
  state: MarketState;
  summary: Pick<RunSummary, "instrument"> | null;
  /** The market clock of the moment on screen, "11:42". */
  clock?: string | null;
}) {
  const reference = summary?.instrument.reference_price ?? null;
  const price = state.lastPrice ?? state.openingPrice ?? reference;
  const change = price !== null && reference !== null ? changeShort(price, reference) : null;
  return (
    <StatusBar session={state.session} clock={clock}>
      <span className="symbol">{summary?.instrument.symbol ?? "…"}</span>
      <span className="price" aria-live="off">
        {price === null ? "…" : rupees(price)}
      </span>
      {change && <Delta dir={change.dir}>{change.text}</Delta>}
      {reference !== null && <span className="muted small">since yesterday's close of {rupees(reference)}</span>}
    </StatusBar>
  );
}
