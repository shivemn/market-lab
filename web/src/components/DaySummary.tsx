import { useEffect, useRef } from "react";
import type { DayResult } from "../lib/dayresult";
import { rupees, signed } from "../lib/format";

export interface PastDay {
  seed: number;
  result: number;
}

interface Props {
  open: boolean;
  seed: number;
  symbol: string;
  result: DayResult;
  held: number;
  lastPrice: number;
  days: readonly PastDay[];
  onClose: () => void;
  onStatement: () => void;
  onNextDay: () => void;
}

function headline(result: number): string {
  if (result === 0) return "You finished the day even";
  return `You ${result > 0 ? "made" : "lost"} ${rupees(Math.abs(result))} today`;
}

/** Shown when the market closes: how the day went in money, and what happens next. */
export function DaySummary({ open, seed, symbol, result, held, lastPrice, days, onClose, onStatement, onNextDay }: Props) {
  const box = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = box.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  const direction = result.result > 0 ? "up" : result.result < 0 ? "down" : "flat";
  return (
    <dialog ref={box} className="daybox" aria-labelledby="day-title" onClose={onClose}>
      <h2 id="day-title" className={direction}>
        {headline(result.result)}
      </h2>
      <p className="muted small">Day {seed} is over. This is your net result after all charges.</p>
      <dl className="mini">
        <div>
          <dt>Worth at the start</dt>
          <dd>{rupees(result.startWorth)}</dd>
        </div>
        <div>
          <dt>From price moves</dt>
          <dd>{signed(result.priceMoves)}</dd>
        </div>
        <div>
          <dt>Taxes and charges</dt>
          <dd>{signed(-result.charges)}</dd>
        </div>
        <div className="total">
          <dt>Worth at the close</dt>
          <dd>{rupees(result.endWorth)}</dd>
        </div>
      </dl>
      {held > 0 && (
        <p className="callout">
          You still hold {held} {symbol} {held === 1 ? "share" : "shares"}, valued at the last price of {rupees(lastPrice)}. The
          result is on paper until you sell them, and selling adds more charges.
        </p>
      )}
      {days.length > 1 && (
        <div>
          <h3 className="sub">Your days so far</h3>
          <ul className="orders">
            {days.map((d, i) => (
              <li key={i}>
                <span>Day {d.seed}</span>
                <b className={d.result > 0 ? "up" : d.result < 0 ? "down" : ""}>{signed(d.result)}</b>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="dialog-actions">
        <button className="btn" onClick={onStatement}>
          See every charge
        </button>
        <button className="btn primary" onClick={onNextDay}>
          Start the next day
        </button>
        <button className="btn" onClick={onClose}>
          Close
        </button>
      </div>
    </dialog>
  );
}
