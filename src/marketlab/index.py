"""Stock indices, worked out with the same formula the real ones use.

An index is one number that stands for a basket of shares. Nifty 50 and Sensex do not average prices. Each
member counts in proportion to its free-float market capitalisation (price x the shares actually available to the
public), and the sum is divided by a number called the divisor, which is chosen once so the index starts at its
base value:

    index = (sum of price_i x shares_i)  /  divisor           divisor = (that sum on the base date) / base value

Three kinds are offered, and they differ only in the number of "shares" q_i each member is given:

    cap-weighted (Nifty, Sensex)   q_i = free-float shares            big companies move the index most
    price-weighted (the Dow)       q_i = 1                            a share that costs more counts more
    equal-weighted                 q_i = 1 / (n x base price_i)       every company counts the same

The divisor is what keeps the index honest when something changes that is not a price move. If a company in a
price-weighted index splits two for one, its price halves, and without a new divisor the index would fall for no
reason. `after_split` and `rebalance` choose the new divisor so the level stays exactly where it was.

All the arithmetic uses exact fractions; only the final number shown to a person is rounded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Literal

Kind = Literal["cap", "equal", "price"]
KINDS: tuple[Kind, ...] = ("cap", "equal", "price")
BASE_VALUE = 1000


@dataclass(frozen=True, slots=True)
class Member:
    symbol: str
    free_float_shares: int


@dataclass(frozen=True, slots=True)
class Index:
    kind: Kind
    members: tuple[Member, ...]
    quantities: tuple[Fraction, ...]  # q_i for each member, in the same order
    divisor: Fraction

    # -- making one -------------------------------------------------------------------------------------------

    @staticmethod
    def create(
        kind: Kind, members: Sequence[Member], base_prices: Mapping[str, int], base_value: int = BASE_VALUE
    ) -> Index:
        """An index that equals `base_value` when the members trade at `base_prices` (paise)."""
        if not members:
            raise ValueError("an index needs at least one member")
        if len({m.symbol for m in members}) != len(members):
            raise ValueError("a company can be in an index only once")
        quantities = _quantities(kind, members, base_prices)
        total = sum((q * base_prices[m.symbol] for m, q in zip(members, quantities, strict=True)), Fraction(0))
        return Index(kind, tuple(members), quantities, total / base_value)

    # -- reading it -------------------------------------------------------------------------------------------

    def _numerator(self, prices: Mapping[str, int]) -> Fraction:
        return sum((q * prices[m.symbol] for m, q in zip(self.members, self.quantities, strict=True)), Fraction(0))

    def level(self, prices: Mapping[str, int]) -> Fraction:
        return self._numerator(prices) / self.divisor

    def weights(self, prices: Mapping[str, int]) -> dict[str, Fraction]:
        """Each member's share of the index (they add up to 1)."""
        total = self._numerator(prices)
        return {m.symbol: q * prices[m.symbol] / total for m, q in zip(self.members, self.quantities, strict=True)}

    def contributions(self, prices: Mapping[str, int], since: Mapping[str, int]) -> dict[str, Fraction]:
        """How many index points each member added since `since` (negative if it took points away).

        They add up exactly to `level(prices) - level(since)`.
        """
        return {
            m.symbol: q * (prices[m.symbol] - since[m.symbol]) / self.divisor
            for m, q in zip(self.members, self.quantities, strict=True)
        }

    # -- keeping it honest ------------------------------------------------------------------------------------

    def rebalance(self, prices: Mapping[str, int], members: Sequence[Member] | None = None) -> Index:
        """Change who is in the index (or reset equal weights) without moving the level. Only the divisor absorbs it."""
        level = self.level(prices)
        chosen = tuple(members) if members is not None else self.members
        quantities = _quantities(self.kind, chosen, prices)
        fresh = Index(self.kind, chosen, quantities, Fraction(1))
        return replace(fresh, divisor=fresh._numerator(prices) / level)

    def after_split(self, prices: Mapping[str, int], symbol: str, ratio: int) -> Index:
        """A `ratio`-for-1 share split of one member. Returns the index to use from now on, with the new prices
        being `prices[symbol] / ratio`. The level does not change at the moment of the split.

        For a cap-weighted index the free-float shares grow as the price shrinks, so the divisor does not need to
        change. For a price-weighted index it does, and that is the whole reason a divisor exists.
        """
        if ratio < 2:
            raise ValueError("a split needs a ratio of at least 2")
        if symbol not in {m.symbol for m in self.members}:
            raise ValueError(f"{symbol} is not in this index")
        level = self.level(prices)
        members = tuple(
            replace(m, free_float_shares=m.free_float_shares * ratio) if m.symbol == symbol else m for m in self.members
        )
        quantities = tuple(  # price-weighted members count one share each, so nothing changes for them
            q * ratio if (m.symbol == symbol and self.kind != "price") else q
            for m, q in zip(self.members, self.quantities, strict=True)
        )
        after = {s: (Fraction(p, ratio) if s == symbol else Fraction(p)) for s, p in prices.items()}
        split = Index(self.kind, members, quantities, Fraction(1))
        numerator = sum((q * after[m.symbol] for m, q in zip(members, quantities, strict=True)), Fraction(0))
        return replace(split, divisor=numerator / level)


def _quantities(kind: Kind, members: Sequence[Member], prices: Mapping[str, int]) -> tuple[Fraction, ...]:
    if kind == "cap":
        return tuple(Fraction(m.free_float_shares) for m in members)
    if kind == "price":
        return tuple(Fraction(1) for _ in members)
    if kind == "equal":
        return tuple(Fraction(1, len(members) * prices[m.symbol]) for m in members)
    raise ValueError(f"unknown index kind: {kind}")


def hundredths(value: Fraction) -> int:
    """A number as a whole number of hundredths, rounded to the nearest (halves round away from zero)."""
    scaled = value * 100
    whole = scaled.numerator // scaled.denominator
    remainder = scaled - whole
    if remainder > Fraction(1, 2) or (remainder == Fraction(1, 2) and scaled > 0):
        whole += 1
    return whole
