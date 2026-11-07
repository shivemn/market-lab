"""Random sequences of ledger operations, compared with a plain dictionary that does the same thing.

The reference model is deliberately dumb: balances in a dict, and an operation is refused when a practice
account would go below zero. If the ledger and the dictionary ever disagree, or the audit finds a problem,
Hypothesis shrinks the sequence to the smallest one that shows it.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from marketlab.ledger import (
    CAPITAL,
    INR,
    MARKET_CASH,
    Entry,
    InsufficientBalance,
    Ledger,
    cash_account,
    market_shares_account,
    shares_account,
)
from tests.helpers import examples

OWNERS = ["a", "b", "c"]
owner = st.sampled_from(OWNERS)
amount = st.integers(min_value=1, max_value=5_000)

operation = st.one_of(
    st.tuples(st.just("deposit"), owner, amount),
    st.tuples(st.just("pay"), owner, owner, amount).filter(lambda t: t[1] != t[2]),
    st.tuples(st.just("buy"), owner, amount, st.integers(min_value=1, max_value=50)),  # money out, shares in
    st.tuples(st.just("sell"), owner, amount, st.integers(min_value=1, max_value=50)),
    st.tuples(st.just("give_shares"), owner, owner, st.integers(min_value=1, max_value=50)).filter(
        lambda t: t[1] != t[2]
    ),
)


def setup() -> tuple[Ledger, dict[str, int]]:
    ledger = Ledger()
    model: dict[str, int] = {CAPITAL: 0, MARKET_CASH: 0, market_shares_account("X"): 0}
    ledger.ensure_account(market_shares_account("X"), "X", allows_negative=True)
    for name in OWNERS:
        ledger.open_account(name, starting_cash=0)
        ledger.ensure_account(shares_account(name, "X"), "X")
        model[cash_account(name)] = 0
        model[shares_account(name, "X")] = 0
    return ledger, model


def apply(model: dict[str, int], entries: list[Entry], floor: set[str]) -> bool:
    """The reference: do it unless a floored account would go below zero. Returns whether it was done."""
    for entry in entries:
        if entry.account in floor and model[entry.account] + entry.amount < 0:
            return False
    for entry in entries:
        model[entry.account] += entry.amount
    return True


@settings(max_examples=examples(200), deadline=None)
@given(st.lists(operation, max_size=40))
def test_ledger_agrees_with_a_dictionary_and_always_audits_clean(ops: list[Any]) -> None:
    ledger, model = setup()
    floor = {a for a in model if a.startswith("user:")}
    for step, op in enumerate(ops):
        kind = op[0]
        if kind == "deposit":
            entries = [Entry(CAPITAL, -op[2]), Entry(cash_account(op[1]), op[2])]
        elif kind == "pay":
            entries = [Entry(cash_account(op[1]), -op[3]), Entry(cash_account(op[2]), op[3])]
        elif kind == "buy":
            entries = [
                Entry(cash_account(op[1]), -op[2]),
                Entry(MARKET_CASH, op[2]),
                Entry(shares_account(op[1], "X"), op[3]),
                Entry(market_shares_account("X"), -op[3]),
            ]
        elif kind == "sell":
            entries = [
                Entry(cash_account(op[1]), op[2]),
                Entry(MARKET_CASH, -op[2]),
                Entry(shares_account(op[1], "X"), -op[3]),
                Entry(market_shares_account("X"), op[3]),
            ]
        else:
            entries = [Entry(shares_account(op[1], "X"), -op[3]), Entry(shares_account(op[2], "X"), op[3])]
        expected = apply(model, entries, floor)
        try:
            ledger.post(entries, at=step, memo=kind)
            done = True
        except InsufficientBalance:
            done = False
        assert done == expected, (op, model)
        balances = ledger.balances()
        assert all(balances[a] == model[a] for a in model), (op, model)
    assert ledger.verify() == []
    balances = ledger.balances()
    # money and shares are conserved: everything adds up to zero in each unit
    money = sum(b for a, b in balances.items() if ":shares:" not in a)
    shares = sum(b for a, b in balances.items() if ":shares:" in a)
    assert money == 0 and shares == 0
    assert INR == "INR"
