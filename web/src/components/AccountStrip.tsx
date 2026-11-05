import { percentSigned, rupees, signed } from "../lib/format";
import type { IndexKind, WorldSnapshot } from "../lib/world";
import { compare, indexPercent, sign, worldDay } from "../lib/worldview";

interface Props {
  snapshot: WorldSnapshot;
  first: WorldSnapshot;
  kind: IndexKind;
}

/** The numbers a person checks after every trade, always in view. */
export function AccountStrip({ snapshot, first, kind }: Props) {
  const day = worldDay(first, snapshot);
  const direction = day.result > 0 ? "up" : day.result < 0 ? "down" : "flat";
  const versus = compare(day.youPercent, indexPercent(snapshot, kind), snapshot.index_name);
  const versusDir = Math.abs(versus.gap) < 0.005 ? "flat" : versus.gap > 0 ? "up" : "down";
  const { portfolio } = snapshot;
  const held = Object.values(portfolio.holdings).filter((h) => h.shares + h.locked > 0).length;
  const sharesValue = snapshot.worth - portfolio.cash - portfolio.reserved;
  return (
    <section className="strip" aria-label="Your account">
      <div className="stat lead">
        <span className="k">Worth now</span>
        <span className="v big">{rupees(snapshot.worth)}</span>
        <span className="sub">started the day at {rupees(first.worth)}</span>
      </div>
      <div className="stat">
        <span className="k">Result today</span>
        <span className={`v ${direction}`}>{signed(day.result)}</span>
        <span className="sub">{percentSigned(Math.round(day.result), first.worth)} of your worth</span>
      </div>
      <div className="stat wide">
        <span className="k">Compared with the index</span>
        <span className={`v ${versusDir}`}>{versus.words.replace(`${snapshot.index_name}`, "the index")}</span>
        <span className="sub">
          you {sign(versus.you)} · index {sign(versus.index)}
        </span>
      </div>
      <div className="stat">
        <span className="k">Cash to use</span>
        <span className="v">{rupees(portfolio.cash)}</span>
        <span className="sub">{portfolio.reserved > 0 ? `${rupees(portfolio.reserved)} held for orders` : ""}</span>
      </div>
      <div className="stat">
        <span className="k">In shares</span>
        <span className="v">{rupees(sharesValue)}</span>
        <span className="sub">{held === 0 ? "no company yet" : `in ${held} ${held === 1 ? "company" : "companies"}`}</span>
      </div>
      <div className="stat">
        <span className="k">Charges paid</span>
        <span className="v">{rupees(snapshot.total_charges)}</span>
        <span className="sub"> </span>
      </div>
    </section>
  );
}
