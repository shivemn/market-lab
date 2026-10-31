"""Writing and reading the event log file.

The file is plain text, one JSON object per line:

    line 1      header: the log format version, the instrument's rules and (for simulated runs) the settings
                that produced it, including the random seed
    lines 2..n  one event per line, in order
    last line   footer: how many events there are and their SHA-256 fingerprint

Reading checks the footer, so a file that was edited, cut short or reordered is rejected instead of being
trusted. Files are always written with plain "\\n" line endings, even on Windows, so the fingerprint is the same
everywhere.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marketlab.codec import UnknownEventType, decode_event, encode_event, hash_lines
from marketlab.core import Event, Instrument

FORMAT = "marketlab-log"
VERSION = 1


class LogError(Exception):
    """The log file is damaged, incomplete or not a Market Lab log."""


@dataclass(frozen=True)
class EventLog:
    instrument: Instrument
    simulation: dict[str, Any] | None  # the settings that produced the run, if it was simulated
    events: list[Event]
    sha256: str
    skipped_unknown: int  # events of a type this version does not know, skipped when reading non-strictly


def _canonical(data: Mapping[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _instrument_to_dict(instrument: Instrument) -> dict[str, Any]:
    return {
        "symbol": instrument.symbol,
        "tick_size": instrument.tick_size,
        "lot_size": instrument.lot_size,
        "reference_price": instrument.reference_price,
        "band_pct": instrument.band_pct,
    }


def write_log(
    path: Path,
    instrument: Instrument,
    events: Sequence[Event],
    simulation: Mapping[str, Any] | None = None,
) -> str:
    """Write a log file and return its SHA-256 fingerprint."""
    lines = [encode_event(event) for event in events]
    fingerprint = hash_lines(lines)
    header = {
        "type": "LogHeader",
        "format": FORMAT,
        "version": VERSION,
        "instrument": _instrument_to_dict(instrument),
        "simulation": dict(simulation) if simulation is not None else None,
    }
    footer = {"type": "LogFooter", "events": len(lines), "sha256": fingerprint}
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join([_canonical(header), *lines, _canonical(footer)]) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return fingerprint


def read_log(path: Path, *, strict: bool = True) -> EventLog:
    """Read and check a log file.

    With strict=True an event type this version does not know is an error. With strict=False such events are
    skipped (they still count towards the fingerprint), so a log from a later phase can still be read.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LogError(f"cannot read {path}: {error}") from error
    lines = [line.rstrip("\r") for line in text.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 2:
        raise LogError("the file is too short to be a log (it needs a header and a footer)")

    header = _parse(lines[0], "header")
    if header.get("type") != "LogHeader" or header.get("format") != FORMAT:
        raise LogError("the first line is not a Market Lab log header")
    if header.get("version") != VERSION:
        raise LogError(f"unsupported log version {header.get('version')!r}")
    footer = _parse(lines[-1], "footer")
    if footer.get("type") != "LogFooter":
        raise LogError("the last line is not a log footer: the file looks cut short")

    body = lines[1:-1]
    events: list[Event] = []
    skipped = 0
    for number, line in enumerate(body, start=1):
        data = _parse(line, f"event {number}")
        if data.get("seq") != number:
            raise LogError(f"event numbers are not in order: expected {number}, found {data.get('seq')!r}")
        try:
            events.append(decode_event(line))
        except UnknownEventType:
            if strict:
                raise LogError(f"event {number} has an unknown type: {data.get('type')!r}") from None
            skipped += 1
        except (ValueError, TypeError) as error:
            raise LogError(f"event {number} is malformed: {error}") from error

    fingerprint = hash_lines(body)
    if footer.get("events") != len(body):
        raise LogError(f"the footer says {footer.get('events')!r} events but the file has {len(body)}")
    if footer.get("sha256") != fingerprint:
        raise LogError("the fingerprint does not match: the events were changed after the log was written")

    try:
        raw = header["instrument"]
        instrument = Instrument(
            symbol=raw["symbol"],
            tick_size=raw["tick_size"],
            lot_size=raw["lot_size"],
            reference_price=raw["reference_price"],
            band_pct=raw["band_pct"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise LogError(f"the header's instrument is invalid: {error}") from error
    simulation = header.get("simulation")
    return EventLog(instrument, simulation if isinstance(simulation, dict) else None, events, fingerprint, skipped)


def _parse(line: str, what: str) -> dict[str, Any]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as error:
        raise LogError(f"the {what} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise LogError(f"the {what} is not a JSON object")
    return data
