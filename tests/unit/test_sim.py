"""The simulator: same seed same day, and a day that obeys the exchange's rules."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from marketlab.codec import hash_events
from marketlab.core import OrderRejected, Session, SessionChanged, Side, Trade
from marketlab.sim import SimConfig, run_simulation
from marketlab.sim.processes import FairValue
from marketlab.sim.rng import SimRng

SHORT = SimConfig(seed=11, pre_open_seconds=10, open_seconds=60, noise_traders=8)


def test_same_seed_same_day() -> None:
    first, second = run_simulation(SHORT), run_simulation(SHORT)
    assert first.events == second.events
    assert first.sha256 == second.sha256 == hash_events(first.events)


def test_different_seeds_give_different_days() -> None:
    other = SimConfig(seed=12, pre_open_seconds=10, open_seconds=60, noise_traders=8)
    assert run_simulation(SHORT).sha256 != run_simulation(other).sha256


def test_changing_a_setting_changes_the_day() -> None:
    other = SimConfig(seed=11, pre_open_seconds=10, open_seconds=60, noise_traders=9)
    assert run_simulation(SHORT).sha256 != run_simulation(other).sha256


def test_config_round_trip_and_unknown_settings() -> None:
    assert SimConfig.from_dict(SHORT.to_dict()) == SHORT
    with pytest.raises(ValueError, match="unknown"):
        SimConfig.from_dict({**SHORT.to_dict(), "colour": "red"})


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_a_day_obeys_the_rules(seed: int) -> None:
    config = SimConfig(seed=seed, pre_open_seconds=15, open_seconds=90, noise_traders=10)
    result = run_simulation(config)
    events = result.events
    instrument = result.instrument

    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert all(a.sim_time <= b.sim_time for a, b in zip(events, events[1:], strict=False))
    sessions = [e.session for e in events if isinstance(e, SessionChanged)]
    assert sessions == [Session.PRE_OPEN, Session.OPEN, Session.CLOSED]
    assert result.exchange.session is Session.CLOSED and len(result.exchange.book) == 0

    trades = [e for e in events if isinstance(e, Trade)]
    assert trades, "a day with no trades would make every other check meaningless"
    assert all(instrument.band_low <= t.price <= instrument.band_high for t in trades)
    assert all(t.price % instrument.tick_size == 0 for t in trades)
    assert all(t.quantity > 0 and t.buy_account_id != "" for t in trades)
    # The simulated traders only send valid orders, so the exchange should never need to reject one.
    assert not [e for e in events if isinstance(e, OrderRejected)]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_state_rebuilt_from_events_matches_the_live_exchange(seed: int) -> None:
    config = SimConfig(seed=seed, pre_open_seconds=15, open_seconds=90, noise_traders=10, close_market=False)
    result = run_simulation(config)
    assert result.exchange.session is Session.OPEN
    book, state = result.exchange.book, result.state
    book.check_invariants()
    assert not book.is_crossed()
    assert len(state.orders) == len(book) > 0
    for side in (Side.BUY, Side.SELL):
        assert state.depth(side) == book.depth(side)
        for level in book.depth(side):
            expected = [(o.order_id, o.remaining) for o in book.orders_at(side, level.price)]
            assert state.queue(side, level.price) == expected
    assert state.events_applied == len(result.events)


@settings(max_examples=15, deadline=None)
@given(seed=st.integers(0, 2**32), noise=st.integers(0, 6), makers=st.integers(0, 2), values=st.integers(0, 2))
def test_any_small_market_runs_cleanly(seed: int, noise: int, makers: int, values: int) -> None:
    config = SimConfig(
        seed=seed, pre_open_seconds=5, open_seconds=20, noise_traders=noise, market_makers=makers, value_traders=values
    )
    result = run_simulation(config)
    result.exchange.book.check_invariants()
    assert not result.exchange.book.is_crossed()
    assert [e.seq for e in result.events] == list(range(1, len(result.events) + 1))
    assert not [e for e in result.events if isinstance(e, OrderRejected)]


# ---- the random number generator and the price process ----


def test_rng_is_reproducible_and_seeds_differ() -> None:
    a, b, c = SimRng(5), SimRng(5), SimRng(6)
    first = [a.random() for _ in range(5)]
    assert first == [b.random() for _ in range(5)]
    assert first != [c.random() for _ in range(5)]


def test_exponential_waiting_times_have_the_right_average() -> None:
    rng = SimRng(1)
    mean = sum(rng.exponential(4.0) for _ in range(20_000)) / 20_000
    assert mean == pytest.approx(0.25, rel=0.03)


def test_fair_value_without_noise_or_jumps_stays_put() -> None:
    fair = FairValue(250_000.0, volatility=0.0, jump_rate=0.0, jump_sd=0.0)
    rng = SimRng(1)
    for _ in range(100):
        fair.advance(1.0, rng)
    assert fair.value == 250_000.0


def test_fair_value_volatility_matches_the_setting() -> None:
    """The standard deviation of one-second log returns should be close to the volatility setting."""
    vol = 0.001
    fair = FairValue(100.0, volatility=vol, jump_rate=0.0, jump_sd=0.0)
    rng = SimRng(2)
    returns = []
    for _ in range(20_000):
        before = fair.value
        fair.advance(1.0, rng)
        returns.append(math.log(fair.value / before))
    mean = sum(returns) / len(returns)
    sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    assert sd == pytest.approx(vol, rel=0.03)


def test_jumps_fatten_the_tails() -> None:
    def kurtosis(jump_rate: float) -> float:
        fair = FairValue(100.0, volatility=0.0005, jump_rate=jump_rate, jump_sd=0.01)
        rng = SimRng(3)
        returns = []
        for _ in range(20_000):
            before = fair.value
            fair.advance(1.0, rng)
            returns.append(math.log(fair.value / before))
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        return sum((r - mean) ** 4 for r in returns) / len(returns) / var**2

    assert kurtosis(0.0) == pytest.approx(3.0, abs=0.4)  # a plain normal distribution
    assert kurtosis(0.01) > 6.0  # jumps make big moves much more common


def test_fair_value_rejects_bad_settings() -> None:
    with pytest.raises(ValueError):
        FairValue(0.0, 0.1, 0.0, 0.0)
    with pytest.raises(ValueError):
        FairValue(1.0, -0.1, 0.0, 0.0)
