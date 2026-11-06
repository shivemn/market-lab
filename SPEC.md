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
5. Orders not fully filled move onto the continuous book (DAY limit orders) or are cancelled (market orders and IOC orders).
6. If no prices cross, there is no opening trade, the opening price is the reference price, and all DAY limit orders move to the book.

How it is implemented (Week 3):
- Market orders wait in a separate list during PRE_OPEN, because they cannot rest on the book. Limit orders rest on the book, which may overlap until the auction runs.
- Priority on each side: market orders first (in arrival order), then limit orders from the best price down, and within one price the earliest first.
- Only a few prices need to be tried: every limit price, the tick either side of it, and the reference price. Between two limit prices, every price gives identical totals, so these cover every case. A randomised test compares this shortcut with a brute-force search over every tick in the band.
- Rule 3's final tie-break (the lower price) can never actually decide anything. The set of best prices after the first two rules is one unbroken run of ticks, so the one nearest the reference price is unique. The rule is kept so the result is always fully determined.
- After the auction the book is never crossed. This follows from the rules, and the exchange checks it every time.
- Events come in this order: `AuctionResult`, the `Trade` events (price is the auction price, there is no aggressor), cancellations of unfilled market and IOC orders, then `SessionChanged(OPEN)`.
- Opening straight from CLOSED to OPEN is still allowed and skips the auction.

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
`SessionChanged`, `OrderAccepted`, `OrderRejected`, `OrderCancelled`, `OrderModified`, `OrderExpired`, `Trade`, `AuctionResult`. (The instrument's rules are in the log header, so there is no separate listing event.)

### Reserved for later phases
`NEWS_EVENT` (Phase 3), `STRATEGY_DECISION` (Phase 2). The log schema and the reader ignore unknown types safely, so adding them later does not break old logs.

### Storage and verification (built in Week 4)
- **File format:** JSON Lines, always written with plain `\n` line endings. Line 1 is a header (format name, version, the instrument's rules, and for simulated runs the settings including the seed). Then one event per line in canonical form (keys sorted, no spaces). The last line is a footer with the event count and a SHA-256 fingerprint over the event lines.
- **Reading checks everything:** header, footer, gapless `seq` from 1, count and fingerprint. A file that was edited, cut short, or had events removed or swapped is refused with a plain error.
- **Replay has two meanings here.** (1) *Fold*: `MarketState` rebuilds the market (book, last price, volume) from events alone, and a property test checks it equals the live exchange after every random command. (2) *Re-run*: `marketlab replay` re-runs a simulated log from the settings in its header and checks the fingerprint matches. Events do not record rejected orders' details, so a log cannot be re-executed command by command; the seed is what makes a day reproducible.
- **Known limits:** the header is not covered by the fingerprint (changing the seed in the header is caught by `replay`, but changing, say, the tick size in a header with no re-run is not); same seed gives the same day on one machine and Python, and in practice everywhere, but cross-platform float equality is not guaranteed (see `sim/rng.py`), so the pinned golden fingerprint covers only an integer-only scripted day.
- **Parquet export** (for DuckDB) is postponed to Phase 2, when there is something to analyse.

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
       def on_event(self, event: Event) -> list[Command]: ...
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
    codec.py     event <-> canonical JSON line, fingerprint
    log.py       log file writer and reader (header, events, footer)
    projection.py  rebuild the market from events (what a screen uses)
    describe.py  plain-language one-line event descriptions
    sim/         rng, price process, traders, the simulation loop
    api/         FastAPI app and WebSocket (Week 5)
    cli.py       run, show, replay
  web/           React dashboard (Vite, TypeScript)
  tests/
    unit/  property/
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
| 4 | Event log, replay, hash check, seeded simulator agents (done) | Event sourcing, stochastic processes |
| 5 | CLI, API, WebSocket, first dashboard (done) | Streaming, state snapshots |
| 6 | Opening-auction screen, benchmark, diagrams, README (done) | Writing the story, measuring honestly |

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
3. **Dashboard:** React and TypeScript (Week 5), built from the design mock-up. The browser folds the same events into the same market picture as `MarketState`; a shared fixture (`tests/export_fixture.py`) checks the two agree.
4. **Repository:** private until Weeks 1 and 2 are reviewed, then made public with the README status table.
5. **Python:** 3.11 or newer. CI tests 3.11, 3.12 and 3.13.
6. **Week 1 delivered:** types, validation, order book with cancel and reduce, 42 tests (unit tests with
   hand-calculated numbers, plus a randomised test that compares the book with a simple reference model).
7. **Week 6 delivered:** the dashboard's "opening auction" screen (it recomputes the auction price from the orders in
   TypeScript and a test checks it against the exchange's own answer on 40 simulated mornings), a benchmark
   (`python -m benchmarks.bench_exchange`, results in `docs/benchmark-results.md`), architecture diagrams
   (`docs/architecture.md`), screenshots, and the portfolio README. Phase 1 is complete.
8. **Phase 2 decisions (agreed):** delivery product only (intraday later); instant settlement; a small database for
   accounts that persist across days (SQLite: one file, in the standard library, real transactions, and it can be
   moved to Postgres in Phase 4); long only, no short selling; one kind of trading to begin with.
9. **Week 7 delivered:** `marketlab.ledger`. Accounts hold one unit each (paise or shares of one stock); a transaction
   is a set of signed entries that add up to zero per unit; practice accounts cannot go below zero (checked in Python
   with a clear message and again by a database trigger); entries and transactions are append-only; a `cause` key
   makes replaying the same log harmless; `post_trades` turns `Trade` events into entries. Tested with hand-worked
   examples, a Hypothesis comparison against a plain dictionary, a reconciliation of the ledger against the trades on
   25 simulated days, and deliberate bugs that the tests must catch.
10. **Week 8 delivered:** `marketlab.costs` and `marketlab costs`. Rates are exact fractions (never floats), rounded to the
    paisa with halves up. Government and exchange charges are a dated `ChargeSchedule` with its source; the broker's own
    charges are a separate `BrokerPlan` (default "zero": no brokerage, no demat fee). The NSE transaction charge is
    Rs 307 per crore from 1 March 2026 (NSE circular NSE/FA/73061; Rs 297 before). STT 0.1% both sides, stamp duty
    0.015% on buys, SEBI fee Rs 10 per crore and GST 18% (on brokerage, demat, exchange and SEBI charges, not on STT or
    stamp duty) come from broker pages and should be checked against the statutes before anyone relies on them.
    Charges are worked out per order and collected fill by fill, so splitting an order never changes its total, and a
    flat brokerage lands on the first fill. Each kind of charge has its own ledger account. Simplifications: demat fee
    charged per sell order, not per holding per day; delivery equity on the NSE only.
11. **Week 9a delivered:** `marketlab.ledger.Gateway`. Before an order reaches the exchange, a buy sets aside its
    worst case (price x quantity plus the highest charges it could incur; a market buy is priced at the top of the
    band and the refusal message says so) and a sell locks its shares so they cannot be sold twice (plus the fixed
    fees of the broker plan, nothing on the default plan). Each fill pays from what was set aside; a buy that trades
    below its limit gets the difference back; an order that ends (filled, cancelled, expired, IOC remainder, rejected
    by the exchange) returns whatever is left. All of it stays in the ledger in `reserved` and `locked` accounts.
    Refusals are plain sentences with the numbers. Changing an open order is not supported yet (cancel and re-enter).
    Tested on a real exchange with hand-worked cases, a random-sequence test that checks after every step that the
    ledger agrees with the gateway and the exchange's book, and that the live ledger equals one rebuilt from the log
    alone; five deliberate bugs are caught.
## 14. Design for Week 9b: the live practice session (to review before building)

**Principle: the server never owns a clock.** It advances the simulation only when asked. The browser keeps the timer,
so speed and pause are the browser's choice and pausing costs nothing. The simulation is already a deterministic
event loop, so this is a small step, and it needs no threads.

**A session** is one simulated day with one practice account: `{seed, config, account, ledger, gateway, simulator state}`.

| Call | What it does |
|---|---|
| `POST /api/sessions` | Start a day (seed, owner). Opens the account if new. Returns the session id and the events so far (the pre-open). |
| `POST /api/sessions/{id}/advance` `{seconds}` | Run the simulation forward. Returns only the new events and the portfolio. |
| `POST /api/sessions/{id}/orders` | Check and reserve, then send the order at the current simulated moment. Refusal is a 422 with the plain sentence. |
| `DELETE /api/sessions/{id}/orders/{order_id}` | Cancel. |
| `GET /api/sessions/{id}` | Current portfolio: cash, reserved, holdings, open orders. |

**Determinism with my orders in the day.** The log records every command of mine with the simulated moment it was
sent. Replay re-runs the same seed and injects the same commands at the same moments. At the same microsecond, my
command goes in before the simulated traders act. A test checks that the same seed and the same commands always give
the same fingerprint and the same ledger. The simulated traders react to my orders through the book, so the rest of the
day differs from the day without me, and that is the point.

**Advance stops early** when one of my orders trades, so the page can pause and explain it ("12 of your 20 shares
traded, 8 are still waiting behind 14 shares"). The browser decides whether to pause.

**Where the code goes:** the simulator gets a stepping interface (`advance_to(t)` and `inject(command)`) next to the
existing `run_simulation`, which stays as it is and becomes a loop over the new interface. The existing WebSocket
playback stays for watching days. Sessions live in memory; the ledger lives in SQLite.

**Tests planned:** the same seed with no commands gives the same fingerprint as today's `run_simulation` (nothing
regresses); a recorded session replays exactly; random commands interleaved with random advances keep every ledger
invariant from Week 9a; refusals do not change the day.

**Decisions made:** advance-based API (agreed); auto-pause on my fills (the server pauses; the page decides what to show); no modify yet.

12. **Week 9b delivered:** `Simulation` (a steppable day; `run_simulation` is now this class run to the end, and all 28
    reference days kept their fingerprints), `PracticeSession`, and the `/api/sessions` endpoints. User orders are
    numbered from 1,000,000,001 so they never disturb the traders' ids. `advance` stops just after the moment one of
    your orders trades (`now` is that microsecond plus one, so nothing is skipped on replay). Starting a new day for
    an account ends its old day and returns anything still set aside; a crashed session's leftovers are returned the
    same way. Accounts live in a SQLite file (`marketlab serve --db practice.db`), so cash and shares carry over.
    A random-sessions test (random advances, orders and cancels) checks consistency after every action and that
    replay from the seed and the commands gives the same fingerprint and the same books; it found one real bug while
    being written (a market order waiting for the opening auction was missing from the account's open orders).
    Known limits: sessions are kept in memory (lost if the server restarts, which returns the money on the next
    start); the command script is not yet written to a log file; one server process, with one request at a time.
13. **Week 10 delivered:** the Practice tab. `usePractice` is the clock (asks the server to advance `speed x 0.25` seconds
    four times a second; every call goes through one queue so replies cannot arrive out of order, and the page checks
    its event count against the server's after every reply). Server replies now carry `new_ends` (command boundaries)
    so the page folds whole commands only. `previewOrder` walks the queue on screen and says in plain words what an
    order would do (trade now, part now, join the queue behind N shares, or nothing); the server's refusal messages use
    rupees with Indian grouping. Narration says "Your order traded: you bought 5 shares at ..." for your own trades.
    Checked end to end against a real server with Playwright (refusal, market buy, resting limit order, auto-pause on a
    fill). Known limits: no modify, no marks for your fills on the chart yet, practice state lives in the server's memory.
14. **Week 11 delivered:** `build_statement(ledger, owner)` reads only ledger transactions. Reservations and releases
    move money between an owner's own accounts, so they are left out; "money" means cash plus cash set aside, and
    "shares" means free plus locked, so the statement does not jump while orders are open. It lists the starting
    money, share grants, and each fill with the charges it paid, and `check()` compares the result with the ledger's
    stored balances. `GET /api/sessions/{id}/statement` serves it, and the Practice tab shows "what trading has cost
    you" by charge line. The result splits into price moves and charges. Holdings are valued at the last traded price
    (the previous close before any trade). Tests include 15 random days reconciled against the live portfolio, and two
    deliberately broken versions (wrong sign on charges, buy and sell swapped) that the tests catch.
15. **Practice screen redesign (pass 1):** one layout, three looks (Desk, Terminal, Notebook) set by tokens in
    `theme.css`. The account (worth, result, cash, shares, charges paid) is always visible at the top. Trading sits on
    one side: order ticket, a clickable price ladder (click a price to use it), and waiting orders. The chart has no
    explaining paragraph; short "?" notes replace paragraphs. "What just happened" is replaced by a permanent log of the
    person's own orders and fills, and a trade tape that refreshes at most once a second while the day runs (the Day
    tab's feed is slowed the same way). The Day and Opening auction tabs take the new themes and header but keep their
    old layout for now.
16. **End-of-day summary:** when the market closes, a dialog says what the day did to the account in money: worth at the
    start and the close, the part from price moves, and the part paid in taxes and charges. Shares carried into a new day
    are valued at where the previous day ended, so the daily results add up to the whole result (checked: -142.69 and
    +212.00 gave +69.31, the change in worth). The result is on paper while shares are held. The list of past days is kept
    in the page, not in the database, so it starts again when the page is reloaded.

17. **Steadier page (redesign pass 3):** nothing below a live region may move while the day plays. The queue and the
    price ladder always draw the same number of rows (empty ones are blank), the recent-trades table keeps 12 rows,
    the order preview, activity panel and What-just-happened box have a fixed minimum height, the header price line
    no longer wraps, and the scrollbar space is reserved. Measured with a script: the page height stays the same
    across a whole replayed day in all three themes. The chart lost its in-plot "Highest", "Lowest", "Market opens at"
    and "Biggest move" text, which collided with the price line and the cursor label; Open, High, Low and yesterday's
    close sit in a row above the chart instead, and the markers keep a hover tooltip. The "Before the open" chip in the
    Terminal theme now has a fixed yellow background with dark text.
18. **A market of twelve companies (Phase 3):** `world.py` runs twelve exchanges on one clock. Prices share a market
    move and a sector move (`factors.py`, drawn once from the day's seed) plus their own noise, so an index is calmer than
    one stock but not flat (a test checks both). `index.py` implements one formula, level = sum(price x q) / divisor, with
    q = free-float shares (cap-weighted), 1 (price-weighted) or 1/(n x base price) (equal-weighted); `after_split` and
    `rebalance` keep the level unchanged. Days open at the previous close and the index carries on. Per-company profit
    and loss uses the average-cost method and adds up exactly to the account's total change (tested). Noise traders pull
    quotes more than 0.4% from the price, which removes stale-order spikes. Day and Opening-auction tabs are lessons on one
    company (UDHAAR) and never touch the account.
19. **Saved history and the market clock:** every practice day that is played to the close (or left after trading) is
    written to a `days` table (migration 2: owner, seed, closing prices, result, per-company result, every fill), outside
    the append-only books, so history and the next day's opening prices survive a restart. `GET /api/accounts/{owner}/days`
    serves it. The simulated day is shown on the real clock: the first simulated minute is the 9:00-9:15 pre-open and the
    next ten are 9:15-15:30 (`clock()` in `lib/format.ts`). The Practice screen is hidden, not unmounted, when you visit
    another tab, and the day pauses while you are away. Trade text names the company ("13 UDHAAR shares").
20. **News, comparison rules and results over time:** `news.py` schedules five announcements per day from the seed and
    adds them to each affected company's fair value as a log-return (60% within 5 s, the rest over 120 s). They are not
    log events, so the replay path (`World._common`) must include them, and it does. The page sees an item only after its
    time, and its size only after the close (a test checks both). `rules.py` gives three shadow portfolios (cash, hold
    all twelve, a 3-look trend rule) from per-minute prices, shown only after the close. Past days keep their news and the
    page draws worth over days and totals. The event list in Watch a day keeps every line and is a fixed-size box.
