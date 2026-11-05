"""Pre-trade checks and settlement, worked on a real exchange. Prices in paise: 250_000 is 2,500.00 rupees.

The default charges are used (no brokerage), so a buy of 25,000,000 paise costs 29,686 paise in charges and a sell
costs 25,936 (see tests/unit/test_costs.py for how those are worked out).
"""

from __future__ import annotations

from datetime import date

import pytest

from marketlab.core import (
    CancelOrder,
    Event,
    Exchange,
    ModifyOrder,
    NewOrder,
    Order,
    Session,
    Side,
    TimeInForce,
)
from marketlab.costs import PLANS, CostModel, schedule_on
from marketlab.ledger import (
    Gateway,
    Ledger,
    LedgerError,
    OrderRefused,
    cost_account,
    locked_account,
    reserved_account,
)
from tests.helpers import DEMO, limit, market

DAY = date(2026, 11, 1)
ME = "YOU"


def costs(plan: str = "zero") -> CostModel:
    return CostModel(schedule_on(DAY), PLANS[plan])


class Desk:
    """An exchange, a ledger and a gateway wired together the way a live session will wire them."""

    def __init__(self, cash: int = 30_000_000, shares: int = 0, plan: str = "zero") -> None:
        self.ledger = Ledger()
        self.ledger.open_account(ME, starting_cash=cash)
        if shares:
            self.ledger.grant_shares(ME, "DEMO1", shares)
        self.exchange = Exchange(DEMO, Session.OPEN)
        self.gateway = Gateway(self.ledger, ME, DEMO, costs(plan))
        self.events: list[Event] = []
        self.clock = 0
        self.next_id = 1

    def other(self, order: Order) -> list[Event]:
        """Someone else's order: straight to the exchange."""
        self.clock += 1
        new = self.exchange.submit(NewOrder(order), self.clock)
        self.events += new
        self.gateway.settle(new)
        return new

    def mine(self, order: Order) -> list[Event]:
        """My order: checked and reserved first, then sent, then settled."""
        self.gateway.reserve(order)
        return self.other(order)

    def cancel(self, order_id: int) -> list[Event]:
        self.clock += 1
        new = self.exchange.submit(CancelOrder(order_id), self.clock)
        self.events += new
        self.gateway.settle(new)
        return new

    def id(self) -> int:
        self.next_id += 1
        return self.next_id

    def cash(self) -> int:
        return self.ledger.cash(ME)

    def reserved(self) -> int:
        return self.ledger.balance(reserved_account(ME))

    def locked(self) -> int:
        return self.ledger.balance(locked_account(ME, "DEMO1"))


def test_a_resting_buy_sets_aside_its_worst_case_cost_and_a_cancel_returns_it() -> None:
    desk = Desk()
    desk.mine(limit(1, Side.BUY, 250_000, 100, account=ME))
    assert desk.reserved() == 25_000_000 + 29_686
    assert desk.cash() == 30_000_000 - 25_029_686 == 4_970_314
    desk.cancel(1)
    assert (desk.cash(), desk.reserved()) == (30_000_000, 0)
    assert desk.ledger.verify() == []


def test_a_buy_that_cannot_be_afforded_is_refused_in_plain_words_and_changes_nothing() -> None:
    desk = Desk(cash=10_000_000)  # 1,00,000 rupees
    with pytest.raises(OrderRefused) as caught:
        desk.mine(limit(1, Side.BUY, 250_000, 100, account=ME))
    assert "₹1,00,000.00 available" in str(caught.value)
    assert "₹2,50,296.86" in str(caught.value)
    assert (desk.cash(), desk.reserved()) == (10_000_000, 0)
    assert desk.gateway.open_order_ids() == []


def test_two_orders_that_each_fit_but_not_together_are_not_both_accepted() -> None:
    desk = Desk(cash=30_000_000)
    desk.mine(limit(1, Side.BUY, 250_000, 100, account=ME))  # sets aside 2,50,296.86 of 3,00,000
    with pytest.raises(OrderRefused):
        desk.mine(limit(2, Side.BUY, 250_000, 100, account=ME))
    assert desk.gateway.open_order_ids() == [1]


def test_a_buy_that_trades_below_its_limit_gets_the_difference_back() -> None:
    desk = Desk()
    desk.other(limit(1, Side.SELL, 249_950, 100, account="X"))
    desk.mine(limit(2, Side.BUY, 250_000, 100, account=ME))  # trades at the seller's 2,499.50
    # value 24,995,000. STT 24,995; exchange 767.35 -> 767; SEBI 24.995 -> 25; stamp 3,749.25 -> 3,749;
    # GST 18% of (767 + 25) = 142.56 -> 143. Charges 29,679.
    assert desk.cash() == 30_000_000 - 24_995_000 - 29_679 == 4_975_321
    assert desk.reserved() == 0
    assert desk.ledger.shares(ME, "DEMO1") == 100
    assert desk.gateway.open_order_ids() == []
    assert desk.ledger.balance(cost_account("stt")) == 24_995
    assert desk.ledger.verify() == []


def test_a_partly_filled_buy_keeps_the_rest_set_aside_until_it_ends() -> None:
    desk = Desk()
    desk.other(limit(1, Side.SELL, 250_000, 40, account="X"))
    desk.mine(limit(2, Side.BUY, 250_000, 100, account=ME))  # 40 trade now, 60 rest
    paid = 10_000_000 + costs().for_order(Side.BUY, 10_000_000).total
    assert desk.ledger.shares(ME, "DEMO1") == 40
    assert desk.reserved() == 25_029_686 - paid
    assert desk.gateway.open_order_ids() == [2]
    desk.cancel(2)
    assert desk.reserved() == 0
    assert desk.cash() == 30_000_000 - paid


def test_an_ioc_buy_returns_what_did_not_trade_straight_away() -> None:
    desk = Desk()
    desk.other(limit(1, Side.SELL, 250_000, 40, account="X"))
    desk.mine(limit(2, Side.BUY, 250_000, 100, account=ME, tif=TimeInForce.IOC))
    paid = 10_000_000 + costs().for_order(Side.BUY, 10_000_000).total
    assert (desk.reserved(), desk.cash()) == (0, 30_000_000 - paid)
    assert desk.gateway.open_order_ids() == []


def test_a_market_buy_is_checked_at_the_top_of_the_price_band_and_says_so() -> None:
    desk = Desk(cash=3_000_000)  # 30,000 rupees; 10 shares at the band top 2,750.00 is 27,500 plus charges
    assert DEMO.band_high == 275_000
    desk.mine(market(1, Side.BUY, 10, account=ME))  # affordable: exchange has no seller, so it is rejected
    assert (desk.cash(), desk.reserved()) == (3_000_000, 0)  # and everything is given back
    with pytest.raises(OrderRefused, match="top of today's price band"):
        desk.mine(market(2, Side.BUY, 11, account=ME))  # 11 x 2,750.00 = 30,250 > 30,000


def test_an_order_the_exchange_rejects_gives_everything_back() -> None:
    desk = Desk()
    desk.mine(limit(1, Side.BUY, 250_003, 10, account=ME))  # off the 5-paise grid
    assert (desk.cash(), desk.reserved()) == (30_000_000, 0)
    assert desk.gateway.open_order_ids() == []


def test_a_sell_locks_its_shares_so_they_cannot_be_sold_twice() -> None:
    desk = Desk(shares=100)
    desk.mine(limit(1, Side.SELL, 260_000, 60, account=ME))
    assert desk.locked() == 60
    assert desk.ledger.shares(ME, "DEMO1") == 40
    with pytest.raises(OrderRefused, match=r"40 DEMO1 shares free.*60 more are locked"):
        desk.mine(limit(2, Side.SELL, 260_000, 50, account=ME))
    desk.cancel(1)
    assert (desk.locked(), desk.ledger.shares(ME, "DEMO1")) == (0, 100)


def test_selling_shares_you_do_not_hold_is_refused() -> None:
    desk = Desk(shares=0)
    with pytest.raises(OrderRefused, match="0 DEMO1 shares free"):
        desk.mine(limit(1, Side.SELL, 250_000, 1, account=ME))


def test_a_sell_that_trades_pays_proceeds_minus_charges() -> None:
    desk = Desk(cash=1_000_000, shares=100)
    desk.other(limit(1, Side.BUY, 250_000, 100, account="X"))
    desk.mine(limit(2, Side.SELL, 250_000, 100, account=ME))
    assert desk.cash() == 1_000_000 + 25_000_000 - 25_936
    assert (desk.ledger.shares(ME, "DEMO1"), desk.locked(), desk.reserved()) == (0, 0, 0)
    assert desk.ledger.verify() == []


def test_a_broker_plan_with_fixed_fees_sets_them_aside_for_a_sell() -> None:
    # Rs 20 brokerage + Rs 20 demat = 4,000 paise, plus 18% GST = 720, so 4,720 is set aside.
    poor = Desk(cash=4_719, shares=10, plan="flat20")
    with pytest.raises(OrderRefused, match="broker's fees"):
        poor.mine(limit(1, Side.SELL, 250_000, 10, account=ME))

    desk = Desk(cash=1_000_000, shares=100, plan="flat20")
    desk.mine(limit(1, Side.SELL, 260_000, 100, account=ME))
    assert desk.reserved() == 4_720
    assert desk.cash() == 1_000_000 - 4_720
    desk.cancel(1)
    assert (desk.cash(), desk.reserved()) == (1_000_000, 0)

    desk.other(limit(2, Side.BUY, 250_000, 100, account="X"))
    desk.mine(limit(3, Side.SELL, 250_000, 100, account=ME))
    # sell charges on the flat plan: 2,000 + 25,000 + 768 + 25 + 2,000 + 863 = 30,656
    assert desk.cash() == 1_000_000 + 25_000_000 - 30_656
    assert desk.reserved() == 0


def test_changing_an_open_practice_order_is_not_supported_yet() -> None:
    desk = Desk()
    desk.mine(limit(1, Side.BUY, 250_000, 10, account=ME))
    new = desk.exchange.submit(ModifyOrder(1, new_quantity=5), 99)
    with pytest.raises(LedgerError, match="cancel it and place a new one"):
        desk.gateway.settle(new)


def test_an_order_for_someone_else_or_another_stock_is_refused() -> None:
    desk = Desk()
    with pytest.raises(OrderRefused):
        desk.mine(limit(1, Side.BUY, 250_000, 1, account="SOMEONE"))
    with pytest.raises(OrderRefused):
        desk.mine(limit(2, Side.BUY, 250_000, 1, account=ME, symbol="OTHER"))


def test_the_gateway_needs_an_opened_account() -> None:
    with pytest.raises(LedgerError):
        Gateway(Ledger(), "nobody", DEMO, costs())
