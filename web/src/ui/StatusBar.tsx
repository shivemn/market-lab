import type { ReactNode } from "react";
import { ThemeSwitch } from "../components/ThemeSwitch";
import { LivePill, type Session } from "./LivePill";

interface Props {
  session: Session;
  /** The simulated market clock, "11:42". */
  clock?: string | null;
  /** The quote in the middle: a company's price or an index level. */
  children: ReactNode;
}

/** The thin bar along the top of every screen: brand, the quote, the session, the market clock and the look. */
export function StatusBar({ session, clock, children }: Props) {
  return (
    <header className="top">
      <div className="brand">
        <div className="brand-name">Market Lab</div>
        <div className="muted small">Pretend money, made-up companies</div>
      </div>
      <div className="quote">{children}</div>
      <div className="top-right">
        {clock ? (
          <span className="sb-clock" aria-label={`Market time ${clock}`}>
            {clock} <span className="tz">IST</span>
          </span>
        ) : null}
        <LivePill session={session} />
        <ThemeSwitch />
      </div>
    </header>
  );
}
