import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ActivityItem, myActivity } from "../lib/activity";
import { fold } from "../lib/market";
import { indexSeries, tradeSeries } from "../lib/series";
import { useStatement } from "../lib/useStatement";
import { useDays } from "../lib/useDays";
import { useWorld } from "../lib/useWorld";
import type { IndexKind, WorldRequest } from "../lib/world";
import { compare, indexPercent, sign, worldDay } from "../lib/worldview";
import { AccountStrip } from "./AccountStrip";
import { Activity, ActivityTab } from "./Activity";
import { useAccount } from "./AuthGate";
import { CompaniesPanel } from "./CompaniesPanel";
import { DaySummary, PastDay } from "./DaySummary";
import { HistoryPanel } from "./HistoryPanel";
import { IndexPanel } from "./IndexPanel";
import { Ladder } from "./Ladder";
import { MarketBoard } from "./MarketBoard";
import { headlineOf, NewsPanel, NewsTicker } from "./NewsPanel";
import { OpenOrders } from "./OpenOrders";
import { OrderTicket } from "./OrderTicket";
import { IndexChart } from "./IndexChart";
import { PriceChart } from "./PriceChart";
import { StatementPanel } from "./StatementPanel";
import { WorldHeader } from "./WorldHeader";

type Practice = ReturnType<typeof useWorld>;
type PlanName = WorldRequest["plan"];

function StartCard({ practice, again, refresh }: { practice: Practice; again?: boolean; refresh?: unknown }) {
  const account = useAccount();
  const [typed, setOwner] = useState("you");
  const owner = account.username ?? typed; // signed in: the account is your sign-in name, not a box to fill
  const saved = useDays(owner, refresh);
  const [seed, setSeed] = useState(7);
  const [plan, setPlan] = useState<PlanName>("zero");
  const valid = /^[A-Za-z0-9_-]{1,32}$/.test(owner);
  return (
    <section className="card picker" aria-labelledby="start-title">
      <h2 id="start-title">{again ? "Start a new practice day" : "Practice with pretend money"}</h2>
      <p className="muted lead">
        {again
          ? "Your cash and shares carry over. Orders still waiting are returned first."
          : "You start with ₹1,00,000 of pretend money. Twelve made-up companies trade together. Buy and sell, follow the Shifty 12 index, and see every tax and charge a real investor would pay. Nothing here is real or advice."}
      </p>
      {account.username === null ? (
        <label className="field">
          Your name for the account (letters and numbers)
          <input value={owner} onChange={(e) => setOwner(e.target.value)} aria-invalid={!valid} />
        </label>
      ) : (
        <p className="account-fixed">
          Playing as <strong>{account.username}</strong>
          {account.guest ? " (guest)" : ""}
        </p>
      )}
      <label className="field">
        Day number
        <div className="inline">
          <input type="number" min={0} max={4294967295} value={seed} onChange={(e) => setSeed(Math.max(0, Math.floor(Number(e.target.value))))} />
          <button className="btn" type="button" onClick={() => setSeed(Math.floor(Math.random() * 100000))}>
            Surprise me
          </button>
        </div>
      </label>
      <label className="field">
        Broker charges
        <select value={plan} onChange={(e) => setPlan(e.target.value as PlanName)}>
          <option value="zero">No brokerage (only taxes and exchange charges)</option>
          <option value="flat20">₹20 brokerage per order, ₹20 demat fee on sells</option>
        </select>
      </label>
      <button
        className="btn primary big"
        disabled={!valid || practice.status === "starting"}
        onClick={() => void practice.start({ owner, seed, plan })}
      >
        {practice.status === "starting" ? "Starting…" : "Start the day"}
      </button>
      {practice.error && (
        <p className="error" role="alert">
          {practice.error}
        </p>
      )}
      {!again && (
        <>
          <h3 className="sub">Your past days</h3>
          <HistoryPanel days={saved.days} failed={saved.failed} preOpenUs={60_000_000} closeUs={660_000_000} />
        </>
      )}
    </section>
  );
}

const COACH_KEY = "marketlab-coach-dismissed";

const GUIDE = [
  "Press play on the chart. The day runs at the speed you choose, and you can pause any time.",
  "Pick a company on the board, then choose Buy and a number of shares in the order box.",
  "Your order is in. Watch the Activity tab: the day pauses when it trades, so you never miss it.",
  "You hold shares now. The strip on top shows your result against the index. At 15:30 you get a summary.",
];

/** A four-step guide for the first day. It follows what you actually do and stays out of the way afterwards. */
function Coach({ played, ordered, holding }: { played: boolean; ordered: boolean; holding: boolean }) {
  const [hidden, setHidden] = useState(() => {
    try {
      return window.localStorage.getItem(COACH_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (hidden) return null;
  const step = holding ? 3 : ordered ? 2 : played ? 1 : 0;
  const dismiss = () => {
    setHidden(true);
    try {
      window.localStorage.setItem(COACH_KEY, "1");
    } catch {
      // it just comes back next visit
    }
  };
  return (
    <div className="coach" role="note" aria-label="First day guide">
      <ol className="coach-steps" aria-hidden="true">
        {GUIDE.map((_, i) => (
          <li key={i} className={i < step ? "done" : i === step ? "now" : ""} />
        ))}
      </ol>
      <span>
        <b>Step {step + 1} of {GUIDE.length}.</b> {GUIDE[step]}
      </span>
      <button className="btn small-btn" onClick={dismiss}>
        {step === GUIDE.length - 1 ? "Got it" : "Skip the guide"}
      </button>
    </div>
  );
}

export function PracticeView({ tabs, active }: { tabs: ReactNode; active: boolean }) {
  const world = useWorld();
  const { events, ends, touched, version, snapshot, first } = world;
  const [selected, setSelected] = useState("UDHAAR");
  const [kind, setKind] = useState<IndexKind>("cap");
  const [pick, setPick] = useState<{ price: number; nonce: number } | null>(null);
  const [tab, setTab] = useState<ActivityTab>("activity");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [days, setDays] = useState<PastDay[]>([]);
  const lastRequest = useRef<WorldRequest | null>(null);
  const summarised = useRef<string | null>(null);

  // leaving this screen pauses the day (the server keeps no clock, so nothing runs behind your back); it stays as it was
  const { status, togglePause } = world;
  useEffect(() => {
    if (!active && status === "playing") togglePause();
  }, [active, status]); // eslint-disable-line react-hooks/exhaustive-deps
  const saved = useDays(snapshot?.owner ?? "", `${snapshot?.id}:${world.status}`);

  const company = snapshot?.companies.find((c) => c.symbol === selected) ?? snapshot?.companies[0] ?? null;
  const symbol = company?.symbol ?? selected;
  const state = useMemo(() => fold(events[symbol] ?? []), [version, symbol]); // eslint-disable-line react-hooks/exhaustive-deps
  const trades = useMemo(() => tradeSeries(events[symbol] ?? []), [version, symbol]); // eslint-disable-line react-hooks/exhaustive-deps
  const owner = snapshot?.owner ?? "";
  const indexLine = useMemo(() => {
    const f = world.factors?.[kind];
    if (!f || !snapshot) return [];
    const closes = Object.fromEntries(snapshot.companies.map((c) => [c.symbol, c.instrument.reference_price]));
    return indexSeries(events, f, closes, Math.max(1, Math.floor(snapshot.close_at / 600)));
  }, [version, kind, world.factors]); // eslint-disable-line react-hooks/exhaustive-deps
  const mine = useMemo<ActivityItem[]>(() => {
    const all: ActivityItem[] = [];
    [...touched].forEach((s, i) => {
      for (const item of myActivity(events[s] ?? [], ends[s] ?? [], owner, s)) {
        all.push({ ...item, key: item.key * 16 + i });
      }
    });
    return all.sort((a, b) => b.at - a.at || b.key - a.key);
  }, [version, owner]); // eslint-disable-line react-hooks/exhaustive-deps

  const stamp =
    snapshot === null
      ? ""
      : [snapshot.portfolio.cash, snapshot.portfolio.reserved, snapshot.total_charges, ...Object.values(snapshot.portfolio.holdings).map((h) => `${h.shares}/${h.locked}`)].join(":");
  const { statement, failed } = useStatement(snapshot?.id ?? null, stamp);

  const day = snapshot !== null && first !== null ? worldDay(first, snapshot) : null;
  const versus =
    snapshot !== null && day !== null ? compare(day.youPercent, indexPercent(snapshot, kind), snapshot.index_name) : null;

  // when the market closes, say how the day went (once the statement has caught up with the final balances)
  useEffect(() => {
    if (world.status !== "done" || snapshot === null || statement === null || day === null) return;
    if (summarised.current === snapshot.id || statement.money !== snapshot.portfolio.cash + snapshot.portfolio.reserved) return;
    summarised.current = snapshot.id;
    setDays((list) => [...list, { seed: snapshot.config.seed, result: day.result }]);
    setDialogOpen(true);
  }, [world.status, snapshot?.id, statement, snapshot]); // eslint-disable-line react-hooks/exhaustive-deps

  const startDay = (request: WorldRequest) => {
    lastRequest.current = request;
    setPick(null);
    return world.start(request);
  };
  const nextDay = () => {
    if (snapshot === null) return;
    const last = lastRequest.current ?? { owner: snapshot.owner, seed: snapshot.config.seed, plan: "zero" as PlanName };
    setDialogOpen(false);
    void startDay({ ...last, seed: last.seed + 1 });
  };

  const companyResults =
    snapshot === null
      ? []
      : snapshot.companies
          .filter((c) => touched.has(c.symbol) || (snapshot.positions[c.symbol]?.today ?? 0) !== 0)
          .map((c) => ({ symbol: c.symbol, name: c.name, today: snapshot.positions[c.symbol]?.today ?? 0 }))
          .sort((a, b) => b.today - a.today);
  const held =
    snapshot === null
      ? []
      : Object.entries(snapshot.portfolio.holdings)
          .filter(([, h]) => h.shares + h.locked > 0)
          .map(([s, h]) => `${s} ${h.shares + h.locked}`);

  return (
    <div className="app desk">
      <WorldHeader snapshot={snapshot} kind={kind} />
      {tabs}
      {snapshot === null || first === null || company === null ? (
        <StartCard practice={{ ...world, start: startDay }} refresh={world.status} />
      ) : (
        <>
          <AccountStrip snapshot={snapshot} first={first} kind={kind} />
          <Coach played={world.played} ordered={touched.size > 0} holding={held.length > 0} />
          {world.notice && (
            <p className="notice" role="status">
              <span>{world.notice}</span>
              {world.status === "done" && day !== null && (
                <button className="btn small-btn" onClick={() => setDialogOpen(true)}>
                  See how the day went
                </button>
              )}
            </p>
          )}
          <MarketBoard
            snapshot={snapshot}
            selected={symbol}
            onSelect={(s) => {
              setSelected(s);
              setPick(null);
            }}
          />
          <div className="desk-grid">
            <div className="desk-main">
              <label className="toggle">
                <input type="checkbox" checked={world.pauseOnFill} onChange={(e) => world.setPauseOnFill(e.target.checked)} />
                Pause the day when one of my orders trades
              </label>
              <NewsTicker snapshot={snapshot} />
              <PriceChart
                news={snapshot.news}
                symbol={company.name}
                trades={trades}
                state={state}
                durationUs={snapshot.close_at}
                preOpenUs={snapshot.open_at}
                referencePrice={company.instrument.reference_price}
                nowUs={snapshot.now}
                following
                status={world.status}
                speed={world.speed}
                biggest={null}
                practice
                onSeek={() => undefined}
                onLive={() => undefined}
                onReplay={() => undefined}
                onPlayPause={world.togglePause}
                onSpeed={world.setSpeed}
                onAuction={() => undefined}
                onBiggest={() => undefined}
              />
              <IndexChart
                name={snapshot.index_name}
                kind={kind}
                onKind={setKind}
                line={indexLine}
                open={snapshot.indices[kind].open}
                level={snapshot.indices[kind].level}
                nowUs={snapshot.now}
                durationUs={snapshot.close_at}
                preOpenUs={snapshot.open_at}
                news={snapshot.news}
              />
              <Activity
                mine={mine}
                events={events[symbol] ?? []}
                symbol={symbol}
                version={version}
                owner={owner}
                playing={world.status === "playing"}
                tab={tab}
                onTab={setTab}
                panels={{
                  news: <NewsPanel snapshot={snapshot} />,
                  companies: <CompaniesPanel snapshot={snapshot} />,
                  index: <IndexPanel snapshot={snapshot} kind={kind} onKind={setKind} />,
                  statement: <StatementPanel statement={statement} failed={failed} prices={snapshot.prices} />,
                  history: <HistoryPanel days={saved.days} failed={saved.failed} preOpenUs={snapshot.open_at} closeUs={snapshot.close_at} />,
                }}
              />
            </div>
            <aside className="desk-side" aria-label="Trading">
              <OrderTicket
                state={state}
                company={{ symbol, name: company.name, example: ((state.lastPrice ?? company.instrument.reference_price) / 100).toFixed(2) }}
                tickSize={company.instrument.tick_size}
                disabled={world.status === "done" || world.status === "error"}
                refusal={world.refusal}
                pick={pick}
                onPlace={(side, quantity, limit) => world.place(symbol, side, quantity, limit)}
                onClearRefusal={world.clearRefusal}
              />
              <Ladder
                state={state}
                symbol={symbol}
                mine={snapshot.portfolio.open_orders.filter((o) => o.symbol === symbol)}
                onPick={(price) => setPick({ price, nonce: (pick?.nonce ?? 0) + 1 })}
              />
              <OpenOrders orders={snapshot.portfolio.open_orders} onCancel={(s, id) => void world.cancel(s, id)} />
            </aside>
          </div>
          {world.error && (
            <p className="error" role="alert">
              {world.error}
            </p>
          )}
          {day !== null && versus !== null && (
            <DaySummary
              open={dialogOpen}
              seed={snapshot.config.seed}
              result={day}
              companies={companyResults}
              held={held}
              versus={versus.words}
              detail={`You ${sign(versus.you)}, the index ${sign(versus.index)}`}
              days={days}
              standings={[
                { label: "You", percent: day.youPercent, you: true },
                { label: snapshot.index_name, percent: indexPercent(snapshot, kind) },
                ...snapshot.benchmarks.map((b) => ({ label: b.label, percent: b.bp / 100, note: b.note })),
              ].sort((a, b) => b.percent - a.percent)}
              news={snapshot.news.map((n) => ({ headline: headlineOf(n), bp: n.impact_bp }))}
              onClose={() => setDialogOpen(false)}
              onStatement={() => {
                setTab("statement");
                setDialogOpen(false);
              }}
              onNextDay={nextDay}
            />
          )}
          <details className="panel picker">
            <summary>Start a new day</summary>
            <StartCard practice={{ ...world, start: startDay }} again refresh={`${snapshot.id}:${world.status}`} />
          </details>
          <p className="muted small foot-note">
            Day number {snapshot.config.seed}. The same day number gives the same market until you place an order; after that
            the simulated traders react to you. Each day opens at the previous day's closing prices. Charges: {world.plan} All
            prices, companies and people here are made up. Nothing on this page is investment advice.
          </p>
        </>
      )}
    </div>
  );
}
