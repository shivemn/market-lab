"""Turning events into text and back, and fingerprinting a whole run.

Every event becomes one line of JSON in a fixed ("canonical") form: keys in alphabetical order, no spaces, and
only whole numbers, text, true/false and null. The same event always gives the same bytes, which is what lets
a run be fingerprinted with SHA-256 and compared byte for byte.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import fields
from enum import Enum
from typing import Any

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

EVENT_TYPES: dict[str, type[Event]] = {
    cls.__name__: cls
    for cls in (
        SessionChanged,
        OrderAccepted,
        OrderRejected,
        OrderCancelled,
        OrderModified,
        OrderExpired,
        Trade,
        AuctionResult,
    )
}

# Fields that hold an enum are stored as their text value, and need turning back into the enum on reading.
_ENUM_FIELDS: dict[tuple[str, str], type[Enum]] = {
    ("SessionChanged", "session"): Session,
    ("OrderAccepted", "side"): Side,
    ("OrderAccepted", "order_type"): OrderType,
    ("OrderAccepted", "tif"): TimeInForce,
    ("OrderRejected", "reason"): RejectReason,
    ("OrderCancelled", "reason"): CancelReason,
    ("Trade", "aggressor_side"): Side,
}


class UnknownEventType(ValueError):
    """The line holds an event type this version does not know (for example, one added in a later phase)."""


def event_to_dict(event: Event) -> dict[str, Any]:
    data: dict[str, Any] = {"type": type(event).__name__}
    for field in fields(event):
        value = getattr(event, field.name)
        data[field.name] = value.value if isinstance(value, Enum) else value
    return data


def encode_event(event: Event) -> str:
    """The canonical one-line text form of an event."""
    return json.dumps(event_to_dict(event), sort_keys=True, separators=(",", ":"))


def event_from_dict(data: Mapping[str, Any]) -> Event:
    type_name = data.get("type")
    cls = EVENT_TYPES.get(type_name) if isinstance(type_name, str) else None
    if cls is None:
        raise UnknownEventType(f"unknown event type: {type_name!r}")
    names = {field.name for field in fields(cls)}
    unexpected = set(data) - names - {"type"}
    if unexpected:
        raise ValueError(f"{cls.__name__} has unexpected fields: {sorted(unexpected)}")
    kwargs: dict[str, Any] = {}
    for field in fields(cls):
        if field.name not in data:
            raise ValueError(f"{cls.__name__} is missing the field {field.name!r}")
        value = data[field.name]
        enum_type = _ENUM_FIELDS.get((cls.__name__, field.name))
        if enum_type is not None and value is not None:
            value = enum_type(value)
        kwargs[field.name] = value
    return cls(**kwargs)


def decode_event(line: str) -> Event:
    return event_from_dict(json.loads(line))


def hash_lines(lines: Iterable[str]) -> str:
    """SHA-256 over each line followed by a newline."""
    digest = hashlib.sha256()
    for line in lines:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def hash_events(events: Iterable[Event]) -> str:
    """The fingerprint of a run: SHA-256 over the canonical lines of all its events, in order."""
    return hash_lines(encode_event(event) for event in events)
