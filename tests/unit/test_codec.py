"""Events to text and back."""

from __future__ import annotations

import json

import pytest

from marketlab.codec import EVENT_TYPES, UnknownEventType, decode_event, encode_event, event_from_dict, hash_events
from marketlab.core import (
    AuctionResult,
    CancelReason,
    Event,
    OrderAccepted,
    OrderCancelled,
    OrderExpired,
    OrderModified,
    OrderRejected,
    OrderType,
    RejectReason,
    Session,
    SessionChanged,
    Side,
    TimeInForce,
    Trade,
)

SAMPLES: list[Event] = [
    SessionChanged(1, 0, Session.PRE_OPEN),
    OrderAccepted(2, 10, 7, "A", "DEMO1", Side.BUY, OrderType.LIMIT, 100, 250_000, TimeInForce.DAY),
    OrderAccepted(3, 11, 8, "B", "DEMO1", Side.SELL, OrderType.MARKET, 50, None, TimeInForce.IOC),
    OrderRejected(4, 12, 9, RejectReason.OUTSIDE_BAND),
    OrderCancelled(5, 13, 7, 40, CancelReason.USER),
    OrderModified(6, 14, 7, 80, 250_005, 60, True),
    OrderExpired(7, 15, 7, 60),
    Trade(8, 16, 1, "DEMO1", 250_000, 25, 7, 8, "A", "B", Side.SELL),
    Trade(9, 17, 2, "DEMO1", 250_000, 25, 7, 8, "A", "B", None),
    AuctionResult(10, 18, 250_000, 25, 250_000, 0, 5),
    AuctionResult(11, 19, None, 0, 250_000, 0, 0),
]


@pytest.mark.parametrize("event", SAMPLES, ids=lambda e: type(e).__name__)
def test_every_event_survives_a_round_trip(event: Event) -> None:
    assert decode_event(encode_event(event)) == event


def test_all_event_types_are_covered_by_the_samples() -> None:
    assert {type(e).__name__ for e in SAMPLES} == set(EVENT_TYPES)


def test_the_text_form_is_canonical() -> None:
    line = encode_event(SAMPLES[1])
    assert line == (
        '{"account_id":"A","limit_price":250000,"order_id":7,"order_type":"LIMIT","quantity":100,'
        '"seq":2,"side":"BUY","sim_time":10,"symbol":"DEMO1","tif":"DAY","type":"OrderAccepted"}'
    )
    assert " " not in line and "\n" not in line


def test_none_is_written_as_null_and_comes_back_as_none() -> None:
    line = encode_event(SAMPLES[2])
    assert json.loads(line)["limit_price"] is None
    decoded = decode_event(line)
    assert isinstance(decoded, OrderAccepted) and decoded.limit_price is None


def test_unknown_event_type_is_reported_as_unknown() -> None:
    with pytest.raises(UnknownEventType):
        event_from_dict({"type": "FutureEvent", "seq": 1, "sim_time": 0})


def test_a_missing_field_is_an_error() -> None:
    data = json.loads(encode_event(SAMPLES[4]))
    del data["quantity"]
    with pytest.raises(ValueError, match="missing"):
        event_from_dict(data)


def test_an_extra_field_is_an_error() -> None:
    data = json.loads(encode_event(SAMPLES[4]))
    data["surprise"] = 1
    with pytest.raises(ValueError, match="unexpected"):
        event_from_dict(data)


def test_a_bad_enum_value_is_an_error() -> None:
    data = json.loads(encode_event(SAMPLES[0]))
    data["session"] = "LUNCH"
    with pytest.raises(ValueError):
        event_from_dict(data)


def test_the_fingerprint_changes_when_anything_changes() -> None:
    base = hash_events(SAMPLES)
    assert hash_events(SAMPLES) == base
    assert hash_events(SAMPLES[:-1]) != base  # fewer events
    assert hash_events(list(reversed(SAMPLES))) != base  # different order
    changed = [*SAMPLES[:4], OrderRejected(4, 12, 9, RejectReason.BAD_TICK), *SAMPLES[5:]]
    assert hash_events(changed) != base  # one field different
