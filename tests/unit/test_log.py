"""The log file: writing, reading and refusing damaged files."""

from __future__ import annotations

from pathlib import Path

import pytest

from marketlab.log import LogError, read_log, write_log
from marketlab.sim import SimConfig, run_simulation

CONFIG = SimConfig(seed=3, pre_open_seconds=10, open_seconds=30, noise_traders=5)


@pytest.fixture
def written(tmp_path: Path) -> tuple[Path, str]:
    result = run_simulation(CONFIG)
    path = tmp_path / "day.jsonl"
    sha = write_log(path, result.instrument, result.events, CONFIG.to_dict())
    return path, sha


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")[:-1]


def _save(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def test_round_trip_keeps_events_instrument_and_settings(written: tuple[Path, str]) -> None:
    path, sha = written
    result = run_simulation(CONFIG)
    log = read_log(path)
    assert log.events == result.events
    assert log.instrument == result.instrument
    assert log.sha256 == sha == result.sha256
    assert SimConfig.from_dict(log.simulation or {}) == CONFIG


def test_file_shape_is_header_events_footer(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    assert lines[0].startswith('{"format":"marketlab-log"')
    assert lines[-1].startswith('{"events":')
    assert len(lines) == len(read_log(path).events) + 2


def test_files_use_plain_newlines(written: tuple[Path, str]) -> None:
    assert b"\r" not in written[0].read_bytes()


def test_a_file_saved_with_windows_line_endings_still_reads(written: tuple[Path, str]) -> None:
    path, sha = written
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert read_log(path).sha256 == sha


def test_changing_a_number_is_detected(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    index = next(i for i, line in enumerate(lines) if '"type":"Trade"' in line)
    lines[index] = lines[index].replace('"quantity":', '"quantity":9')
    _save(path, lines)
    with pytest.raises(LogError, match="fingerprint"):
        read_log(path)


def test_deleting_an_event_in_the_middle_is_detected(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    del lines[5]
    _save(path, lines)
    with pytest.raises(LogError, match="not in order"):
        read_log(path)


def test_deleting_the_last_event_is_detected(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    del lines[-2]
    _save(path, lines)
    with pytest.raises(LogError, match="footer says"):
        read_log(path)


def test_swapping_two_events_is_detected(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    lines[4], lines[5] = lines[5], lines[4]
    _save(path, lines)
    with pytest.raises(LogError, match="not in order"):
        read_log(path)


def test_a_cut_short_file_is_detected(written: tuple[Path, str]) -> None:
    path, _ = written
    _save(path, _lines(path)[:-1])
    with pytest.raises(LogError, match="cut short"):
        read_log(path)


def test_a_wrong_footer_count_is_detected(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    lines[-1] = lines[-1].replace('{"events":', '{"events":1')
    _save(path, lines)
    with pytest.raises(LogError, match="footer says"):
        read_log(path)


@pytest.mark.parametrize(
    "text",
    ["", "\n", "not json\nnot json\n", '{"type":"LogHeader","format":"other","version":1}\n{"type":"LogFooter"}\n'],
)
def test_garbage_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(LogError):
        read_log(path)


def test_a_newer_version_is_refused(written: tuple[Path, str]) -> None:
    path, _ = written
    lines = _lines(path)
    lines[0] = lines[0].replace('"version":1', '"version":2')
    _save(path, lines)
    with pytest.raises(LogError, match="version"):
        read_log(path)


def test_a_missing_file_is_a_log_error(tmp_path: Path) -> None:
    with pytest.raises(LogError, match="cannot read"):
        read_log(tmp_path / "nope.jsonl")


def test_unknown_event_types_are_an_error_unless_asked_to_skip(tmp_path: Path) -> None:
    """A log written by a later phase has events this version does not know."""
    from marketlab.codec import hash_lines

    result = run_simulation(CONFIG)
    path = tmp_path / "future.jsonl"
    write_log(path, result.instrument, result.events[:3])
    lines = _lines(path)
    future = '{"seq":4,"sim_time":5,"type":"FutureEvent"}'
    body = [*lines[1:-1], future]
    footer = f'{{"events":{len(body)},"sha256":"{hash_lines(body)}","type":"LogFooter"}}'
    _save(path, [lines[0], *body, footer])
    with pytest.raises(LogError, match="unknown type"):
        read_log(path)
    log = read_log(path, strict=False)
    assert log.skipped_unknown == 1
    assert log.events == result.events[:3]
