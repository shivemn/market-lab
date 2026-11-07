import { ReactNode, useMemo, useState } from "react";
import { percentSigned, points, pointsSigned } from "../lib/format";
import { clock } from "../lib/format";
import { SPEEDS } from "../lib/useRun";
import { lineRange } from "../lib/series";
import { useIndexLine } from "../lib/useIndexLine";
import type { IndexKind } from "../lib/world";
import { INDEX_KINDS } from "../lib/world";
import { INDEX_TEXT } from "../lib/worldview";
import { IndexChart } from "./IndexChart";
import { IndexPanel } from "./IndexPanel";
import { NewsPanel } from "./NewsPanel";
import { Practice, StartCard } from "./PracticeView";
import { WorldHeader } from "./WorldHeader";

type Which = "twelve" | "seven";
const WEIGHTINGS = INDEX_KINDS.filter((k) => k !== "top");

const direction = (n: number) => (n === 0 ? "flat" : n > 0 ? "up" : "down");
const move = (change: number, open: number) =>
  change === 0 ? "unchanged" : `${change > 0 ? "▲" : "▼"} ${pointsSigned(change)} (${percentSigned(change, open)})`;

/**
 * A page only about the two indices: Shifty 12 (the Nifty 50 kind of index) and Shifty 7 (the Sensex kind), drawn from
 * the same market as the practice day. The day is shared with the Practice screen: press play here or there. Leaving
 * for another screen pauses it (the Practice screen, which stays mounted, does that).
 */
export function IndicesView({ tabs, world }: { tabs: ReactNode; world: Practice }) {
  const { snapshot, events, version, factors, status, speed } = world;
  const [which, setWhich] = useState<Which>("twelve");
  const [weighting, setWeighting] = useState<IndexKind>("cap");
  const kind: IndexKind = which === "seven" ? "top" : weighting;
  const line = useIndexLine(events, version, factors, snapshot, kind);

  const range = useMemo(() => lineRange(line), [line]);

  if (snapshot === null) {
    return (
      <div className="app desk">
        <WorldHeader snapshot={null} kind={kind} />
        {tabs}
        <section className="card" aria-labelledby="indices-intro">
          <h2 id="indices-intro">The two indices</h2>
          <p className="muted lead">
            An index is one number that stands for a whole market. <b>Shifty 12</b> counts all twelve companies, like the
            Nifty 50 counts fifty. <b>Shifty 7</b> counts only the seven biggest, like the Sensex counts the biggest thirty.
            They move on the same simulated day. Start a day to watch both.
          </p>
        </section>
        <StartCard practice={world} refresh={status} />
      </div>
    );
  }

  const twelve = snapshot.indices[weighting];
  const seven = snapshot.indices.top;
  const view = snapshot.indices[kind];
  const playing = status === "playing";
  const canPause = status === "playing" || status === "paused";

  const controls = (
    <div className="controls">
      <button className="round" onClick={world.togglePause} disabled={!canPause} aria-label={playing ? "Pause" : "Play"}>
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
          {playing ? <path d="M3 2h4v12H3zM9 2h4v12H9z" fill="currentColor" /> : <path d="M4 2 L14 8 L4 14 Z" fill="currentColor" />}
        </svg>
      </button>
      <button
        className="btn"
        onClick={() => world.setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length])}
        aria-label={`Playback speed ${speed} times. Select to change.`}
      >
        {speed}×
      </button>
    </div>
  );

  const card = (id: Which, title: string, subtitle: string, v: { level: number; open: number; change: number }) => (
    <button
      key={id}
      type="button"
      className={`index-card${which === id ? " on" : ""}`}
      aria-pressed={which === id}
      onClick={() => setWhich(id)}
    >
      <span className="index-card-name">{title}</span>
      <span className="index-card-sub">{subtitle}</span>
      <span className="index-card-level">{points(v.level)}</span>
      <span className={`change ${direction(v.change)}`}>{move(v.change, v.open)}</span>
    </button>
  );

  return (
    <div className="app desk">
      <WorldHeader snapshot={snapshot} kind={kind} />
      {tabs}
      <div className="index-picker" role="group" aria-label="Which index to look at">
        {card("twelve", "Shifty 12", "All twelve companies, like the Nifty 50", twelve)}
        {card("seven", "Shifty 7", "The seven biggest only, like the Sensex", seven)}
      </div>
      {which === "twelve" && (
        <div className="seg quiet weighting" role="group" aria-label="How Shifty 12 is worked out">
          {WEIGHTINGS.map((k) => (
            <button key={k} type="button" className={k === weighting ? "on" : ""} aria-pressed={k === weighting} onClick={() => setWeighting(k)}>
              {INDEX_TEXT[k].name}
            </button>
          ))}
        </div>
      )}
      {world.notice && (
        <p className="notice" role="status">
          <span>{world.notice}</span>
        </p>
      )}
      <IndexChart
        name={which === "seven" ? "Shifty 7" : "Shifty 12"}
        kind={kind}
        onKind={setWeighting}
        line={line}
        open={view.open}
        level={view.level}
        nowUs={snapshot.now}
        durationUs={snapshot.close_at}
        preOpenUs={snapshot.open_at}
        news={snapshot.news}
        height={360}
        showKinds={false}
        controls={controls}
      />
      <dl className="chart-stats index-stats" aria-label="Level, high and low so far">
        <div>
          <dt>Now ({clock(snapshot.now, snapshot.open_at, snapshot.close_at)})</dt>
          <dd>{points(view.level)}</dd>
        </div>
        <div>
          <dt>Yesterday's close</dt>
          <dd>{points(view.open)}</dd>
        </div>
        <div>
          <dt>High so far</dt>
          <dd>{range === null ? "–" : points(Math.max(range.high, view.open))}</dd>
        </div>
        <div>
          <dt>Low so far</dt>
          <dd>{range === null ? "–" : points(Math.min(range.low, view.open))}</dd>
        </div>
      </dl>
      <section className="panel" aria-labelledby="index-how">
        <h2 id="index-how" className="sr-only">
          How this index is worked out and what moved it
        </h2>
        <IndexPanel snapshot={snapshot} kind={kind} onKind={setWeighting} showKinds={false} />
      </section>
      {which === "twelve" && (
        <section className="panel" aria-labelledby="sectors-title">
          <h2 id="sectors-title">The four sectors inside Shifty 12</h2>
          <div className="table-scroll" tabIndex={0}>
            <table className="statement">
              <caption className="sr-only">Each sector's own index</caption>
              <thead>
                <tr>
                  <th scope="col">Sector</th>
                  <th scope="col">Level</th>
                  <th scope="col">Today</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.sectors.map((s) => {
                  const v = snapshot.indices.sectors[s.key];
                  return (
                    <tr key={s.key}>
                      <td>{s.label}</td>
                      <td>{points(v.level)}</td>
                      <td className={direction(v.change)}>{move(v.change, v.open)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="panel" aria-labelledby="news-title">
        <h2 id="news-title">News that moved the market</h2>
        <NewsPanel snapshot={snapshot} />
      </section>
      <p className="muted small foot-note">
        Day number {snapshot.config.seed}. Both indices come from the same twelve made-up companies and the same day. Nothing
        on this page is investment advice.
      </p>
    </div>
  );
}
