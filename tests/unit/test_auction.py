"""Hand-calculated examples for the equilibrium price of a call auction.

Reference price 250000 paise, tick 5, band 225000 to 275000. Prices below are in paise.
"""

from __future__ import annotations

from marketlab.core import AuctionOutcome, compute_auction


def auction(
    buys: list[tuple[int, int]] | None = None,
    sells: list[tuple[int, int]] | None = None,
    *,
    market_buy: int = 0,
    market_sell: int = 0,
) -> AuctionOutcome:
    return compute_auction(
        buy_limits=buys or [],
        sell_limits=sells or [],
        market_buy=market_buy,
        market_sell=market_sell,
        reference_price=250_000,
        tick_size=5,
        band_low=225_000,
        band_high=275_000,
    )


def test_largest_executable_volume_wins() -> None:
    # Willing to pay at least: 250010 -> 100 shares, 250000 -> 150 shares in total.
    # Willing to accept at most: 250000 -> 80 shares, 250010 -> 140 shares in total.
    # At 250000: min(150, 80) = 80.  At 250005: min(100, 80) = 80.  At 250010: min(100, 140) = 100.
    outcome = auction(buys=[(250_010, 100), (250_000, 50)], sells=[(250_000, 80), (250_010, 60)])
    assert outcome == AuctionOutcome(price=250_010, volume=100, buy_eligible=100, sell_eligible=140)


def test_a_flat_range_of_prices_picks_the_one_closest_to_the_reference() -> None:
    # Every price from 250000 to 250010 gives volume 100 and no imbalance. The reference is 250000.
    outcome = auction(buys=[(250_010, 100)], sells=[(250_000, 100)])
    assert outcome.price == 250_000 and outcome.volume == 100


def test_reference_price_outside_the_flat_range_picks_the_nearest_edge() -> None:
    # Flat range 250010 to 250020, reference 250000, so the nearest price in the range is 250010.
    outcome = auction(buys=[(250_020, 100)], sells=[(250_010, 100)])
    assert outcome.price == 250_010


def test_reference_price_inside_a_flat_range_is_chosen_even_if_nobody_typed_it() -> None:
    # Flat range 249900 to 250100. Nobody quoted 250000, but it is the reference price and inside the range.
    outcome = auction(buys=[(250_100, 100)], sells=[(249_900, 100)])
    assert outcome.price == 250_000


def test_smaller_imbalance_beats_closeness_to_the_reference() -> None:
    # Buyers: 60 shares at 250010 or better, 40 more at 250000.  Sellers: 60 at 250000, 10 more at 250010.
    # 250000: min(100, 60) = 60, imbalance 40.  250005: min(60, 60) = 60, imbalance 0.
    # 250010: min(60, 70) = 60, imbalance 10.  Volume ties at 60, so the zero imbalance at 250005 wins,
    # even though 250000 is closer to the reference.
    outcome = auction(buys=[(250_010, 60), (250_000, 40)], sells=[(250_000, 60), (250_010, 10)])
    assert outcome.price == 250_005 and outcome.volume == 60
    assert outcome.buy_eligible == 60 and outcome.sell_eligible == 60


def test_no_overlap_means_no_trade() -> None:
    assert auction(buys=[(249_990, 10)], sells=[(250_010, 10)]) == AuctionOutcome(None, 0, 0, 0)


def test_nothing_at_all_means_no_trade() -> None:
    assert auction() == AuctionOutcome(None, 0, 0, 0)


def test_one_sided_book_means_no_trade() -> None:
    assert auction(buys=[(250_000, 10)]) == AuctionOutcome(None, 0, 0, 0)
    assert auction(market_buy=50) == AuctionOutcome(None, 0, 0, 0)


def test_market_orders_count_at_every_price() -> None:
    # 50 shares to buy at any price against sellers of 30 at 250000 and 40 more at 250010.
    # The most that can trade is 50, and only once the 250010 seller is included.
    outcome = auction(sells=[(250_000, 30), (250_010, 40)], market_buy=50)
    assert outcome == AuctionOutcome(price=250_010, volume=50, buy_eligible=50, sell_eligible=70)


def test_only_market_orders_trade_at_the_reference_price() -> None:
    outcome = auction(market_buy=40, market_sell=60)
    assert outcome == AuctionOutcome(price=250_000, volume=40, buy_eligible=40, sell_eligible=60)


def test_the_price_never_leaves_the_band() -> None:
    # Both sides at the top edge of the band. One tick above would be outside the band.
    outcome = auction(buys=[(275_000, 10)], sells=[(275_000, 10)])
    assert outcome.price == 275_000 and outcome.volume == 10
