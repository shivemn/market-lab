"""Turning the exchange's trades into ledger transactions.

The exchange never knows about money in accounts; it only writes `Trade` events. This module reads those events
and records, for each tracked account, what the trade did to its cash and its shares. Because it only reads the
event log, the ledger of any run can be rebuilt from the log, and the two can be checked against each other.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from marketlab.core import Event, Trade
from marketlab.ledger.ledger import Entry, Ledger
from marketlab.ledger.names import INR, MARKET_CASH, cash_account, market_shares_account, shares_account


def post_trades(
    ledger: Ledger,
    events: Iterable[Event],
    *,
    source: str,
    tracked: Callable[[str], bool],
    allows_negative: bool = False,
) -> int:
    """Record the trades of `tracked` accounts. Returns how many ledger transactions were new.

    Accounts that do not exist yet are created, with `allows_negative` as their rule; ones that exist keep theirs.
    `source` names the run the events came from (for example its fingerprint), so that giving the same events
    twice changes nothing. With `allows_negative` False, a trade that the account could not afford, or a sale of
    shares it does not hold, raises an error and the whole call is undone.
    """
    posted = 0
    with ledger.batch():
        for event in events:
            if not isinstance(event, Trade):
                continue
            value = event.price * event.quantity
            sides = (
                ("buy", event.buy_account_id, 1),
                ("sell", event.sell_account_id, -1),
            )
            for label, owner, sign in sides:
                if not tracked(owner):
                    continue
                cash = cash_account(owner)
                shares = shares_account(owner, event.symbol)
                market_shares = market_shares_account(event.symbol)
                for account, unit, negative in (
                    (cash, INR, allows_negative),
                    (shares, event.symbol, allows_negative),
                    (market_shares, event.symbol, True),
                ):
                    if not ledger.has_account(account):  # an account that already exists keeps its own rules
                        ledger.ensure_account(account, unit, allows_negative=negative)
                done = ledger.post(
                    [
                        Entry(cash, -sign * value),
                        Entry(MARKET_CASH, sign * value),
                        Entry(shares, sign * event.quantity),
                        Entry(market_shares, -sign * event.quantity),
                    ],
                    at=event.sim_time,
                    memo=f"{'Bought' if sign > 0 else 'Sold'} {event.quantity} {event.symbol} at {event.price} paise",
                    cause=f"{source}:{event.seq}:{label}",
                )
                if done is not None:
                    posted += 1
    return posted
