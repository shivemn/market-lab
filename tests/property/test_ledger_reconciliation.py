"""The ledger rebuilt from a simulated day's log must agree with the log, on many days.

Every simulated trader's trades are recorded in a ledger (the traders have no cash limits, so their accounts
are allowed below zero here). The ledger's positions are then compared with positions worked out directly from
the Trade events by a three-line fold that shares no code with the ledger.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from marketlab.core import Trade
from marketlab.ledger import MARKET_CASH, Ledger, cash_account, market_shares_account, post_trades, shares_account
from marketlab.sim.runner import SimConfig, run_simulation
from tests.helpers import examples


@pytest.mark.parametrize("seed", range(1, examples(25, minimum=2) + 1))
def test_ledger_rebuilt_from_the_log_matches_a_direct_fold_of_the_trades(seed: int) -> None:
    result = run_simulation(SimConfig(seed=seed))
    trades = [e for e in result.events if isinstance(e, Trade)]

    shares: dict[str, int] = defaultdict(int)
    cash: dict[str, int] = defaultdict(int)
    for t in trades:
        shares[t.buy_account_id] += t.quantity
        shares[t.sell_account_id] -= t.quantity
        cash[t.buy_account_id] -= t.price * t.quantity
        cash[t.sell_account_id] += t.price * t.quantity

    ledger = Ledger()
    posted = post_trades(ledger, result.events, source=result.sha256, tracked=lambda _: True, allows_negative=True)

    assert posted == 2 * len(trades)
    assert ledger.verify() == []
    for account in set(shares) | set(cash):
        assert ledger.shares(account, "DEMO1") == shares[account]
        assert ledger.balance(cash_account(account)) == cash[account]
    assert ledger.balance(MARKET_CASH) == 0  # every party is tracked, so the market account is empty
    assert ledger.balance(market_shares_account("DEMO1")) == 0
    assert sum(ledger.balance(shares_account(a, "DEMO1")) for a in shares) == 0


@pytest.mark.parametrize("seed", [3, 11])
def test_feeding_the_log_in_pieces_gives_the_same_ledger_as_all_at_once(seed: int) -> None:
    result = run_simulation(SimConfig(seed=seed))
    all_at_once = Ledger()
    post_trades(all_at_once, result.events, source="r", tracked=lambda _: True, allows_negative=True)

    in_pieces = Ledger()
    cut = len(result.events) // 3
    for chunk in (result.events[:cut], result.events[: 2 * cut], result.events):  # overlapping on purpose
        post_trades(in_pieces, chunk, source="r", tracked=lambda _: True, allows_negative=True)

    assert in_pieces.balances() == all_at_once.balances()
    assert len(in_pieces.transactions()) == len(all_at_once.transactions())
