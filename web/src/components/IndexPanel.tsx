import { percentSigned, points, pointsSigned, rupees } from "../lib/format";
import { IndexKind, INDEX_KINDS, WorldSnapshot } from "../lib/world";
import { INDEX_TEXT } from "../lib/worldview";

interface Props {
  snapshot: WorldSnapshot;
  kind: IndexKind;
  onKind: (kind: IndexKind) => void;
  showKinds?: boolean; // false where the page already has its own switch
}

/** How the index is built, and which companies moved it today. */
export function IndexPanel({ snapshot, kind, onKind, showKinds = true }: Props) {
  const view = snapshot.indices[kind];
  const biggest = Math.max(1, ...Object.values(view.members).map((m) => Math.abs(m.points)));
  return (
    <div className="index-wrap">
      {showKinds && (
        <div className="seg quiet" role="group" aria-label="How the index is worked out">
          {INDEX_KINDS.map((k) => (
            <button key={k} type="button" className={k === kind ? "on" : ""} aria-pressed={k === kind} onClick={() => onKind(k)}>
              {INDEX_TEXT[k].name}
            </button>
          ))}
        </div>
      )}
      <p className="muted small how">{INDEX_TEXT[kind].how}</p>
      <p className="muted small how">
        The level is the sum of (price × shares counted) divided by a fixed number called the divisor, set so the index
        started at {kind === "top" ? "100" : "1,000"}. The divisor only changes when something other than a price changes, such as a share split.
      </p>
      <div className="table-scroll" tabIndex={0}>
        <table className="statement index-table">
          <caption className="sr-only">What each company added to the index today</caption>
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Price</th>
              <th scope="col">Share of the index</th>
              <th scope="col">Points added today</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.companies.map((c) => {
              const m = view.members[c.symbol];
              if (m === undefined) {
                return (
                  <tr key={c.symbol} className="outside">
                    <td>
                      <b>{c.symbol}</b> <span className="muted small">{c.name}</span>
                    </td>
                    <td>{rupees(snapshot.prices[c.symbol])}</td>
                    <td className="muted" colSpan={2}>
                      Not in this index
                    </td>
                  </tr>
                );
              }
              const dir = m.points === 0 ? "flat" : m.points > 0 ? "up" : "down";
              return (
                <tr key={c.symbol}>
                  <td>
                    <b>{c.symbol}</b> <span className="muted small">{c.name}</span>
                  </td>
                  <td>{rupees(snapshot.prices[c.symbol])}</td>
                  <td>{(m.weight_bp / 100).toFixed(1)}%</td>
                  <td className="contrib">
                    <span className={`bar2 ${dir}`} style={{ width: `${(Math.abs(m.points) / biggest) * 100}%` }} aria-hidden="true" />
                    <span className={dir}>{pointsSigned(m.points)}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={3}>
                {view.name}: {points(view.open)} at yesterday's close, {points(view.level)} now
              </th>
              <td>
                <b>
                  {pointsSigned(view.change)} ({percentSigned(view.change, view.open)})
                </b>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
