from __future__ import annotations

import pytest

from marketlab.core import Instrument


def test_band_edges_for_demo_stock() -> None:
    stock = Instrument("DEMO1", tick_size=5, lot_size=1, reference_price=250_000, band_pct=10)
    assert stock.band_low == 225_000
    assert stock.band_high == 275_000


def test_band_rounds_inwards_to_valid_ticks() -> None:
    # Reference 10.05 rupees (1005 paise). 10 percent below is 904.5 paise, which is not a valid tick,
    # so the lowest valid price is the next tick up: 905. 10 percent above is 1105.5, rounded down to 1105.
    stock = Instrument("DEMO2", tick_size=5, lot_size=1, reference_price=1005, band_pct=10)
    assert stock.band_low == 905
    assert stock.band_high == 1105
    assert stock.band_low % 5 == 0 and stock.band_high % 5 == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"symbol": ""},
        {"tick_size": 0},
        {"lot_size": 0},
        {"reference_price": 0},
        {"reference_price": 250_003},  # not a multiple of the tick
        {"band_pct": 0},
        {"band_pct": 100},
    ],
)
def test_invalid_instrument_is_rejected(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "symbol": "DEMO1",
        "tick_size": 5,
        "lot_size": 1,
        "reference_price": 250_000,
        "band_pct": 10,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        Instrument(**base)  # type: ignore[arg-type]
