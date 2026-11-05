"""How accounts are named.

Every ledger account holds one kind of thing: money (in paise, unit "INR") or shares of one stock (unit = the
symbol). A practice account belongs to one owner, so one owner has one cash account and one shares account per
stock. The "system" accounts are the other side of every entry, so that each transaction adds up to zero.
"""

from __future__ import annotations

INR = "INR"  # amounts of money are whole paise

CAPITAL = "system:capital"  # where the virtual money comes from
MARKET_CASH = "system:market:cash"  # the other side of every trade, for money
COST_LINES = ("brokerage", "stt", "exchange", "sebi", "stamp", "demat", "gst")  # where each kind of charge ends up


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


def cost_account(line: str) -> str:
    """The account that collects one kind of charge, for example the securities transaction tax."""
    if line not in COST_LINES:
        raise ValueError(f"unknown cost line {line!r}; expected one of {COST_LINES}")
    return f"system:costs:{line}"


def reserved_account(owner: str) -> str:
    """Cash set aside for an owner's open buy orders (and for the fixed fees of open sell orders)."""
    return f"user:{_check_owner(owner)}:reserved"


def locked_account(owner: str, symbol: str) -> str:
    """Shares set aside for an owner's open sell orders, so the same shares cannot be sold twice."""
    return f"user:{_check_owner(owner)}:locked:{symbol}"


def capital_shares_account(symbol: str) -> str:
    """Where practice shares come from when an account is given some to start with."""
    return f"system:capital:shares:{symbol}"
