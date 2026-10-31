"""A pinned fingerprint for the hand-written day.

The scripted day uses only integers, so its fingerprint must be the same on every computer and Python version.
If this test fails, either the exchange's behaviour changed (check that this was meant) or the log format
changed (then also raise `VERSION` in log.py). Update GOLDEN only when the change was meant.
"""

from __future__ import annotations

from marketlab.codec import hash_events
from tests.unit.scenario import scripted_day

GOLDEN_EVENTS = 29
GOLDEN_SHA256 = "729330e10831ac68b6497c5c7aeeb6d76f8f7e4e85759d6707133f906d74d7c0"


def test_the_scripted_day_has_the_pinned_fingerprint() -> None:
    events, _ = scripted_day()
    assert len(events) == GOLDEN_EVENTS
    assert hash_events(events) == GOLDEN_SHA256
