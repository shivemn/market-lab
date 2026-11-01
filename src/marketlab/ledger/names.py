"""How accounts are named.

Every ledger account holds one kind of thing: money (in paise, unit "INR") or shares of one stock (unit = the
symbol). A practice account belongs to one owner, so one owner has one cash account and one shares account per
stock. The "system" accounts are the other side of every entry, so that each transaction adds up to zero.
"""

from __future__ import annotations

INR = "INR"  # amounts of money are whole paise

CAPITAL = "system:capital"  # where the virtual money comes from
MARKET_CASH = "system:market:cash"  # the other side of every trade, for money
COSTS = "system:costs"  # brokerage, taxes and charges end up here (from Week 8)


def _check_owner(owner: str) -> str:
    if not owner or ":" in owner or owner != owner.strip():
        raise ValueError(f"an account owner must be non-empty, without ':' or edge spaces; got {owner!r}")
    return owner


def cash_account(owner: str) -> str:
    return f"user:{_check_owner(owner)}:cash"


def shares_account(owner: str, symbol: str) -> str:
    return f"user:{_check_owner(owner)}:shares:{symbol}"


def market_shares_account(symbol: str) -> str:
    """The other side of every trade, for shares of one stock."""
    return f"system:market:shares:{symbol}"
