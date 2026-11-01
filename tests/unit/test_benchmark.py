"""The benchmark must at least run and measure something real. Its numbers are not tested, only its shape."""

from __future__ import annotations

from benchmarks import bench_exchange as bench

from marketlab.core import Exchange, Session, Trade


def test_the_generated_stream_is_repeatable_and_really_trades() -> None:
    first = bench.generate(2_000, seed=1)
    assert first == bench.generate(2_000, seed=1)
    assert first != bench.generate(2_000, seed=2)
    exchange = Exchange(bench.INSTRUMENT, Session.OPEN)
    trades = 0
    for number, spec in enumerate(first, start=1):
        trades += sum(isinstance(e, Trade) for e in exchange.submit(bench.build(spec), number))
    assert trades > 100, "a benchmark with almost no trades would not exercise matching"


def test_a_quick_run_has_every_part_of_the_report() -> None:
    result = bench.run(quick=True, progress=lambda _: None)
    flow = result["mixed_flow"]
    assert flow["commands_per_second"]["median"] > 0
    latency = flow["latency_ns"]
    assert 0 < latency["p50"] <= latency["p90"] <= latency["p99"] <= latency["max"]
    assert [row["depth"] for row in result["depth"]] == [200, 1_000, 5_000]
    text = bench.to_markdown(result)
    assert "commands per second" in text and "Measured on" in text
