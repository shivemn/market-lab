"""The equilibrium price of a call auction, as a pure function.

In a call auction, orders are collected without trading and then matched all at once at a single price.

For a candidate price p:
    buy quantity  B(p) = market buy orders + limit buys priced at p or higher   (people willing to pay p)
    sell quantity S(p) = market sell orders + limit sells priced at p or lower  (people willing to accept p)
    executable volume  = min(B(p), S(p))

The equilibrium price is chosen by these rules, in order:
1. the price with the largest executable volume;
2. if tied, the smallest imbalance |B(p) - S(p)|;
3. if still tied, the price closest to the reference price (the previous close);
4. if still tied, the lower price. (This last rule never decides anything: the prices left after rules 1 and 2 form
   one unbroken run of ticks, so the one nearest the reference price is unique. It is kept as a safety net.)

If no price has any executable volume, nothing trades.

Only some prices need to be checked. B(p) and S(p) are step functions that change only at the limit prices
people typed in. Between two neighbouring limit prices every price gives the same numbers, so it is enough to try
each limit price, the ticks just either side of it, and the reference price itself.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import accumulate


@dataclass(frozen=True)
class AuctionOutcome:
    price: int | None  # None when nothing can trade
    volume: int  # shares that trade
    buy_eligible: int  # B(price): buy quantity willing to trade at that price (0 when there is no price)
    sell_eligible: int  # S(price)


def compute_auction(
    *,
    buy_limits: Sequence[tuple[int, int]],
    sell_limits: Sequence[tuple[int, int]],
    market_buy: int,
    market_sell: int,
    reference_price: int,
    tick_size: int,
    band_low: int,
    band_high: int,
) -> AuctionOutcome:
    """Find the equilibrium price. Limit orders are (price, quantity) pairs. Quantities must be positive."""
    buys = sorted(buy_limits)
    buy_prices = [price for price, _ in buys]
    # buy_suffix[i] is the total quantity of buys[i:], that is, everyone priced at buy_prices[i] or higher.
    buy_suffix = [0] * (len(buys) + 1)
    for i in range(len(buys) - 1, -1, -1):
        buy_suffix[i] = buy_suffix[i + 1] + buys[i][1]

    sells = sorted(sell_limits)
    sell_prices = [price for price, _ in sells]
    # sell_prefix[i] is the total quantity of sells[:i], that is, everyone priced below sell_prices[i].
    sell_prefix = [0, *accumulate(quantity for _, quantity in sells)]

    candidates = {reference_price}
    for price in buy_prices + sell_prices:
        candidates.update((price - tick_size, price, price + tick_size))

    best_key: tuple[int, int, int, int] | None = None
    best: tuple[int, int, int, int] | None = None
    for price in sorted(candidates):
        if price < band_low or price > band_high or price % tick_size != 0:
            continue
        buy_quantity = market_buy + buy_suffix[bisect_left(buy_prices, price)]
        sell_quantity = market_sell + sell_prefix[bisect_right(sell_prices, price)]
        volume = min(buy_quantity, sell_quantity)
        key = (-volume, abs(buy_quantity - sell_quantity), abs(price - reference_price), price)
        if best_key is None or key < best_key:
            best_key = key
            best = (price, volume, buy_quantity, sell_quantity)

    if best is None or best[1] == 0:
        return AuctionOutcome(None, 0, 0, 0)
    return AuctionOutcome(price=best[0], volume=best[1], buy_eligible=best[2], sell_eligible=best[3])
