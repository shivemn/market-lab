import { useMemo, useState } from "react";
import { myActivity, recentTrades } from "../lib/activity";
import { clock, money } from "../lib/format";
import type { MarketEvent } from "../lib/market";
import type { Statement } from "../lib/practice";
import { useThrottled } from "../lib/useThrottled";
import { Help } from "./Help";
import { StatementPanel } from "./StatementPanel";

interface Props {
  events: readonly MarketEvent[];
  ends: readonly number[];
  version: number;
  owner: string;
  playing: boolean;
  statement: Statement | null;
  statementFailed: boolean;
  lastPrice: number | null;
}

/** Two tabs under the chart: what happened to you, and what it cost. */
export function Activity({ events, ends, version, owner, playing, statement, statementFailed, lastPrice }: Props) {
  const [tab, setTab] = useState<"activity" | "statement">("activity");
  const mine = useMemo(() => myActivity(events, ends, owner), [version, owner]);
  const tapeNow = useMemo(() => recentTrades(events, 12, owner), [version, owner]);
  const tape = useThrottled(tapeNow, playing ? 1000 : 0); // at 100x the tape would be a blur; once a second is readable
  return (
    <section className="panel activity" aria-label="Your activity">
      <div className="tabline" role="tablist">
        <button role="tab" aria-selected={tab === "activity"} className={tab === "activity" ? "on" : ""} onClick={() => setTab("activity")}>
          Activity
        </button>
        <button role="tab" aria-selected={tab === "statement"} className={tab === "statement" ? "on" : ""} onClick={() => setTab("statement")}>
          Statement and costs
        </button>
      </div>
      {tab === "statement" ? (
        <StatementPanel statement={statement} failed={statementFailed} lastPrice={lastPrice} />
      ) : (
        <div className="act-grid">
          <div>
            <div className="ptitle">
              <h3 className="sub">Your orders</h3>
              <Help>Everything that happens to your own orders stays here, newest first. It does not scroll away while the day runs.</Help>
            </div>
            {mine.length === 0 ? (
              <p className="muted small">Nothing yet. Place an order and each step shows here.</p>
            ) : (
              <ol className="log">
                {mine.map((item) => (
                  <li key={item.key} className={item.kind}>
                    <span className="t">{clock(item.at)}</span>
                    <span>{item.text}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div>
            <div className="ptitle">
              <h3 className="sub">Recent trades</h3>
              <Help>The latest trades in the market, updated once a second while the day runs. Your own are marked.</Help>
            </div>
            {tape.length === 0 ? (
              <p className="muted small">No trades yet.</p>
            ) : (
              <table className="tape">
                <thead>
                  <tr>
                    <th scope="col">Time</th>
                    <th scope="col">Price ₹</th>
                    <th scope="col">Shares</th>
                  </tr>
                </thead>
                <tbody>
                  {tape.map((row) => (
                    <tr key={row.key} className={row.mine ? "mine" : ""}>
                      <td>{clock(row.at)}</td>
                      <td className={row.dir}>
                        {row.dir === "up" ? "▲ " : row.dir === "down" ? "▼ " : ""}
                        {money(row.price)}
                      </td>
                      <td>
                        {row.quantity}
                        {row.mine ? " (you)" : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
