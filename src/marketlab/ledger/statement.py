"""A statement: what happened to one owner's money and shares, worked out from the ledger alone.

Reservations and releases move money between an owner's own accounts, so they never change what the owner has;
the statement leaves them out and lists only the money that came in (starting money), the trades, and the charges
each trade paid. "Money" here means free cash plus cash set aside for open orders, and "shares" means free plus
locked shares, so the statement does not jump about while orders are open.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketlab.ledger.ledger import Ledger
from marketlab.ledger.names import CAPITAL, COST_LINES, MARKET_CASH, cash_account, reserved_account

_COST_PREFIX = "system:costs:"
_MARKET_SHARES_PREFIX = "system:market:shares:"
_CAPITAL_SHARES_PREFIX = "system:capital:shares:"


@dataclass(frozen=True, slots=True)
class StatementRow:
    at: int  # logical time in microseconds
    kind: str  # "start", "grant", "buy" or "sell"
    memo: str
    symbol: str | None
    shares_change: int
    value: int  # paise traded (price x quantity); 0 for start and grant rows
    charges: tuple[tuple[str, int], ...]  # (line, paise) for each charge this row paid
    money_change: int  # paise: what this row did to the owner's money, charges included
    money_after: int
    shares_after: int  # of this row's symbol

    @property
    def total_charges(self) -> int:
        return sum(amount for _, amount in self.charges)


@dataclass(frozen=True, slots=True)
class Statement:
    owner: str
    rows: tuple[StatementRow, ...]
    money: int  # cash plus cash set aside, according to the ledger's own balances
    holdings: tuple[tuple[str, int], ...]  # (symbol, shares including locked) according to the ledger

    @property
    def starting_money(self) -> int:
        return sum(r.money_change for r in self.rows if r.kind == "start")

    @property
    def trades(self) -> tuple[StatementRow, ...]:
        return tuple(r for r in self.rows if r.kind in ("buy", "sell"))

    @property
    def bought(self) -> int:
        return sum(r.value for r in self.rows if r.kind == "buy")

    @property
    def sold(self) -> int:
        return sum(r.value for r in self.rows if r.kind == "sell")

    @property
    def traded_value(self) -> int:
        return self.bought + self.sold

    @property
    def charges_by_line(self) -> dict[str, int]:
        totals = dict.fromkeys(COST_LINES, 0)
        for row in self.rows:
            for line, amount in row.charges:
                totals[line] += amount
        return totals

    @property
    def total_charges(self) -> int:
        return sum(self.charges_by_line.values())

    @property
    def charges_basis_points(self) -> int:
        """Charges as hundredths of a percent of everything traded, rounded to the nearest whole number."""
        if self.traded_value == 0:
            return 0
        return (self.total_charges * 20_000 + self.traded_value) // (2 * self.traded_value)

    def worth(self, prices: dict[str, int]) -> int:
        """Money plus every holding valued at the given prices (paise a share)."""
        return self.money + sum(qty * prices[symbol] for symbol, qty in self.holdings)

    def result(self, prices: dict[str, int]) -> dict[str, int]:
        """What happened to the owner's worth, split into the part the market did and the part charges took."""
        gain = self.worth(prices) - self.starting_money
        return {
            "gain": gain,
            "charges": self.total_charges,
            "gain_before_charges": gain + self.total_charges,
        }

    def check(self) -> list[str]:
        """Compare the statement, built from transactions, with the ledger's stored balances."""
        problems: list[str] = []
        if self.rows and self.rows[-1].money_after != self.money:
            problems.append(f"statement ends with {self.rows[-1].money_after} paise but the ledger holds {self.money}")
        if not self.rows and self.money != 0:
            problems.append(f"statement is empty but the ledger holds {self.money} paise")
        return problems


def build_statement(ledger: Ledger, owner: str) -> Statement:
    cash = cash_account(owner)
    reserved = reserved_account(owner)
    mine = f"user:{owner}:"
    money = 0
    shares: dict[str, int] = {}
    rows: list[StatementRow] = []
    for tx in ledger.owner_transactions(owner):
        amounts: dict[str, int] = {}
        for entry in tx.entries:
            amounts[entry.account] = amounts.get(entry.account, 0) + entry.amount
        if not any(account.startswith(mine) for account in amounts):
            continue
        if CAPITAL in amounts and cash in amounts:
            money += amounts[cash]
            rows.append(StatementRow(tx.at, "start", tx.memo, None, 0, 0, (), amounts[cash], money, 0))
        elif MARKET_CASH in amounts:
            market_shares = next((a for a in amounts if a.startswith(_MARKET_SHARES_PREFIX)), None)
            if market_shares is None:
                continue
            symbol = market_shares.removeprefix(_MARKET_SHARES_PREFIX)
            change = -amounts[market_shares]  # what the market gave up, the owner received
            value = abs(amounts[MARKET_CASH])
            charges = tuple(
                (account.removeprefix(_COST_PREFIX), amount)
                for account, amount in amounts.items()
                if account.startswith(_COST_PREFIX) and amount
            )
            paid = sum(amount for _, amount in charges)
            kind = "buy" if change > 0 else "sell"
            delta = (-value if kind == "buy" else value) - paid
            money += delta
            shares[symbol] = shares.get(symbol, 0) + change
            rows.append(
                StatementRow(tx.at, kind, tx.memo, symbol, change, value, charges, delta, money, shares[symbol])
            )
        else:
            grant = next((a for a in amounts if a.startswith(_CAPITAL_SHARES_PREFIX)), None)
            if grant is not None:
                symbol = grant.removeprefix(_CAPITAL_SHARES_PREFIX)
                change = -amounts[grant]
                shares[symbol] = shares.get(symbol, 0) + change
                rows.append(StatementRow(tx.at, "grant", tx.memo, symbol, change, 0, (), 0, money, shares[symbol]))
    held = tuple(sorted((symbol, qty) for symbol, qty in shares.items() if qty))
    mine_now = ledger.owner_balances(owner)
    stored = mine_now[cash] + mine_now.get(reserved, 0)
    return Statement(owner, tuple(rows), stored, held)
