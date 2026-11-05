import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { dayResult } from "../lib/dayresult";
import { fold } from "../lib/market";
import { PlanName, StartRequest } from "../lib/practice";
import { tradeSeries } from "../lib/series";
import { usePractice } from "../lib/usePractice";
import { useStatement } from "../lib/useStatement";
import { AccountStrip } from "./AccountStrip";
import { Activity } from "./Activity";
import { DaySummary, PastDay } from "./DaySummary";
import { Header } from "./Header";
import { Ladder } from "./Ladder";
import { OpenOrders } from "./OpenOrders";
import { OrderTicket } from "./OrderTicket";
import { PriceChart } from "./PriceChart";

type Practice = ReturnType<typeof usePractice>;

function StartCard({ practice, again }: { practice: Practice; again?: boolean }) {
  const [owner, setOwner] = useState("you");
  const [seed, setSeed] = useState(7);
  const [plan, setPlan] = useState<PlanName>("zero");
  const valid = /^[A-Za-z0-9_-]{1,32}$/.test(owner);
  return (
    <section className="card picker" aria-labelledby="start-title">
      <h2 id="start-title">{again ? "Start a new practice day" : "Practice with pretend money"}</h2>
      <p className="muted lead">
        {again
          ? "Your cash and shares carry over. Orders still waiting are returned first."
          : "You start with ₹1,00,000 of pretend money. Place orders, watch them meet the market, and see every tax and charge a real investor would pay. Nothing here is real or advice."}
      </p>
      <label className="field">
        Your name for the account (letters and numbers)
        <input value={owner} onChange={(e) => setOwner(e.target.value)} aria-invalid={!valid} />
      </label>
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
    </section>
  );
}

const COACH_KEY = "marketlab-coach-dismissed";

function Coach() {
  const [hidden, setHidden] = useState(() => {
    try {
      return window.localStorage.getItem(COACH_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (hidden) return null;
  return (
    <div className="coach" role="note">
      <span>
        <b>1</b> Press play. <b>2</b> Choose buy or sell and a number of shares. <b>3</b> Watch the ladder, your orders and
        your account on the right and below.
      </span>
      <button
        className="btn small-btn"
        onClick={() => {
          setHidden(true);
          try {
            window.localStorage.setItem(COACH_KEY, "1");
          } catch {
            // it just comes back next visit
          }
        }}
      >
        Got it
      </button>
    </div>
  );
}

export function PracticeView({ tabs }: { tabs: ReactNode }) {
  const practice = usePractice();
  const { events, ends, version, session, portfolio } = practice;
  const [pick, setPick] = useState<{ price: number; nonce: number } | null>(null);
  const state = useMemo(() => fold(events), [version]);
  const trades = useMemo(() => tradeSeries(events), [version]);
  const stamp = portfolio === null ? "" : [portfolio.cash, portfolio.reserved, portfolio.shares, portfolio.locked].join(":");
  const { statement, failed } = useStatement(session?.id ?? null, stamp);
  const [tab, setTab] = useState<"activity" | "statement">("activity");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [days, setDays] = useState<PastDay[]>([]);
  const lastRequest = useRef<StartRequest | null>(null);
  const chargesBefore = useRef<{ id: string; charges: number } | null>(null);
  const summarised = useRef<string | null>(null);
  // Shares carried into a new day are valued at where the last day left them, so the days add up to the whole result.
  const lastClose = useRef<number | null>(null);
  const startPrice = useRef<{ id: string; price: number } | null>(null);
  useEffect(() => {
    if (session !== null && startPrice.current?.id !== session.id) {
      startPrice.current = { id: session.id, price: lastClose.current ?? session.instrument.reference_price };
    }
  }, [session?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const dayStartPrice =
    session !== null && startPrice.current?.id === session.id ? startPrice.current.price : session?.instrument.reference_price ?? 0;

  // the charges the account had paid before this day, so the day's own charges can be told apart
  useEffect(() => {
    if (statement !== null && session !== null && chargesBefore.current?.id !== session.id) {
      chargesBefore.current = { id: session.id, charges: statement.total_charges };
    }
  }, [statement, session?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const today =
    session !== null && portfolio !== null && practice.startPortfolio !== null && statement !== null && chargesBefore.current !== null
      ? dayResult(
          practice.startPortfolio,
          portfolio,
          dayStartPrice,
          state.lastPrice,
          statement.total_charges - chargesBefore.current.charges,
        )
      : null;

  // when the market closes, say how the day went (once the statement has caught up with the final balances)
  useEffect(() => {
    if (practice.status !== "done" || session === null || portfolio === null || statement === null || today === null) return;
    if (summarised.current === session.id || statement.money !== portfolio.cash + portfolio.reserved) return;
    summarised.current = session.id;
    setDays((list) => [...list, { seed: session.config.seed, result: today.result }]);
    setDialogOpen(true);
  }, [practice.status, session?.id, statement, portfolio]); // eslint-disable-line react-hooks/exhaustive-deps

  const startDay = (request: StartRequest) => {
    lastRequest.current = request;
    lastClose.current = session === null ? null : (state.lastPrice ?? dayStartPrice);
    return practice.start(request);
  };
  const nextDay = () => {
    if (session === null) return;
    const last = lastRequest.current ?? { owner: session.owner, seed: session.config.seed, plan: "zero" as PlanName };
    setDialogOpen(false);
    void startDay({ ...last, seed: last.seed + 1 });
  };

  return (
    <div className="app desk">
      <Header state={state} summary={session} />
      {tabs}
      {session === null || portfolio === null ? (
        <StartCard practice={{ ...practice, start: startDay }} />
      ) : (
        <>
          <AccountStrip
            portfolio={portfolio}
            start={practice.startPortfolio}
            statement={statement}
            lastPrice={state.lastPrice}
            previousClose={dayStartPrice}
            symbol={session.instrument.symbol}
          />
          <Coach />
          {practice.notice && (
            <p className="notice" role="status">
              <span>{practice.notice}</span>
              {practice.status === "done" && today !== null && (
                <button className="btn small-btn" onClick={() => setDialogOpen(true)}>
                  See how the day went
                </button>
              )}
            </p>
          )}
          <div className="desk-grid">
            <div className="desk-main">
              <PriceChart
                symbol={session.instrument.symbol}
                trades={trades}
                state={state}
                durationUs={session.close_at}
                preOpenUs={session.open_at}
                referencePrice={session.instrument.reference_price}
                nowUs={practice.now}
                following
                status={practice.status}
                speed={practice.speed}
                biggest={null}
                practice
                onSeek={() => undefined}
                onLive={() => undefined}
                onReplay={() => undefined}
                onPlayPause={practice.togglePause}
                onSpeed={practice.setSpeed}
                onAuction={() => undefined}
                onBiggest={() => undefined}
              />
              <Activity
                events={events}
                ends={ends}
                version={version}
                owner={session.owner}
                playing={practice.status === "playing"}
                statement={statement}
                statementFailed={failed}
                lastPrice={state.lastPrice}
                tab={tab}
                onTab={setTab}
              />
            </div>
            <aside className="desk-side" aria-label="Trading">
              <OrderTicket
                state={state}
                tickSize={session.instrument.tick_size}
                disabled={practice.status === "done" || practice.status === "error"}
                refusal={practice.refusal}
                pick={pick}
                onPlace={practice.place}
                onClearRefusal={practice.clearRefusal}
              />
              <Ladder state={state} mine={portfolio.open_orders} onPick={(price) => setPick({ price, nonce: (pick?.nonce ?? 0) + 1 })} />
              <OpenOrders orders={portfolio.open_orders} onCancel={(id) => void practice.cancel(id)} />
            </aside>
          </div>
          {practice.error && (
            <p className="error" role="alert">
              {practice.error}
            </p>
          )}
          {today !== null && (
            <DaySummary
              open={dialogOpen}
              seed={session.config.seed}
              symbol={session.instrument.symbol}
              result={today}
              held={portfolio.shares + portfolio.locked}
              lastPrice={state.lastPrice ?? session.instrument.reference_price}
              days={days}
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
            <StartCard practice={{ ...practice, start: startDay }} again />
          </details>
          <p className="muted small foot-note">
            Day number {session.config.seed}. The same day number gives the same market until you place an order; after that
            the simulated traders react to you. Charges: {session.plan} All prices and people here are simulated. Nothing on
            this page is investment advice.
          </p>
        </>
      )}
    </div>
  );
}
