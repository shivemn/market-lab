import { ReactNode, useMemo } from "react";
import { ActivityItem, recentTrades } from "../lib/activity";
import { clock, money } from "../lib/format";
import type { MarketEvent } from "../lib/market";
import { useThrottled } from "../lib/useThrottled";
import { Help } from "./Help";

export type ActivityTab = "activity" | "companies" | "index" | "statement" | "history";

const TABS: { key: ActivityTab; label: string }[] = [
  { key: "activity", label: "Activity" },
  { key: "companies", label: "Your result by company" },
  { key: "index", label: "The index" },
  { key: "statement", label: "Statement and costs" },
  { key: "history", label: "Your past days" },
];

interface Props {
  /** Your orders in every company, newest first. */
  mine: readonly ActivityItem[];
  /** The selected company's events, for the recent-trades list. */
  events: readonly MarketEvent[];
  symbol: string;
  version: number;
  owner: string;
  playing: boolean;
  tab: ActivityTab;
  onTab: (tab: ActivityTab) => void;
  panels: Record<Exclude<ActivityTab, "activity">, ReactNode>;
}

/** Tabs under the chart: what happened to you, how each company did, how the index is built, and what it all cost. */
export function Activity({ mine, events, symbol, version, owner, playing, tab, onTab: setTab, panels }: Props) {
  const tapeNow = useMemo(() => recentTrades(events, 12, owner), [version, owner, events]);
  const tape = useThrottled(tapeNow, playing ? 1000 : 0); // at 100x the tape would be a blur; once a second is readable
  return (
    <section className="panel activity" aria-label="Your activity">
      <div className="tabline" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab !== "activity" ? (
        panels[tab]
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
              <h3 className="sub">Recent trades in {symbol}</h3>
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
                  {Array.from({ length: Math.max(0, 12 - tape.length) }, (_, i) => (
                    <tr key={`g${i}`} className="ghost" aria-hidden="true">
                      <td colSpan={3}>&nbsp;</td>
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
