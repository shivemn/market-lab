from __future__ import annotations

import pytest

from marketlab.core import Instrument, RejectReason, Session, Side, validate_order
from tests.helpers import DEMO, limit, market


def test_valid_limit_order_is_accepted() -> None:
    assert validate_order(limit(1, Side.BUY, 250_000, 10), DEMO, Session.OPEN) is None


def test_valid_market_order_is_accepted() -> None:
    assert validate_order(market(1, Side.SELL, 10), DEMO, Session.OPEN) is None


def test_orders_are_accepted_in_pre_open() -> None:
    assert validate_order(limit(1, Side.BUY, 250_000, 10), DEMO, Session.PRE_OPEN) is None
    assert validate_order(market(2, Side.BUY, 10), DEMO, Session.PRE_OPEN) is None


def test_unknown_symbol() -> None:
    order = limit(1, Side.BUY, 250_000, 10, symbol="OTHER")
    assert validate_order(order, DEMO, Session.OPEN) is RejectReason.UNKNOWN_SYMBOL
    assert validate_order(order, None, Session.OPEN) is RejectReason.UNKNOWN_SYMBOL


def test_market_closed() -> None:
    order = limit(1, Side.BUY, 250_000, 10)
    assert validate_order(order, DEMO, Session.CLOSED) is RejectReason.MARKET_CLOSED


def test_limit_order_without_price_is_malformed() -> None:
    order = limit(1, Side.BUY, 250_000, 10)
    order.limit_price = None
    assert validate_order(order, DEMO, Session.OPEN) is RejectReason.BAD_ORDER


def test_market_order_with_price_is_malformed() -> None:
    order = market(1, Side.BUY, 10)
    order.limit_price = 250_000
    assert validate_order(order, DEMO, Session.OPEN) is RejectReason.BAD_ORDER


@pytest.mark.parametrize("quantity", [0, -5])
def test_non_positive_quantity(quantity: int) -> None:
    order = limit(1, Side.BUY, 250_000, 10)
    order.quantity = quantity
    assert validate_order(order, DEMO, Session.OPEN) is RejectReason.BAD_QUANTITY


def test_quantity_must_be_a_multiple_of_the_lot_size() -> None:
    stock = Instrument("LOT10", tick_size=5, lot_size=10, reference_price=250_000, band_pct=10)
    ok = limit(1, Side.BUY, 250_000, 30, symbol="LOT10")
    bad = limit(2, Side.BUY, 250_000, 35, symbol="LOT10")
    assert validate_order(ok, stock, Session.OPEN) is None
    assert validate_order(bad, stock, Session.OPEN) is RejectReason.BAD_LOT


def test_price_must_be_on_a_tick() -> None:
    assert validate_order(limit(1, Side.BUY, 250_005, 1), DEMO, Session.OPEN) is None
    assert validate_order(limit(2, Side.BUY, 250_003, 1), DEMO, Session.OPEN) is RejectReason.BAD_TICK


def test_band_edges_are_inclusive_and_one_tick_beyond_is_rejected() -> None:
    assert validate_order(limit(1, Side.BUY, DEMO.band_low, 1), DEMO, Session.OPEN) is None
    assert validate_order(limit(2, Side.SELL, DEMO.band_high, 1), DEMO, Session.OPEN) is None
    below = limit(3, Side.BUY, DEMO.band_low - DEMO.tick_size, 1)
    above = limit(4, Side.SELL, DEMO.band_high + DEMO.tick_size, 1)
    assert validate_order(below, DEMO, Session.OPEN) is RejectReason.OUTSIDE_BAND
    assert validate_order(above, DEMO, Session.OPEN) is RejectReason.OUTSIDE_BAND


def test_zero_and_negative_prices_are_outside_the_band() -> None:
    assert validate_order(limit(1, Side.BUY, 0, 1), DEMO, Session.OPEN) is RejectReason.OUTSIDE_BAND
    assert validate_order(limit(2, Side.BUY, -5, 1), DEMO, Session.OPEN) is RejectReason.OUTSIDE_BAND


def test_checks_run_in_a_fixed_order() -> None:
    # Wrong symbol beats closed market, and closed market beats a bad quantity.
    order = limit(1, Side.BUY, 250_003, 0, symbol="OTHER")
    assert validate_order(order, DEMO, Session.CLOSED) is RejectReason.UNKNOWN_SYMBOL
    order = limit(2, Side.BUY, 250_003, 0)
    assert validate_order(order, DEMO, Session.CLOSED) is RejectReason.MARKET_CLOSED
    assert validate_order(order, DEMO, Session.OPEN) is RejectReason.BAD_QUANTITY
