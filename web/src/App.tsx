import { useEffect, useMemo, useState } from "react";
import { Header } from "./components/Header";
import { Queue } from "./components/Queue";
import { AuctionView } from "./components/AuctionView";
import { PriceChart } from "./components/PriceChart";
import { PracticeView } from "./components/PracticeView";
import { HowToRead, JustHappened, StartPanel } from "./components/Side";
import { fold } from "./lib/market";
import { narrate } from "./lib/narrate";
import { biggestMove, endTimes, lastEndAtOrBefore, priceSeries, tradeSeries } from "./lib/series";
import { COMPANIES } from "./lib/companies";
import { useRun } from "./lib/useRun";

export default function App() {
  const run = useRun();
  const { events, ends, version, summary } = run;
  const [cursor, setCursor] = useState<number | null>(null); // index into ends; null means "the latest moment"
  const [followed, setFollowed] = useState<number | null>(null);
  const [view, setView] = useState<"day" | "auction" | "practice">("day");
  const { start } = run;
  const [company, setCompany] = useState("UDHAAR");

  useEffect(() => {
    void start({ seed: 7, open_seconds: 600, pre_open_seconds: 60, noise_traders: 20, company: "UDHAAR" });
  }, [start]);

  const pickCompany = (symbol: string) => {
    setCompany(symbol);
    setCursor(null);
    setFollowed(null);
    const config = summary?.config;
    void start({
      seed: config?.seed ?? 7,
      open_seconds: config?.open_seconds ?? 600,
      pre_open_seconds: config?.pre_open_seconds ?? 60,
      noise_traders: config?.noise_traders ?? 20,
      company: symbol,
    });
  };

  const latest = ends.length - 1;
  const position = cursor === null ? latest : Math.min(cursor, latest);
  const count = position >= 0 ? ends[position] : 0;
  const following = cursor === null;

  const state = useMemo(() => fold(events, count), [version, count]);
  const times = useMemo(() => endTimes(events, ends), [version]);
  const duration = summary?.duration_us ?? 1;
  const trades = useMemo(() => tradeSeries(events), [version]);
  const series = useMemo(() => priceSeries(events, Math.max(duration / 300, 1)), [version, duration]);
  const biggest = useMemo(() => biggestMove(series, 10_000_000), [series]);
  const lines = useMemo(() => narrate(events, ends, count, 4, undefined, summary?.instrument.symbol), [events, ends, count, version]);
  const nowUs = position >= 0 ? times[position] ?? 0 : 0;

  const seek = (timeUs: number) => {
    const index = lastEndAtOrBefore(times, timeUs);
    setCursor(index >= latest ? null : Math.max(index, 0));
  };
  const jumpTo = (timeUs: number) => setCursor(Math.max(0, lastEndAtOrBefore(times, timeUs)));

  const goAuction = () => {
    const at = events.findIndex((e) => e.type === "AuctionResult");
    if (at >= 0) jumpTo(events[at].sim_time);
  };

  const tabs = (
    <nav className="tabs" aria-label="Screens">
      <button className={`tab${view === "day" ? " on" : ""}`} aria-pressed={view === "day"} onClick={() => setView("day")}>
        Watch a day
      </button>
      <button className={`tab${view === "auction" ? " on" : ""}`} aria-pressed={view === "auction"} onClick={() => setView("auction")}>
        Opening auction
      </button>
      <button className={`tab${view === "practice" ? " on" : ""}`} aria-pressed={view === "practice"} onClick={() => setView("practice")}>
        Practice
      </button>
    </nav>
  );

  // The practice screen is only hidden, never closed, so a day in progress (and its history) is still there when you come back.
  const [visitedPractice, setVisitedPractice] = useState(false);
  useEffect(() => {
    if (view === "practice") setVisitedPractice(true);
  }, [view]);
  const practice = visitedPractice || view === "practice" ? (
    <div hidden={view !== "practice"}>
      <PracticeView tabs={tabs} active={view === "practice"} />
    </div>
  ) : null;
  if (view === "practice") return practice;

  return (
    <>
    {practice}
    <div className="app">
      <Header state={state} summary={summary} />
      {tabs}
      <label className="company-pick">
        Company to watch
        <select value={company} onChange={(e) => pickCompany(e.target.value)}>
          {COMPANIES.map((c) => (
            <option key={c.symbol} value={c.symbol}>
              {c.symbol} · {c.name}
            </option>
          ))}
        </select>
      </label>
      <p className="lesson" role="note">
        {view === "auction"
          ? "A lesson, not your account. Before 9:15 the exchange does not trade one order at a time. It collects orders for 15 minutes, then finds the single price at which the most shares can change hands, and everyone matched gets that price. That price is where the day opens. Here is how it is worked out for the company you chose."
          : "A lesson, not your account. This replays the one company you choose above, and shows the queue of buyers and sellers behind every price. Nothing you do here uses your money. To trade across all twelve companies, go to Practice."}
      </p>
      {view === "auction" ? (
        <AuctionView events={events} version={version} instrument={summary?.instrument ?? null} onBack={() => setView("day")} />
      ) : (
        <>
      <HowToRead />
      <PriceChart
        symbol={summary?.instrument.symbol ?? "UDHAAR"}
        trades={trades}
        state={state}
        durationUs={duration}
        preOpenUs={(summary?.config.pre_open_seconds ?? 60) * 1_000_000}
        referencePrice={summary?.instrument.reference_price ?? 250_000}
        nowUs={nowUs}
        following={following}
        status={run.status}
        speed={run.speed}
        biggest={biggest}
        onSeek={seek}
        onLive={() => setCursor(null)}
        onReplay={() => {
          if (!summary) return;
          setCursor(null);
          setFollowed(null);
          void run.start({
            seed: summary.config.seed,
            open_seconds: summary.config.open_seconds,
            pre_open_seconds: summary.config.pre_open_seconds,
            noise_traders: summary.config.noise_traders,
            company,
          });
        }}
        onPlayPause={run.togglePause}
        onSpeed={run.setSpeed}
        onAuction={goAuction}
        onBiggest={() => biggest && jumpTo(biggest.to.t)}
      />
      <main className="main">
        <Queue state={state} followed={followed} onFollow={setFollowed} symbol={summary?.instrument.symbol} />
        <JustHappened lines={lines} slow={run.status === "playing"} />
      </main>
        </>
      )}
      <footer className="foot">
        <StartPanel
          status={run.status}
          error={run.error}
          onStart={(request) => {
            setCursor(null);
            setFollowed(null);
            void run.start({ ...request, company });
          }}
        />
        {summary && (
          <p className="muted small" title={summary.sha256}>
            Day number {summary.config.seed}. Fingerprint {summary.sha256.slice(0, 8)}: the same day number always
            gives exactly this market. All prices and people here are simulated. Nothing on this page is investment
            advice.
          </p>
        )}
      </footer>
    </div>
    </>
  );
}
