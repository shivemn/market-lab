import { useEffect, useRef } from "react";
import { rupees, signed } from "../lib/format";
import type { WorldDay } from "../lib/worldview";

export interface PastDay {
  seed: number;
  result: number;
}

export interface CompanyResult {
  symbol: string;
  name: string;
  today: number;
}

interface Props {
  open: boolean;
  seed: number;
  result: WorldDay;
  /** Companies where something happened today, best first. */
  companies: readonly CompanyResult[];
  /** Companies you still hold shares in, as "UDHAAR 5". */
  held: readonly string[];
  versus: string; // "Behind Shifty 12 by 0.31%"
  detail: string; // "you +0.00% · index +0.31%"
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
export function DaySummary({ open, seed, result, companies, held, versus, detail, days, onClose, onStatement, onNextDay }: Props) {
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
      <p className="callout">
        <b>{versus}.</b> {detail}.
      </p>
      {companies.length > 0 && (
        <div>
          <h3 className="sub">Company by company, today</h3>
          <ul className="orders">
            {companies.map((c) => (
              <li key={c.symbol}>
                <span>{c.name}</span>
                <b className={c.today > 0 ? "up" : c.today < 0 ? "down" : ""}>{signed(c.today)}</b>
              </li>
            ))}
          </ul>
        </div>
      )}
      {held.length > 0 && (
        <p className="callout">
          You still hold {held.join(", ")}, valued at the last prices. The result is on paper until you sell, and selling adds more
          charges.
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
