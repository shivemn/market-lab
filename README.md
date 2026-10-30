# Market Lab

A small stock exchange that runs on your computer. Simulated traders send orders, the exchange matches them with
real market rules (price-time priority, tick sizes, price bands, a pre-open auction), and everything that happens is
written to an ordered log that can be replayed exactly.

The long-term goal is a place where beginners can practise with virtual money and see how a market really behaves:
their order joins a queue, gets partly filled, and moves the price if it is large.

**Status: work in progress.** Phase 1 (the exchange) is being built week by week. See [SPEC.md](SPEC.md) for the
full design and plan.

| Week | Deliverable | Status |
|---|---|---|
| 1 | Types, order validation, order book, cancel and reduce, tests | done |
| 2 | Continuous matching, IOC and market orders, cancel, modify, open and close | done |
| 3 | Pre-open auction (price bands are already enforced) | next |
| 4 | Event log, replay, simulated traders | |
| 5 | CLI, API, live dashboard | |
| 6 | Benchmark, diagrams, write-up | |

All money is in paise and all quantities in shares, as integers. All data is simulated.
Nothing here is investment advice.

## Run the tests (Windows PowerShell)

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
ruff check .
mypy
```

If PowerShell refuses to run the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Layout

```
src/marketlab/core/     order types, validation, order book, events, the exchange (no input or output)
tests/unit/             hand-calculated examples
tests/property/         randomised tests: the book and the exchange are compared with simple reference models
```
