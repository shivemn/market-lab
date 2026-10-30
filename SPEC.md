# Market Lab: Phase 1 spec (the exchange)

Status: draft for review. Nothing is built yet. Read this, mark what you disagree with, and we change it before any code is written.

Working name: `market-lab`. Language: Python 3.12.

## 1. What we are building

A small stock exchange that runs on your computer. Simulated traders send orders, the exchange matches them with real exchange rules, and every single thing that happens is written to an ordered log. You can replay the log and get exactly the same result.

Later phases add strategies and a backtester (Phase 2), real announcements and an event study (Phase 3), and a plain-language app for ordinary investors (Phase 4). Phase 1 is only the exchange, and it has to be correct and well tested before anything is built on it.

### Goals
1. Correct matching with price-time priority.
2. Indian-market rules that matter: tick size, price bands (circuit limits) and a pre-open call auction.
3. Deterministic replay: same seed and same inputs always give the same event log, byte for byte.
4. A live view: order book ladder, trade tape and price chart.
5. A strategy interface designed now (used in Phase 2), so we do not rewrite the core later.

### Non-goals for Phase 1
- No real money, no real broker connection, no live NSE/BSE data.
- No multi-stock portfolios, no derivatives (futures and options come much later, if ever).
- No user accounts or login.
- No machine learning yet. The simulator uses stochastic models, not trained models.
- No claim that the simulation predicts the real market.

## 2. Design rules (these decide the hard cases)

1. **Integers only for money and quantity.** Prices are stored in paise (1 rupee = 100 paise), quantities in shares. Floats cause rounding bugs that surface as lost money in tests.
2. **Logical time, not wall-clock time.** The simulation has its own clock, driven by events. This is what makes replay possible.
3. **One matching thread per instrument.** The order book for one stock is touched by one piece of code at a time. No locks, no races.
4. **Event sourcing.** The log is the truth. The order book is just the log folded into current state. If the book and the log ever disagree, the log wins.
5. **The core has no input or output.** The matching engine is a pure library: commands in, events out. The CLI, the API and the dashboard sit outside it.
6. **Everything random is seeded.** One seed produces one reproducible market.

## 3. Domain model

### Instrument
| Field | Meaning | Example |
|---|---|---|
| symbol | unique code | `DEMO1` |
| tick_size | smallest price step, in paise | 5 (= ₹0.05) |
| lot_size | order quantity multiple | 1 |
| reference_price | previous close, in paise | 250000 (₹2,500.00) |
| band_pct | allowed move from reference price | 10 (± 10%) |

Use made-up symbols. We do not use real company data in Phase 1.

### Order
`order_id`, `account_id`, `symbol`, `side` (BUY or SELL), `type`, `quantity`, `limit_price` (paise, absent for market orders), `time_in_force`, `entered_at` (logical time).

Supported in Phase 1:
- **LIMIT** order with time in force **DAY** (rests until cancelled or the session ends) or **IOC** (fill what you can now, cancel the rest).
- **MARKET** order. Executes against the book at once, and any unfilled part is cancelled. It never rests on the book. If the book is empty on the other side, it is rejected.

Cancel and modify:
- **Cancel** removes a resting order.
- **Modify** changes quantity or price. The quantity given is the new *total* size, including anything already filled, so it must exceed the filled amount (to remove an order, cancel it). A price change, or an increase in quantity, loses time priority (it is treated as cancel and new). A quantity decrease keeps priority.

### Order validation (reject with a reason)
`UNKNOWN_SYMBOL`, `MARKET_CLOSED`, `BAD_ORDER` (malformed: a limit order without a price, or a market order with one), `BAD_QUANTITY` (zero or negative), `BAD_LOT`, `BAD_TICK` (price not a multiple of tick size), `OUTSIDE_BAND` (price beyond reference ± band), `NO_LIQUIDITY` (market order, empty opposite side), `UNKNOWN_ORDER` (cancel or modify of something that is not resting), `DUPLICATE_ORDER_ID` (an id is never reused, even after the order is gone). Checks run in exactly this order, so a bad order always gets the same reason.

### Sessions
`CLOSED → PRE_OPEN → OPEN → CLOSED`. The simulator drives session changes on the logical clock. This is simplified from the real exchange, which also has a buffer period and a post-close session. We note the simplification in the README and do not claim to copy the exchange exactly.

- **PRE_OPEN:** orders are accepted and collected, no matching yet. Cancels and modifies are allowed.
- **Opening auction (end of PRE_OPEN):** see section 4.
- **OPEN:** continuous matching.
- **CLOSED:** all DAY orders are expired and logged, nothing is accepted.

## 4. Matching rules

### Continuous matching (OPEN)
1. A new order is checked against the opposite side of the book.
2. Orders match when prices cross: buy price ≥ sell price.
3. **Price-time priority:** best price first, and at the same price the order that arrived earlier goes first.
4. **Trade price is the resting order's price**, not the incoming order's price.
5. Partial fills are allowed. A resting order can be filled across many trades and keeps its place in the queue.
6. After matching, a DAY limit order's remainder rests on the book. An IOC remainder is cancelled.

Self-trade prevention is out of scope for Phase 1 (listed in section 11).

### Pre-open call auction
All orders collected in PRE_OPEN are matched at a single price.

1. For each candidate price, compute the executable volume = min(total buy quantity willing to pay at least that price, total sell quantity willing to accept at most that price). Market orders count at every price.
2. The **equilibrium price** is the one with the **maximum executable volume**.
3. Ties, in order: smallest unmatched quantity (imbalance), then the price **closest to the reference price**, then the lower price.
4. All executable orders trade at the equilibrium price. Within a side, better-priced and earlier orders fill first.
5. Orders not fully filled move onto the continuous book (DAY limit orders) or are cancelled (market orders).
6. If no prices cross, there is no opening trade, the opening price is the reference price, and all limit orders move to the book.

Both the tie-break order and the single-price rule come from how real call auctions work, but we document our version precisely and test it against hand-calculated examples. We do not claim it equals NSE's implementation.

### Price bands
- The allowed range is reference price ± `band_pct`, rounded to valid ticks.
- Orders outside the range are rejected with `OUTSIDE_BAND`.
- In Phase 1, hitting the band does not halt trading. The real exchange has more rules (halts, market-wide circuit breakers). These are out of scope and listed in section 11.

## 5. The event log

Every state change is one event. The engine does not mutate anything without writing an event first.

| Field | Meaning |
|---|---|
| `seq` | gapless counter, 1, 2, 3, ... |
| `sim_time` | logical time in microseconds since the start of the run |
| `type` | event type |
| `payload` | event-specific fields |

### Event types in Phase 1
`INSTRUMENT_LISTED`, `SESSION_CHANGED`, `ORDER_ACCEPTED`, `ORDER_REJECTED`, `ORDER_CANCELLED`, `ORDER_MODIFIED`, `ORDER_EXPIRED`, `TRADE`, `AUCTION_RESULT`.

### Reserved for later phases
`NEWS_EVENT` (Phase 3), `STRATEGY_DECISION` (Phase 2). The log schema and the reader ignore unknown types safely, so adding them later does not break old logs.

### Storage and verification
- Written as JSON Lines during a run, converted to Parquet for analysis (DuckDB can query it directly).
- **Replay check:** a run ends by writing a SHA-256 hash over the canonical bytes of all events. Replaying the same inputs must give the same hash. This is a test, run in CI.

## 6. The simulator (the fake traders)

The simulator is separate from the exchange. It only produces orders.

| Agent | Behaviour | Maths it uses |
|---|---|---|
| Noise traders | send random market and limit orders | Poisson arrival times, random size from a heavy-tailed distribution |
| Liquidity providers | keep buy and sell quotes around the current fair value, refresh after trades | exponential distance from the mid-price |
| Informed trader | trades towards the true fair value when the market is off it | fair value follows geometric Brownian motion with occasional jumps |

All agents use one seeded random generator. Start with simple Poisson arrivals. Self-exciting arrival models (Hawkes processes, where one order makes more orders likely) are a later upgrade, once the simple version works.

Phase 1 checks that the market looks plausible, not that it is realistic: spreads stay positive, the book does not collapse, prices stay inside the band, and returns are not obviously degenerate.

## 7. Interfaces

1. **Library (`marketlab.core`):** `Exchange.submit(command) -> list[Event]`. No input or output, no clock of its own.
2. **CLI:** `marketlab run --seed 42 --duration 6h --out run42.jsonl`, `marketlab replay run42.jsonl`.
3. **API and live view:** FastAPI with a WebSocket that streams book snapshots, trades and session changes. A small web page shows the depth ladder, the trade tape and a price chart. This part comes last and is the least risky.
4. **Strategy interface (designed now, used in Phase 2):**
   ```python
   class Strategy:
       def on_event(self, event: Event) -> list[Command]:
           ...
   ```
   A strategy receives events and returns commands. It never touches the book directly, so the same strategy code works in the live simulation and in the backtester.

## 8. Tests (written before the code)

**Unit tests with hand-calculated numbers:**
- A buy crossing two sell orders at different prices fills at each resting price, in time order.
- Partial fill leaves the correct remainder and keeps queue position.
- IOC remainder is cancelled. Market order on an empty side is rejected.
- Quantity decrease keeps priority; price change loses it.
- Band and tick validation boundaries.
- Auction examples with a known equilibrium, including each tie-break rule and a no-cross case.

**Property-based tests (Hypothesis) that must hold after every command:**
1. The book is never crossed (best bid < best ask) during continuous trading.
2. Quantity is conserved: shares bought = shares sold, and each order's filled + remaining + cancelled = original quantity.
3. Within a price level, orders fill in arrival order.
4. Replaying a generated event log rebuilds the identical book.
5. No trade occurs outside the price band.

**Replay test:** two runs with the same seed produce the same final hash. Two different seeds produce different hashes.

**Performance check (a measurement, not a pass/fail gate):** orders per second on one instrument, reported in the README. A first target is tens of thousands per second in pure Python. If we later need more, a Rust port of the order book is a clear follow-up project.

## 9. Folder layout

```
market-lab/
  src/marketlab/
    core/        order book, matching, auction, validation (no I/O)
    events.py    event types, canonical encoding, hashing
    sim/         agents, random processes, scenario config
    log/         JSONL writer and reader, Parquet export
    api/         FastAPI app and WebSocket
    cli.py
  web/           dashboard (small, later)
  tests/
    unit/  property/  replay/
  docs/          design notes, diagrams
  SPEC.md  README.md  pyproject.toml
```

Tooling: `uv` or `pip`, `pytest`, `hypothesis`, `ruff`, `mypy`, GitHub Actions.

## 10. Milestones (weekends, one person, part time)

| Week | Deliverable | What you learn |
|---|---|---|
| 1 | Types, validation, order book data structure, cancel, unit tests | Order book design, why integers |
| 2 | Continuous matching, IOC, market orders, modify, property tests | Price-time priority, invariants |
| 3 | Sessions, bands, pre-open auction with tests | Call auctions, tie-breaks |
| 4 | Event log, replay, hash check, seeded simulator agents | Event sourcing, stochastic processes |
| 5 | CLI, API, WebSocket, first dashboard | Streaming, state snapshots |
| 6 | README, benchmark, diagrams, clean-up | Writing the story, measuring honestly |

If a week slips, nothing breaks. Each week ends with a working, tested state.

## 11. Out of scope for Phase 1, kept on a "later" list

Self-trade prevention, stop and stop-limit orders, iceberg orders, trading halts and market-wide circuit breakers, post-close session, multiple instruments with correlated prices, derivatives, fees and taxes (these arrive with the backtester in Phase 2), Hawkes arrival processes, a Rust order book.

## 12. Where this is going: a practice market for beginners

The long-term product is a learning app. Every user gets ₹1,00,000 of virtual money and trades in a market where
their orders really enter an order book next to simulated traders. They see their order queue, get partly filled,
pay realistic costs and move the price when they are large. Many practice apps fill orders at the last price, which
hides all of this. Phase 1 builds the engine that makes it possible.

### Roadmap

| Phase | Adds | Statistics, ML and stochastic tools it uses |
|---|---|---|
| 1 | The exchange (this spec) | Poisson arrivals, geometric Brownian motion with jumps for fair value |
| 2 | Accounts, the virtual ledger, portfolios and costs; strategies run as bots in the market; honest backtester | Bootstrap and walk-forward testing, multiple-testing correction, risk measures, Avellaneda-Stoikov market making, TWAP and VWAP execution |
| 3 | Learning layer: public announcements with LLM extraction, an event study, "why did this move?" explanations, replays of real historical episodes from public end-of-day data | Abnormal returns, t-tests and regression, calibrated news shocks, Hawkes processes for realistic order flow |
| 3+ | Forecasting experiments | ML and deep learning compared against naive baselines after costs, reported honestly even when they lose |
| 4 | The learner app: sign-up, wallet, trading screens, lessons, a "reality check" page | Monte Carlo simulation of SIP and portfolio outcomes with costs, inflation and tax shown as ranges |

Rule for ML and deep learning: a model enters the project only when it beats a simple baseline on held-out data,
with costs included. Most do not, and showing that honestly is part of the value.

### Accounts and the ledger (designed now, built in Phase 2)

- A new user receives ₹1,00,000, stored as 10,000,000 paise.
- Money moves through a **double-entry ledger**: every posting has equal debits and credits, entries are never
  edited, and mistakes are fixed with reversing entries. Accounts: user cash, user reserved cash, user holdings,
  fees collected and an exchange clearing account.
- **Buying power:** a buy order reserves quantity × limit price plus estimated costs. The reservation is released
  on cancel and adjusted on fill. An order that would exceed buying power is rejected before it reaches the book.
- **Costs** are shown as an itemised contract note after each trade: brokerage, securities transaction tax,
  exchange charges, GST and stamp duty. Rates live in one configuration file and must be checked against the
  current official rates before anything is published, because they change.
- **Simplifications for v1, stated openly:** settlement is instant (no T+1 delay), no short selling, no margin, no
  derivatives, equities only.
- The ledger doubles as the core of a future payments-style project, so the design must be careful and tested.

### Safety and legal guardrails

- The app teaches and illustrates. It does not tell people what to buy or sell. In India, personalised investment
  recommendations are regulated, so it stays educational, with clear disclaimers.
- No cash prizes and no paid contests. Online money games are heavily regulated in India. A leaderboard with no
  money involved is the safe version.
- Keep personal data minimal (handle-based or anonymous accounts) because collecting names and emails brings
  obligations under India's data protection law.
- Phases 1 and 2 use fictional stocks, so nobody mistakes simulated prices for real ones. Real companies appear
  only in Phase 3, clearly labelled as history from public data.
- Check the current rules before any public launch. This document is not legal advice.

### Scope guard

Equities first. Mutual funds and SIPs arrive in Phase 4 as educational calculators and simulations. "All kinds of
investments" is where projects grow forever, so nothing outside equities starts before the exchange, the ledger
and the backtester are finished.

## 13. Decisions (defaults chosen so work can start; change any of them)

1. **Session model:** simplified as written in section 3, and documented as a simplification in the README.
2. **Order types:** LIMIT and MARKET, DAY and IOC, cancel and modify. No stop orders in Phase 1.
3. **Dashboard:** plain JavaScript first (Week 5). A React version can come in Phase 4 when there are real screens.
4. **Repository:** private until Weeks 1 and 2 are reviewed, then made public with the README status table.
5. **Python:** 3.11 or newer. CI tests 3.11, 3.12 and 3.13.
6. **Week 1 delivered:** types, validation, order book with cancel and reduce, 42 tests (unit tests with
   hand-calculated numbers, plus a randomised test that compares the book with a simple reference model).
