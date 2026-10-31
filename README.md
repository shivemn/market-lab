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
| 3 | Pre-open session and opening auction (price bands are enforced from Week 1) | done |
| 4 | Event log, replay, simulated traders, command line | done |
| 5 | API, live dashboard | next |
| 6 | Benchmark, diagrams, write-up | |

All money is in paise and all quantities in shares, as integers. All data is simulated.
Nothing here is investment advice.

## Try it

```
marketlab run --seed 7 --out runs/demo.jsonl      # simulate a day (about 5,000 events), write the log
marketlab show runs/demo.jsonl --until 3000       # the market after the first 3,000 events
marketlab replay runs/demo.jsonl                  # re-run from the seed and check it matches exactly
```

The log is the truth: `show` rebuilds the order book from the events alone, and refuses a log that was edited,
cut short or reordered.

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
src/marketlab/core/     order types, validation, order book, auction price, events, the exchange (no I/O)
src/marketlab/codec.py, log.py     events as canonical text, the log file with its fingerprint
src/marketlab/projection.py        the market rebuilt from events alone
src/marketlab/sim/      random price process and the simulated traders
src/marketlab/cli.py    the `marketlab` command
tests/unit/             hand-calculated examples
tests/property/         randomised tests: the book and the exchange are compared with simple reference models
```
