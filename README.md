# Market Lab

A small stock exchange that runs on your computer, with a web page that lets you watch it work.

Simulated traders send orders. The exchange matches them with real market rules: price-time priority, tick sizes,
price bands and an opening auction. Everything that happens is written to an ordered log that can be replayed exactly.
The page draws the day as a price chart and shows, at any moment, who is waiting in line to trade and why the price
moved.

The long-term goal is a place where beginners practise with virtual money and see how a market really behaves: an
order joins a queue, gets partly filled, and moves the price if it is large. This repository is Phase 1, the exchange
and the page that explains it. All prices and people are simulated, and the companies are made up. Nothing here is
investment advice.

![The day view: a price chart with volume, the queue of waiting orders, and what just happened](docs/img/day-view.png)

![The opening auction: buyers and sellers at each price, the price where most shares trade, and who got what](docs/img/auction-view.png)

## What is in it

- **An exchange core** (`src/marketlab/core`): limit and market orders, day and IOC, cancel and modify, price bands, a
  pre-open call auction with documented tie-breaks. Money is integer paise and quantities are integer shares, so there
  are no rounding errors. No file or network code lives here.
- **An event log** (`log.py`, `codec.py`): the log is the truth. The market is rebuilt from events alone, and every log
  carries a SHA-256 fingerprint, so an edited, truncated or reordered log is refused.
- **A seeded simulator** (`sim`): market makers, casual traders and value traders, with a price process that has
  random drift and occasional jumps. The same seed gives the same day.
- **A web page** (`web`): React and TypeScript. It folds the events into the market itself, so you can scrub through
  the day without waiting for the server.

How the pieces fit together, one order's journey, and how the auction picks its price are drawn in
[docs/architecture.md](docs/architecture.md).

## Try it (Windows PowerShell)

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,api]"
cd web
npm install
npm run build
cd ..
marketlab serve
```

Then open http://127.0.0.1:8000. Press play, drag along the chart, or open the "opening auction" tab to see why the
day opened at its price. The server listens on your own computer only and has no login.

If PowerShell refuses to run the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

Without the web page:

```
marketlab run --seed 7 --out runs/demo.jsonl      # simulate a day (about 5,000 events), write the log
marketlab show runs/demo.jsonl --until 3000       # the market after the first 3,000 events
marketlab replay runs/demo.jsonl                  # re-run from the seed and check it matches exactly
```

## How it is tested

The exchange handles other people's money in the long run, so it is tested harder than the rest.

- **Hand-worked examples.** Unit tests whose expected numbers were calculated by hand, not copied from the output.
- **Randomised tests against simple models.** Hypothesis generates long sequences of orders, and a deliberately
  simple reference version of the book, the exchange and the auction must agree with the real one at every step.
- **Checking that the tests can fail.** I put bugs into the code on purpose (for example, breaking time priority) and
  confirmed the tests catch each one.
- **A pinned day.** A scripted day with integers only must always produce the same fingerprint. Any change to
  behaviour shows up as a changed hash.
- **Two languages, one answer.** The web page re-implements the market fold and the auction rules in TypeScript.
  Python writes a fixture, and the TypeScript tests must reproduce Python's answers, including the opening price on 40
  simulated mornings.
- **Static checks.** `ruff` and `mypy --strict` on the code and tests, run in GitHub Actions on Python 3.11 to 3.13
  plus a web job.

```
pytest                       # the test suite
ruff check .
mypy
cd web; npm test; cd ..      # 35 tests
```

## How fast is it

On a Windows laptop (Intel 12th-generation Core, CPython 3.12), with pure Python and no compiled extensions, the
exchange processed about 242,000 commands per second on a realistic mix of limit orders, market orders and cancels
(five repeats, from 239,000 to 243,000). The typical command took 3.4 µs, 1 in 100 took more than 13 µs, and the
slowest took about 1 ms. Speed did not depend on how full the book was: resting and cancelling an order cost about
3 to 5 µs, and a market order that trades cost 4.7 µs, with 1,000, 10,000 or 100,000 orders already waiting. Method,
the spread across repeats and the full table: [docs/benchmark-results.md](docs/benchmark-results.md). Reproduce with
`python -m benchmarks.bench_exchange`.

Three honest notes. First, these are numbers from one machine and will differ on yours. Second, the rest-and-cancel
cost at 10,000 orders (4.7 µs) is higher than at 1,000 and 100,000 (2.7 µs both). A real slowdown would keep growing
with the book, so I read it as noise on a laptop, not a trend. Third, the matching engine is not where a simulated day
spends its time. A whole day (about 5,000 events) takes roughly 0.135 s on a cloud machine, and a profile shows most
of that goes on encoding and hashing the events and on the traders' own decisions. The exchange itself is a small
share. Making matching faster would not make the simulation noticeably faster.

## Decisions worth knowing about

- **Integers everywhere**, and time is a logical counter in microseconds, not the wall clock. That is what makes a day
  repeatable.
- **Trades happen at the resting order's price**, as on real exchanges. A buyer ready to pay more still pays the
  seller's price.
- **The page only shows the market at the end of whole commands**, so you never see a half-finished state, such as a
  crossed book in the middle of a match.
- **The server computes the whole day, the client controls time.** Pause, speed and scrubbing need no round trips.

## Limits

- The fingerprint covers the events but not the log's header line.
- A day is identical for the same seed on the same machine and Python. Floating-point results (the price process) are
  not guaranteed to match across different CPUs or Python builds, which the integer-only pinned day avoids.
- Simulated traders have no cash limits, there is one instrument, and nobody can place an order yet.
- The test fixture for the page is about 0.8 MB.

## Roadmap

Phase 2 is under way (see below). It adds practice accounts with a double-entry ledger, orders you place yourself,
Indian trading costs and an honest backtester that must beat simple baselines after costs. Later phases add real announcements with an event study,
and a plain-language app for learners with virtual money. The full plan and decisions are in [SPEC.md](SPEC.md).

## Phase 2: practice accounts

What does a trade cost? Ask the calculator:

```
marketlab costs --side buy --quantity 100 --price 2500
```

```
Buy 100 shares at 2,500.00
  Value of the trade                      250,000.00
  Securities transaction tax                  250.00
  Exchange transaction charge                   7.68
  SEBI turnover fee                             0.25
  Stamp duty                                   37.50
  GST                                           1.43
  Total charges                               296.86
```

Buying and then selling the same shares at the same price costs about 0.22% of the value in charges, so the price has
to move about that much just to break even. The rates are in `src/marketlab/costs.py` as exact fractions, in dated
schedules that say where each number came from. Charges are collected into one ledger account per kind, so a statement
can later show exactly what was paid and why. These are teaching numbers; check a real contract note for real money.

| Week | Deliverable | Status |
|---|---|---|
| 7 | SQLite ledger: practice accounts with ₹1,00,000, double-entry transactions, overdraft guard, trades posted from the log | done |
| 8 | Indian trading costs for delivery trades (STT, exchange charge, SEBI fee, stamp duty, GST, optional brokerage), dated and sourced | done |
| 9a | Pre-trade checks: cash and shares set aside while an order is open, refusals in plain words, settlement fill by fill | done |
| 9b | A live practice session where you can place orders (the server advances only when asked) | |
| 10 | Order ticket and portfolio on the page | |
| 11 | Statements, reconciliation tests, "what did trading cost me" | |
| 12 | Write-up | |

Scope for now: delivery trades only, long only (no short selling), instant settlement. Each is a simplification
that will be lifted later.

## Layout

```
src/marketlab/core/     order types, validation, order book, auction price, events, the exchange (no I/O)
src/marketlab/codec.py, log.py     events as canonical text, the log file with its fingerprint
src/marketlab/projection.py        the market rebuilt from events alone
src/marketlab/ledger/   practice accounts and the double-entry ledger (SQLite), trades from the log become entries
src/marketlab/sim/      random price process and the simulated traders
src/marketlab/api/      the web server: REST and a WebSocket that plays a day back
src/marketlab/cli.py    the `marketlab` command (run, show, replay, serve)
web/                    the React page (TypeScript, Vite)
benchmarks/             the speed benchmark
docs/                   architecture diagrams, benchmark results, screenshots
tests/unit/             hand-calculated examples
tests/property/         randomised tests against reference models
```
