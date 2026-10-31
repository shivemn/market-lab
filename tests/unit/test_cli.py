"""The command line, end to end."""

from __future__ import annotations

from pathlib import Path

import pytest

from marketlab.cli import main

RUN = ["run", "--seed", "5", "--pre-open-seconds", "10", "--open-seconds", "40", "--noise-traders", "6"]


def test_run_show_and_replay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "day.jsonl"
    assert main([*RUN, "--out", str(log)]) == 0
    out = capsys.readouterr().out
    assert "wrote" in out and "fingerprint" in out and log.exists()

    assert main(["show", str(log), "--until", "100", "--events", "3"]) == 0
    out = capsys.readouterr().out
    assert "showing the market after 100 events" in out and "last events:" in out and "(checked)" in out

    assert main(["replay", str(log)]) == 0
    assert "reproduced exactly" in capsys.readouterr().out


def test_the_same_seed_writes_byte_identical_files(tmp_path: Path) -> None:
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    assert main([*RUN, "--out", str(first)]) == 0
    assert main([*RUN, "--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_show_refuses_a_tampered_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "day.jsonl"
    main([*RUN, "--out", str(log)])
    capsys.readouterr()
    lines = log.read_text(encoding="utf-8").split("\n")
    lines[3] = lines[3].replace('"quantity":', '"quantity":1')
    log.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    assert main(["show", str(log)]) == 2
    assert "error:" in capsys.readouterr().err


def test_replay_notices_a_changed_seed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "day.jsonl"
    main([*RUN, "--out", str(log)])
    capsys.readouterr()
    text = log.read_text(encoding="utf-8")
    assert '"seed":5' in text
    log.write_text(text.replace('"seed":5', '"seed":6', 1), encoding="utf-8", newline="\n")
    assert main(["replay", str(log)]) == 1
    assert "DIFFERENT" in capsys.readouterr().out


def test_missing_file_is_a_clean_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", str(tmp_path / "nope.jsonl")]) == 2
    assert "cannot read" in capsys.readouterr().err
