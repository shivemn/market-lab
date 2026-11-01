"""Command boundaries: the only places where the market is a consistent picture."""

from __future__ import annotations

import pytest

from marketlab.core import Side, TimeInForce
from marketlab.projection import MarketState, command_ends
from marketlab.sim import SimConfig, run_simulation
from tests.helpers import DEMO
from tests.unit.scenario import scripted_day


def test_the_scripted_day_splits_into_exactly_its_steps() -> None:
    events, marks = scripted_day()
    assert command_ends(events) == list(marks.values())


def test_no_events_means_no_boundaries() -> None:
    assert command_ends([]) == []


def test_the_auction_and_its_session_change_are_one_step() -> None:
    events, marks = scripted_day()
    ends = command_ends(events)
    # The opening step holds the auction result, its three trades and the change to OPEN.
    assert marks["open"] - marks["cancel2"] == 5
    assert marks["open"] in ends and marks["open"] - 1 not in ends


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_boundaries_found_from_events_match_the_ones_the_simulator_recorded(seed: int) -> None:
    result = run_simulation(SimConfig(seed=seed, pre_open_seconds=15, open_seconds=90, noise_traders=10))
    assert command_ends(result.events) == result.ends
    assert result.ends[-1] == len(result.events)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_between_commands_the_book_is_sane(seed: int) -> None:
    """At every boundary: nothing that should be gone is still resting, and the open book is never crossed."""
    result = run_simulation(SimConfig(seed=seed, pre_open_seconds=15, open_seconds=90, noise_traders=10))
    state = MarketState(DEMO)
    previous = 0
    for end in result.ends:
        state.apply_all(result.events[previous:end])
        previous = end
        assert all(order.tif is TimeInForce.DAY for order in state.orders.values())
        if state.session.value == "OPEN":
            bid, ask = state.best_bid(), state.best_ask()
            assert bid is None or ask is None or bid < ask
        assert state.depth(Side.BUY) == sorted(state.depth(Side.BUY), key=lambda v: -v.price)


def test_stopping_inside_a_command_can_show_a_crossed_book() -> None:
    """The reason boundaries exist: an IOC order is added to the picture before its leftover is cancelled."""
    result = run_simulation(SimConfig(seed=7))
    state = MarketState(result.instrument)
    crossed_inside, crossed_at_boundary = 0, 0
    boundary_set = set(result.ends)
    for count, event in enumerate(result.events, start=1):
        state.apply(event)
        bid, ask = state.best_bid(), state.best_ask()
        if state.session.value == "OPEN" and bid is not None and ask is not None and bid >= ask:
            if count in boundary_set:
                crossed_at_boundary += 1
            else:
                crossed_inside += 1
    assert crossed_at_boundary == 0
    assert crossed_inside > 0
