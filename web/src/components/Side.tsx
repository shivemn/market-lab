import { useState } from "react";
import type { RunRequest } from "../lib/api";
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

export function JustHappened({ lines: live, slow = false }: { lines: string[]; slow?: boolean }) {
  const lines = useThrottled(live, slow ? 1500 : 0); // at high speed the lines change faster than anyone can read
  return (
    <section className="card grow" aria-labelledby="happened-title">
      <h2 id="happened-title">What just happened</h2>
      {lines.length === 0 ? (
        <p className="muted">Nothing yet.</p>
      ) : (
        <ol className="happened">
          {lines.map((line, i) => (
            <li key={`${i}-${line}`} className={i === 0 ? "newest" : ""}>
              {line}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
