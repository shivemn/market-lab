"""Index arithmetic: the formula, the divisor, and what keeps an index honest."""

from __future__ import annotations

from fractions import Fraction

import pytest

from marketlab.index import BASE_VALUE, KINDS, Index, Member, hundredths

MEMBERS = [Member("A", 100), Member("B", 50), Member("C", 10)]
BASE = {"A": 1000, "B": 2000, "C": 5000}  # paise
LATER = {"A": 1100, "B": 1900, "C": 5200}


def test_every_kind_starts_at_the_base_value() -> None:
    for kind in KINDS:
        assert Index.create(kind, MEMBERS, BASE).level(BASE) == BASE_VALUE


def test_cap_weighted_matches_a_hand_worked_example() -> None:
    # caps at the base: 100000 + 100000 + 50000 = 250000, so the divisor is 250000 / 1000 = 250
    # caps later: 110000 + 95000 + 52000 = 257000, and 257000 / 250 = 1028
    index = Index.create("cap", MEMBERS, BASE)
    assert index.divisor == 250
    assert index.level(LATER) == 1028


def test_price_weighted_matches_the_dow_style_sum() -> None:
    # prices add up to 8000 at the base, so the divisor is 8; later 8200 / 8 = 1025
    index = Index.create("price", MEMBERS, BASE)
    assert index.divisor == 8
    assert index.level(LATER) == 1025


def test_equal_weighted_is_the_plain_average_of_price_relatives() -> None:
    index = Index.create("equal", MEMBERS, BASE)
    average = (Fraction(1100, 1000) + Fraction(1900, 2000) + Fraction(5200, 5000)) / 3
    assert index.level(LATER) == BASE_VALUE * average


def test_the_three_kinds_disagree_on_the_same_day() -> None:
    levels = {kind: Index.create(kind, MEMBERS, BASE).level(LATER) for kind in KINDS}
    assert len(set(levels.values())) == 3


def test_contributions_add_up_exactly_to_the_change_in_the_index() -> None:
    for kind in KINDS:
        index = Index.create(kind, MEMBERS, BASE)
        moved = index.contributions(LATER, BASE)
        assert sum(moved.values()) == index.level(LATER) - index.level(BASE)


def test_weights_add_up_to_one_and_follow_size() -> None:
    weights = Index.create("cap", MEMBERS, BASE).weights(BASE)
    assert sum(weights.values()) == 1
    assert weights["A"] == weights["B"] == Fraction(2, 5)
    equal = Index.create("equal", MEMBERS, BASE).weights(BASE)
    assert set(equal.values()) == {Fraction(1, 3)}


def test_a_split_leaves_the_level_alone_and_only_a_price_weighted_divisor_changes() -> None:
    after = dict(LATER, B=LATER["B"] // 2)  # B splits two for one: its price halves
    for kind in KINDS:
        index = Index.create(kind, MEMBERS, BASE)
        split = index.after_split(LATER, "B", 2)
        assert split.level(after) == index.level(LATER)
        if kind != "price":
            # from here on it moves as it would have, e.g. when A rises by 50 paise. (A price-weighted index
            # does not: the split company now counts for less, which is how the Dow really behaves.)
            moved = dict(after, A=after["A"] + 50)
            old_moved = dict(LATER, A=LATER["A"] + 50)
            assert split.level(moved) == index.level(old_moved)
        if kind == "price":
            assert split.divisor != index.divisor  # the Dow needs a new divisor
        else:
            assert split.divisor == index.divisor  # cap and equal weights absorb it in the share count


def test_without_a_new_divisor_a_split_would_move_a_price_weighted_index() -> None:
    index = Index.create("price", MEMBERS, BASE)
    after = dict(LATER, B=LATER["B"] // 2)
    assert index.level(after) < index.level(LATER)  # the false fall the divisor prevents


def test_changing_the_members_keeps_the_level() -> None:
    for kind in KINDS:
        index = Index.create(kind, MEMBERS, BASE)
        smaller = index.rebalance(LATER, MEMBERS[:2])
        assert smaller.level(LATER) == index.level(LATER)


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        Index.create("cap", [], BASE)
    with pytest.raises(ValueError):
        Index.create("cap", [Member("A", 1), Member("A", 2)], BASE)
    index = Index.create("cap", MEMBERS, BASE)
    with pytest.raises(ValueError):
        index.after_split(BASE, "A", 1)
    with pytest.raises(ValueError):
        index.after_split(BASE, "Z", 2)


def test_hundredths_rounds_halves_away_from_zero() -> None:
    assert hundredths(Fraction(1005, 1000)) == 101  # 1.005 -> 1.01
    assert hundredths(Fraction(-1005, 1000)) == -101  # away from zero
    assert hundredths(Fraction(1000)) == 100_000
    assert hundredths(Fraction(1, 3)) == 33
