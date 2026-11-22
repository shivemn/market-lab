import { percentSigned, rupees, signed } from "../lib/format";
import type { IndexKind, WorldSnapshot } from "../lib/world";
import { Kpi } from "../ui";
import { compare, indexPercent, indexTitle, sign, worldDay } from "../lib/worldview";

interface Props {
  snapshot: WorldSnapshot;
  first: WorldSnapshot;
  kind: IndexKind;
}

/** The numbers a person checks after every trade, always in view. */
export function AccountStrip({ snapshot, first, kind }: Props) {
  const day = worldDay(first, snapshot);
  const direction = day.result > 0 ? "up" : day.result < 0 ? "down" : "flat";
  const versus = compare(day.youPercent, indexPercent(snapshot, kind), indexTitle(snapshot, kind));
  const versusDir = Math.abs(versus.gap) < 0.005 ? "flat" : versus.gap > 0 ? "up" : "down";
  const { portfolio } = snapshot;
  const held = Object.values(portfolio.holdings).filter((h) => h.shares + h.locked > 0).length;
  const sharesValue = snapshot.worth - portfolio.cash - portfolio.reserved;
  return (
    <section className="strip" aria-label="Your account">
      <Kpi className="lead" label="Worth now" value={rupees(snapshot.worth)} big note={`started the day at ${rupees(first.worth)}`} />
      <Kpi label="Result today" value={signed(day.result)} tone={direction} note={`${percentSigned(Math.round(day.result), first.worth)} of your worth`} />
      <Kpi
        className="wide"
        label="Compared with the index"
        value={versus.words.replace(indexTitle(snapshot, kind), "the index")}
        tone={versusDir}
        note={`you ${sign(versus.you)} · index ${sign(versus.index)}`}
      />
      <Kpi label="Cash to use" value={rupees(portfolio.cash)} note={portfolio.reserved > 0 ? `${rupees(portfolio.reserved)} held for orders` : ""} />
      <Kpi label="In shares" value={rupees(sharesValue)} note={held === 0 ? "no company yet" : `in ${held} ${held === 1 ? "company" : "companies"}`} />
      <Kpi label="Charges paid" value={rupees(snapshot.total_charges)} note=" " />
    </section>
  );
}
