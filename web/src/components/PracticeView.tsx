import { ReactNode, useMemo, useState } from "react";
import { fold } from "../lib/market";
import { narrate } from "../lib/narrate";
import { PlanName } from "../lib/practice";
import { tradeSeries } from "../lib/series";
import { usePractice } from "../lib/usePractice";
import { Header } from "./Header";
import { OrderTicket } from "./OrderTicket";
import { PortfolioPanel } from "./PortfolioPanel";
import { PriceChart } from "./PriceChart";
import { Queue } from "./Queue";
import { JustHappened } from "./Side";

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
          ? "Your cash and shares carry over to the new day. Anything still waiting in an open order is returned first."
          : "You start with ₹1,00,000 of pretend money. Watch the queue, place orders, and see exactly what each trade costs you, including the taxes and charges a real investor pays. Nothing here is real, and nothing is advice."}
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

export function PracticeView({ tabs }: { tabs: ReactNode }) {
  const practice = usePractice();
  const { events, ends, version, session, portfolio } = practice;
  const [followed, setFollowed] = useState<number | null>(null);
  const state = useMemo(() => fold(events), [version]);
  const trades = useMemo(() => tradeSeries(events), [version]);
  const lines = useMemo(() => narrate(events, ends, events.length, 4, session?.owner), [version, session]);

  return (
    <div className="app">
      <Header state={state} summary={session} />
      {tabs}
      {session === null || portfolio === null ? (
        <StartCard practice={practice} />
      ) : (
        <>
          {practice.notice && (
            <p className="notice" role="status">
              {practice.notice}
            </p>
          )}
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
          <main className="main">
            <div className="stack">
              <Queue state={state} followed={followed} onFollow={setFollowed} mine={session.owner} />
              <JustHappened lines={lines} />
            </div>
            <div className="stack">
              <OrderTicket
                state={state}
                tickSize={session.instrument.tick_size}
                disabled={practice.status === "done" || practice.status === "error"}
                refusal={practice.refusal}
                onPlace={practice.place}
                onClearRefusal={practice.clearRefusal}
              />
              <PortfolioPanel
                portfolio={portfolio}
                start={practice.startPortfolio}
                lastPrice={state.lastPrice}
                symbol={session.instrument.symbol}
                onCancel={(id) => void practice.cancel(id)}
              />
            </div>
          </main>
          {practice.error && (
            <p className="error" role="alert">
              {practice.error}
            </p>
          )}
          <details className="card picker">
            <summary>Start a new day</summary>
            <StartCard practice={practice} again />
          </details>
          <p className="muted small">
            Day number {session.config.seed}. The same day number gives the same market until you place an order; after
            that the simulated traders react to you. Charges: {session.plan} All prices and people here are simulated.
            Nothing on this page is investment advice.
          </p>
        </>
      )}
    </div>
  );
}
