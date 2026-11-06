import { useLayoutEffect, useRef, useState } from "react";
import type { RunRequest } from "../lib/api";
import { clock } from "../lib/format";
import type { LogLine } from "../lib/narrate";
import { useThrottled } from "../lib/useThrottled";
import type { Status } from "../lib/useRun";

export function StartPanel({ status, onStart, error }: { status: Status; onStart: (r: RunRequest) => void; error: string | null }) {
  const [seed, setSeed] = useState(7);
  const [openSeconds, setOpenSeconds] = useState(600);
  const busy = status === "starting";
  return (
    <details className="card picker">
      <summary>Try a different day</summary>
      <p className="muted small lead">The same day number always gives exactly the same market, so you can share it.</p>
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
        Length of trading
        <select value={openSeconds} onChange={(e) => setOpenSeconds(Number(e.target.value))}>
          <option value={300}>5 minutes</option>
          <option value={600}>10 minutes</option>
          <option value={1800}>30 minutes</option>
        </select>
      </label>
      <button
        className="btn primary big"
        disabled={busy}
        onClick={() => onStart({ seed, open_seconds: openSeconds, pre_open_seconds: 60, noise_traders: 20 })}
      >
        {busy ? "Starting…" : "Start this day"}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}

export function HowToRead() {
  return (
    <section className="howto" aria-label="How to read this page">
      <p>
        <b>The line is the price.</b> Each point is a real trade between one buyer and one seller.
      </p>
      <p>
        <b>The queue explains the line.</b> Buyers and sellers wait in line. A trade happens when they agree on a price.
      </p>
      <p>
        <b>You control time.</b> Press play, or drag along the chart to see the market at any earlier moment.
      </p>
    </section>
  );
}

/**
 * Every line of the day so far, newest first, in a box of fixed size that scrolls. New lines arrive at the top; if you
 * have scrolled down to read, your place is kept instead of jumping.
 */
export function JustHappened({
  lines: live,
  slow = false,
  preOpenUs,
  closeUs,
}: {
  lines: LogLine[];
  slow?: boolean;
  preOpenUs: number;
  closeUs: number;
}) {
  const lines = useThrottled(live, slow ? 1500 : 0); // at high speed the lines change faster than anyone can read
  const box = useRef<HTMLOListElement>(null);
  const height = useRef(0);
  const [away, setAway] = useState(false);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    if (el.scrollTop > 0) el.scrollTop += el.scrollHeight - height.current; // keep the lines you are reading where they were
    height.current = el.scrollHeight;
  }, [lines[0]?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <section className="card grow happened-card" aria-labelledby="happened-title">
      <h2 id="happened-title">What just happened</h2>
      <div className="happened-wrap">
        {lines.length === 0 ? (
          <p className="muted">Nothing yet.</p>
        ) : (
          <ol className="happened" ref={box} tabIndex={0} aria-label="Everything that has happened today, newest first" onScroll={(e) => setAway(e.currentTarget.scrollTop > 60)}>
            {lines.map((line, i) => (
              <li key={line.id} className={i === 0 ? "newest" : ""}>
                <span className="t">{clock(line.at, preOpenUs, closeUs)}</span>
                {line.text}
              </li>
            ))}
          </ol>
        )}
        {away && (
          <button className="btn small-btn to-latest" onClick={() => box.current?.scrollTo({ top: 0, behavior: "smooth" })}>
            Back to the latest
          </button>
        )}
      </div>
    </section>
  );
}
