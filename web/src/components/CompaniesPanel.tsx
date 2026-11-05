import { rupees, signed } from "../lib/format";
import type { WorldSnapshot } from "../lib/world";

/** How each company has done for you: profit locked in by selling, profit on paper, charges, and the net. */
export function CompaniesPanel({ snapshot }: { snapshot: WorldSnapshot }) {
  const rows = snapshot.companies.filter((c) => {
    const p = snapshot.positions[c.symbol];
    return p !== undefined && (p.bought > 0 || p.sold > 0);
  });
  if (rows.length === 0) {
    return <p className="muted small">No trades yet. After you trade, each company you have dealt in gets a line here.</p>;
  }
  const total = rows.reduce(
    (t, c) => {
      const p = snapshot.positions[c.symbol];
      return { net: t.net + p.net, today: t.today + p.today, charges: t.charges + p.charges };
    },
    { net: 0, today: 0, charges: 0 },
  );
  const cls = (n: number) => (n > 0 ? "up" : n < 0 ? "down" : "");
  return (
    <div className="statement-wrap">
      <p className="muted small how">
        <b>Locked in</b> is profit or loss from shares you have sold. <b>On paper</b> is profit or loss on shares you still hold,
        at today's price: it is not yours until you sell. Cost per share is the average of everything you bought.
      </p>
      <div className="table-scroll" tabIndex={0}>
        <table className="statement">
          <caption className="sr-only">Your result in each company</caption>
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Shares</th>
              <th scope="col">Average cost</th>
              <th scope="col">Price now</th>
              <th scope="col">Locked in</th>
              <th scope="col">On paper</th>
              <th scope="col">Charges</th>
              <th scope="col">Net result</th>
              <th scope="col">Today</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const p = snapshot.positions[c.symbol];
              return (
                <tr key={c.symbol}>
                  <td>
                    <b>{c.symbol}</b> <span className="muted small">{c.name}</span>
                  </td>
                  <td>{p.shares}</td>
                  <td>{p.shares > 0 ? rupees(p.average_cost) : "–"}</td>
                  <td>{rupees(snapshot.prices[c.symbol])}</td>
                  <td className={cls(p.realised)}>{p.sold > 0 ? signed(p.realised) : "–"}</td>
                  <td className={cls(p.unrealised)}>{p.shares > 0 ? signed(p.unrealised) : "–"}</td>
                  <td>{p.charges > 0 ? rupees(p.charges) : "–"}</td>
                  <td className={cls(p.net)}>
                    <b>{signed(p.net)}</b>
                  </td>
                  <td className={cls(p.today)}>{signed(p.today)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={6}>
                All companies
              </th>
              <td>{rupees(total.charges)}</td>
              <td className={cls(total.net)}>
                <b>{signed(total.net)}</b>
              </td>
              <td className={cls(total.today)}>{signed(total.today)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
