"""Trades from the exchange become ledger entries. Worked on the scripted day in tests/unit/scenario.py.

The auction at 2,500.00 (250,000 paise) trades 130 shares: A buys 100, E buys 30, C sells 80, D sells 50.
Later L buys 30 from D at 250,000 too. H, I, F and K also trade, at 249,950, but are not tracked here.
"""

from __future__ import annotations

from marketlab.ledger import MARKET_CASH, Ledger, market_shares_account, post_trades
from tests.unit.scenario import scripted_day

TRACKED = {"A", "E", "L", "C", "D"}


def build() -> tuple[Ledger, int]:
    ledger = Ledger()
    for buyer in ("A", "E", "L"):
        ledger.open_account(buyer, starting_cash=30_000_000 if buyer == "A" else 10_000_000)
    for seller in ("C", "D"):
        ledger.open_account(seller, starting_cash=0, allows_negative=True)
    events, _ = scripted_day()
    # the sellers own no shares in this script, so their share accounts must be allowed below zero
    posted = post_trades(ledger, events, source="day", tracked=TRACKED.__contains__, allows_negative=True)
    return ledger, posted


def test_each_tracked_side_of_each_trade_becomes_one_transaction() -> None:
    ledger, posted = build()
    # A: 2 trades, E: 1, L: 1, C: 2, D: 2 (H, I, F and K are not tracked)
    assert posted == 8
    assert ledger.verify() == []


def test_buyers_cash_and_shares_match_the_hand_worked_numbers() -> None:
    ledger, _ = build()
    assert ledger.cash("A") == 30_000_000 - 100 * 250_000 == 5_000_000
    assert ledger.shares("A", "DEMO1") == 100
    assert ledger.cash("E") == 10_000_000 - 30 * 250_000 == 2_500_000
    assert ledger.shares("E", "DEMO1") == 30
    assert ledger.cash("L") == 2_500_000
    assert ledger.shares("L", "DEMO1") == 30


def test_sellers_are_paid_the_same_auction_price_per_share() -> None:
    ledger, _ = build()
    assert ledger.cash("C") == 80 * 250_000  # C sold 80
    assert ledger.shares("C", "DEMO1") == -80
    assert ledger.cash("D") == 80 * 250_000  # D sold 50 in the auction and 30 more to L
    assert ledger.shares("D", "DEMO1") == -80


def test_with_every_party_tracked_the_market_account_nets_to_zero() -> None:
    ledger, _ = build()
    # Buyers paid 160 shares' worth and sellers received 160 shares' worth, so the market holds nothing.
    assert ledger.balance(MARKET_CASH) == 0
    assert ledger.balance(market_shares_account("DEMO1")) == 0


def test_giving_the_same_events_again_changes_nothing() -> None:
    ledger, _ = build()
    before = ledger.balances()
    events, _ = scripted_day()
    assert post_trades(ledger, events, source="day", tracked=TRACKED.__contains__, allows_negative=True) == 0
    assert ledger.balances() == before


def test_a_buyer_who_cannot_afford_the_trade_is_refused_and_nothing_is_recorded() -> None:
    import pytest

    from marketlab.ledger import InsufficientBalance

    ledger = Ledger()
    ledger.open_account("A", starting_cash=1_000_000)  # 10,000 rupees; the auction needs 2,50,000
    events, _ = scripted_day()
    with pytest.raises(InsufficientBalance):
        post_trades(ledger, events, source="day", tracked={"A"}.__contains__)
    assert ledger.cash("A") == 1_000_000
    assert len(ledger.transactions()) == 1  # only the opening deposit


# -- with charges --------------------------------------------------------------------------------------------------


def test_a_buy_split_over_two_fills_pays_the_same_charges_as_one_buy() -> None:
    from datetime import date

    from marketlab.core import Side
    from marketlab.costs import PLANS, CostModel, schedule_on
    from marketlab.ledger import COST_LINES, cost_account

    model = CostModel(schedule_on(date(2026, 11, 1)), PLANS["flat20"])
    ledger = Ledger()
    ledger.open_account("A", starting_cash=30_000_000)
    ledger.open_account("C", starting_cash=0, allows_negative=True)
    ledger.open_account("D", starting_cash=0, allows_negative=True)
    events, _ = scripted_day()
    # A buys 100 in the auction as two fills of 50 (from C and from D). Sellers C and D are tracked too.
    post_trades(ledger, events, source="day", tracked={"A", "C", "D"}.__contains__, allows_negative=True, costs=model)

    # A's order cost: value 25,000,000 paise; flat plan: brokerage 2,000 + STT 25,000 + exchange 768 + SEBI 25
    # + stamp 3,750 + GST 503 = 32,046 paise. Brokerage is charged once, not once per fill.
    # Orders that traded: A's buy, C's sell (80 shares, two fills) and D's sell (80 shares, two fills). Brokerage is
    # once per order, so 3 x 2,000.
    assert ledger.balance(cost_account("brokerage")) == 3 * 2_000
    paid_by_a = 30_000_000 - ledger.cash("A")
    assert paid_by_a == 25_000_000 + 32_046
    # every paisa charged went to a charge account, and the charge accounts hold exactly the three orders' costs
    expected = (
        model.for_order(Side.BUY, 25_000_000).total
        + model.for_order(Side.SELL, 80 * 250_000).total
        + model.for_order(Side.SELL, 80 * 250_000).total
    )
    assert sum(ledger.balance(cost_account(line)) for line in COST_LINES) == expected
    assert ledger.verify() == []


def test_charges_make_a_buy_that_just_fits_without_them_fail() -> None:
    from datetime import date

    import pytest

    from marketlab.costs import PLANS, CostModel, schedule_on
    from marketlab.ledger import InsufficientBalance

    model = CostModel(schedule_on(date(2026, 11, 1)), PLANS["zero"])
    ledger = Ledger()
    ledger.open_account("A", starting_cash=100 * 250_000)  # exactly the price of 100 shares, nothing for charges
    events, _ = scripted_day()
    with pytest.raises(InsufficientBalance):
        post_trades(ledger, events, source="day", tracked={"A"}.__contains__, allows_negative=True, costs=model)
    assert ledger.cash("A") == 100 * 250_000
