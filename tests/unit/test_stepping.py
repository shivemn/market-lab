"""A day that is stepped forward must be exactly the day that is run in one go."""

from __future__ import annotations

import pytest

from marketlab.core import Trade
from marketlab.sim import SimConfig, Simulation, run_simulation

SMALL = SimConfig(seed=4, open_seconds=30, pre_open_seconds=5, noise_traders=4)
MICROS = 1_000_000


@pytest.mark.parametrize("config", [SimConfig(seed=1), SMALL, SimConfig(seed=9, open_seconds=40, pre_open_seconds=8)])
@pytest.mark.parametrize("step", [0.7, 3.0, 11.3, 1000.0])
def test_stepping_in_pieces_gives_the_same_day_as_running_it_whole(config: SimConfig, step: float) -> None:
    whole = run_simulation(config)
    sim = Simulation(config)
    while not sim.finished:
        sim.advance_to(sim.now + round(step * MICROS))
    stepped = sim.result()
    assert stepped.sha256 == whole.sha256
    assert stepped.ends == whole.ends


def test_the_day_cannot_go_backwards_and_stops_at_the_close() -> None:
    sim = Simulation(SMALL)
    sim.advance_to(10 * MICROS)
    with pytest.raises(ValueError, match="back in time"):
        sim.advance_to(5 * MICROS)
    sim.advance_to(10**12)
    assert sim.finished and sim.now == sim.close_at
    assert sim.advance_to(10**13) == []


def test_the_market_is_open_by_the_time_the_opening_moment_is_reached() -> None:
    sim = Simulation(SMALL)
    sim.advance_to(sim.open_at - 1)
    assert not sim.opened
    sim.advance_to(sim.open_at)
    assert sim.opened and sim.state.session.value == "OPEN"


def test_stopping_early_leaves_the_rest_of_the_day_unchanged() -> None:
    whole = run_simulation(SMALL)
    sim = Simulation(SMALL)
    stops = 0
    while not sim.finished:
        before = sim.now
        new = sim.advance_to(sim.close_at, stop=lambda events: any(isinstance(e, Trade) for e in events))
        if not sim.finished:
            stops += 1
            assert sim.now > before
            assert any(isinstance(e, Trade) for e in new)
            assert sim.now == new[-1].sim_time + 1 or new[-1].sim_time < sim.now
    assert stops > 0, "the day should have had trades to stop at"
    assert sim.result().sha256 == whole.sha256


def test_a_commands_time_and_content_are_remembered_for_replay() -> None:
    from marketlab.core import NewOrder, Side
    from tests.helpers import limit

    sim = Simulation(SMALL)
    sim.advance_to(10 * MICROS)
    sim.inject(NewOrder(limit(sim.new_user_order_id(), Side.BUY, 225_000, 3, account="ME")))
    assert [(t, type(c).__name__) for t, c in sim.script] == [(10 * MICROS, "NewOrder")]


def test_sending_a_command_draws_no_random_numbers() -> None:
    """So the traders' random choices go on exactly as they would have. (They still react to the book, as they should:
    an order that becomes the best bid changes what they see, and that is the point of practising.)"""
    from marketlab.core import NewOrder, Side
    from tests.helpers import limit

    sim = Simulation(SMALL)
    sim.advance_to(12 * MICROS)
    before = sim._rng._random.getstate()  # looking inside on purpose: the generator's exact position
    sim.inject(NewOrder(limit(sim.new_user_order_id(), Side.BUY, sim.instrument.band_low, 3, account="ME")))
    assert sim._rng._random.getstate() == before
