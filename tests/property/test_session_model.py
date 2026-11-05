"""Random sessions: a person acts at random moments in a random day, and everything must hold together.

After every action the ledger agrees with the gateway and the exchange's book. At the end, replaying the day from
its seed and the commands that were sent gives the same fingerprint, and a ledger rebuilt from the replayed log
alone equals the one built live.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from marketlab.core import Side, TimeInForce
from marketlab.ledger import Ledger, OrderRefused, locked_account, post_trades, reserved_account
from marketlab.session import PracticeSession, replay
from marketlab.sim import SimConfig

side = st.sampled_from([Side.BUY, Side.SELL])
action = st.one_of(
    st.tuples(st.just("advance"), st.floats(min_value=0.0, max_value=6.0)),
    st.tuples(
        st.just("limit"),
        side,
        st.integers(min_value=-12, max_value=12),
        st.integers(min_value=1, max_value=20),
        st.sampled_from([TimeInForce.DAY, TimeInForce.IOC]),
    ),
    st.tuples(st.just("market"), side, st.integers(min_value=1, max_value=20)),
    st.tuples(st.just("cancel"), st.integers(min_value=0, max_value=20)),
)


def nonzero(ledger: Ledger) -> dict[str, int]:
    return {a: b for a, b in ledger.balances().items() if b != 0}


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=40),
    actions=st.lists(action, max_size=25),
    plan=st.sampled_from(["zero", "flat20"]),
)
def test_random_sessions_stay_consistent_and_replay_exactly(seed: int, actions: list[Any], plan: str) -> None:
    config = SimConfig(seed=seed, open_seconds=25, pre_open_seconds=5, noise_traders=5)
    ledger = Ledger()
    session = PracticeSession(config, ledger, "you", plan=plan, trading_date=date(2026, 11, 1))
    ledger.grant_shares("you", "DEMO1", 40)
    tick = session.sim.instrument.tick_size
    reference = session.sim.instrument.reference_price

    for act in actions:
        if session.finished:
            break
        kind = act[0]
        try:
            if kind == "advance":
                session.advance(act[1])
            elif kind == "limit":
                session.place(act[1], act[3], limit_price=reference + act[2] * tick, tif=act[4])
            elif kind == "market":
                session.place(act[1], act[2])
            else:
                live = session.gateway.open_order_ids()
                if live:
                    session.cancel(live[act[1] % len(live)])
        except OrderRefused:
            pass
        folio = session.portfolio()
        assert ledger.balance(reserved_account("you")) == session.gateway.reserved_cash() == folio.reserved
        assert ledger.balance(locked_account("you", "DEMO1")) == session.gateway.locked_shares() == folio.locked
        assert {o.order_id for o in folio.open_orders} == set(session.gateway.open_order_ids())
        assert all(0 < o.remaining <= o.quantity for o in folio.open_orders)
        assert ledger.verify() == []

    session.advance(10_000, pause_on_fill=False)
    assert session.finished
    folio = session.portfolio()
    assert (folio.reserved, folio.locked, folio.open_orders) == (0, 0, ())

    again = replay(session)
    assert again.result().sha256 == session.fingerprint()

    rebuilt = Ledger()
    rebuilt.open_account("you")
    rebuilt.grant_shares("you", "DEMO1", 40)
    post_trades(rebuilt, again.events, source="day", tracked=lambda a: a == "you", costs=session.costs)
    assert nonzero(ledger) == nonzero(rebuilt)
