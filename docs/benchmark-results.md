# Benchmark results

Measured on: Intel64 Family 6 Model 154 Stepping 3, GenuineIntel, CPython 3.12.10, Windows.
Reproduce with `python -m benchmarks.bench_exchange --markdown docs/benchmark-results.md`.

## Mixed order flow

173,757 commands (69% limit orders, some passive and some crossing the spread; 11% market orders; 19% cancels), repeated 5 times.

- **Throughput:** 242,145 commands per second (lowest run 239,387, highest 243,278)
- **Time per command:** median 3.4 µs, 90th percentile 7.4 µs, 99th 13.0 µs, 99.9th 20.1 µs, slowest 1084 µs

## Does it slow down as the book fills up?

| Orders resting on the book | Rest a new order and cancel it (per command) | Market order that trades (per command) |
|---:|---:|---:|
| 1,000 | 2.7 µs | 4.7 µs |
| 10,000 | 4.7 µs | 4.7 µs |
| 100,000 | 2.7 µs | 4.7 µs |

The 10,000 row for rest-and-cancel is higher than its neighbours. A real slowdown would keep growing with the book, so
this looks like noise from a laptop, not a trend.
