# Market Lab

A practice stock market that runs on your computer. Simulated traders and a real matching engine make a price move
through the day. You trade with ₹1,00,000 of virtual money, see your order join the queue, and see exactly what each
trade cost you in Indian taxes and charges. The point is to show how a market actually behaves: orders wait in line,
get partly filled, and move the price when they are large.

Under the page there is a small exchange with real market rules (price-time priority, tick sizes, price bands, an
opening auction), an ordered event log that replays exactly, and a double-entry ledger in SQLite that keeps your money
honest. All prices and people are simulated and the companies are made up. Nothing here is investment advice.

For the story of how it was built and what testing caught, read [docs/WRITEUP.md](docs/WRITEUP.md).

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
- **A ledger and a gateway** (`ledger`): accounts and transactions in SQLite. Every transaction adds up to zero, and the
  database itself refuses overdrafts and edits. Before an order is sent, the gateway sets aside the worst-case cost,
  and it settles each fill from that money.
- **Indian trading costs** (`costs.py`): brokerage, STT, exchange charge, SEBI fee, stamp duty and GST, as exact
  fractions in dated schedules, charged fill by fill.
- **A practice session and statement** (`session.py`, `ledger/statement.py`): your orders in a live simulated day, and
  a statement rebuilt from the ledger that must agree with the ledger's own balances.
- **A web page** (`web`): React and TypeScript. It folds the events into the market itself, so you can scrub through
  the day without waiting for the server, and its Practice tab is where you trade.

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
marketlab serve --db practice.db
```

Then open http://127.0.0.1:8000. Press play, drag along the chart, or open the "Watch a day" and "Opening auction" lessons to see why the
day opened at its price. In the Practice tab, start a day, press play, and buy a few shares with "Best price now".
The first page is a sign-in: pick a username and a secret (a favourite word and a number, like `purple42`), or press "Play as a guest".
Your account, its money and its history are kept in `practice.db`, so they carry over to the next day; delete the file to start fresh.
![The sign-in page](docs/img/sign-in.png)

Running it alone and want no sign-in page? Use `marketlab serve --db practice.db --no-login`. The server listens on your own computer only.

To put it online, see [docs/DEPLOY.md](docs/DEPLOY.md) (a `Dockerfile` and `render.yaml` are included). The built page `web/dist` is not in git, so a fresh clone must run `npm run build` first.

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
- **Two databases, one test suite.** Every test that uses the ledger also runs against a real PostgreSQL server
  (`MARKETLAB_TEST_PG=postgresql://...`; each in-memory ledger becomes a fresh schema). Extra tests cover what only
  appears with several servers sharing one database: starting together, two servers spending the same money, and a
  deadlock between workers that the test can provoke on demand (it fails if the fix is removed).
- **Static checks.** `ruff` and `mypy --strict` on the code and tests, run in GitHub Actions on Python 3.11 to 3.13,
  a PostgreSQL job and a web job.

```
pytest                       # 418 tests
ruff check .
mypy
cd web; npm test; cd ..      # 64 tests
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

## How the maths works

The full write-up, with worked examples produced by the code, is in [docs/MATHS.md](docs/MATHS.md). In short:

- **Prices:** each company's hidden fair value moves as geometric Brownian motion with jumps, plus a market move shared by
  all twelve (scaled by each company's beta) and a sector move shared by three.
- **Trades:** price-time priority during the day, and one equilibrium price at the open that maximises the shares traded.
- **The index:** $\text{Index} = \sum p_i q_i / D$ with free-float shares as the weights and a divisor $D$ that keeps the
  level continuous. Price-weighted and equal-weighted versions are one toggle away.
- **Costs:** STT 0.1%, exchange charge ₹307 per crore, SEBI ₹10 per crore, stamp duty 0.015% on buys, 18% GST on the
  broker and exchange fees, all exact fractions.
- **Profit and loss:** average-cost method per company; the parts add up to the whole account exactly.

## How many people can play at once?

Measured, not guessed: one server process handles about 100 people comfortably at normal speed (about 25 at fast playback), then slows sharply. With PostgreSQL and two workers the same machine held up noticeably better past that point (the honest limits of my 2-core test machine are in the document below). The test, the numbers and what they change are in [docs/LOADTEST.md](docs/LOADTEST.md); the test itself is `tools/loadtest.py`. To try several workers: `pip install -e ".[api,postgres]"`, then `marketlab cluster --workers 4 --db postgresql://user:password@host/database`.

## System design

By default one Python process serves the web page and the API, with a SQLite file for data: nothing else is needed to run
it. For more people, the same server can run as several worker processes behind a small router, sharing one PostgreSQL
database (`marketlab cluster`, described below). The code is the same either way.

```mermaid
flowchart LR
    subgraph browser["Browser: React + TypeScript"]
        ui["Screens<br/>Practice, Watch a day, Opening auction"]
        gate["Sign-in page<br/>username + secret, or guest"]
        clock["The clock<br/>asks for time every second"]
        fold["fold(events)<br/>chart, queue, ladder, P&L"]
    end
    subgraph router["Router: only with marketlab cluster"]
        route["Sends each person to the same worker<br/>(by the name at the front of their token)<br/>relays the live WebSocket"]
    end
    subgraph server["Server: FastAPI, one lock per process"]
        authn["Auth<br/>/api/auth/enter, guest, me, logout<br/>scrypt hash, attempt limits"]
        api["REST<br/>/api/worlds, /api/runs,<br/>/api/accounts/{owner}/days<br/>(your own account only)"]
    end
    subgraph world["Practice world, in memory"]
        sims["12 simulations<br/>one per company, one shared clock"]
        factors["Market and sector factors<br/>seeded random walks"]
        news["News schedule<br/>8 items a day (6 headlines, 2 silent), from the seed"]
        gws["12 gateways<br/>reserve, then settle"]
    end
    subgraph disk["SQLite file (default) or PostgreSQL (shared)"]
        books["Ledger<br/>accounts, transactions, entries<br/>(append-only)"]
        days["days table<br/>history and closing prices"]
        users["users, logins, attempts tables<br/>secret hashes, token hashes, rate limits"]
    end
    ui --> gate --> authn --> users
    ui --> clock --> api
    clock -. "with several workers" .-> route -.-> api
    api --> world
    factors --> sims
    news --> sims
    sims --> gws --> books
    api --> days
    api -- "new events and a snapshot" --> fold --> ui
```

**The event log is the truth.** Each company's exchange only appends events (order accepted, trade, session changed).
The order book, the chart, the index and your profit and loss are all worked out by reading events in order. The browser
runs the same fold as the server, which is how the page and the server can never disagree about the market.

**The browser owns time.** The server has no clock. Once a second the page asks it to move the day forward by
`speed` simulated seconds (it was four times a second until the load test showed that cost too much). The twelve companies move in 0.2-second steps on one clock, so a fill in any
company can pause the whole day at the exact moment it happens (switchable). This also makes pause, speed and
scrubbing free, and the same seed always gives the same day.

**News and comparison rules.** `news.py` holds a box of about thirty made-up headlines, each marked *major* (usually
matters) or *minor* (usually does not), with an obvious direction where there is one. Each day draws six at random and
rolls dice from the seed: does this one move the price at all (75% of major ones, 15% of minor ones), and which way (a
major one goes its obvious way four times in five; a minor one is a coin toss). Two more "silent shocks" move a random
company with no headline. So there is no table of what moves what, and the unpredictability comes from the dice, not
from rules a person could learn. A move that happens adds a log-return to the companies it touches (60% within five
seconds, the rest over two minutes), the same way the shared market and sector moves enter, so the exchange is unchanged
and a replay from the seed still matches. The page gets a headline only after its time, with no hint of whether it will
matter; silent shocks and what each item did are shown after the close. `rules.py` computes shadow portfolios from the
day's prices once the day is over (stay in cash, hold all twelve equally, follow a simple trend rule) so your result has
something to be compared with. They never trade in the market and ignore charges.

**Accounts.** There is no email and no real name. A person picks a username (3 to 20 letters, numbers or underscores)
and a *secret*, a favourite word and a number such as `purple42`. It is a password under a friendlier name and is treated
like one: only a salted scrypt hash is stored, never the secret; capitals and spaces at the ends are ignored; at least six
characters, not numbers alone, not a common one. One form does both jobs. A username that exists needs its secret, and
any failure reads "That username is taken, or the secret is wrong." A free username first asks "Create it?", so a typo
does not quietly make a new account. Five wrong tries for one username from one address (30 for the username from
anywhere) lock it for 15 minutes. "Play as a guest" makes `guest-xxxxxx` with no secret; a hyphen is not allowed in a
username, so a person can never take a guest name. A sign-in gives the browser a random token; the database keeps only
its hash, and it expires after 30 days. When sign-in is on, every practice route uses *your* account whatever the
request says, and another person's day looks like no day at all (404). `marketlab serve --no-login` switches all of this
off for one person on their own computer.

**An order's path.**

```mermaid
sequenceDiagram
    participant P as Page
    participant S as Server
    participant G as Gateway
    participant X as Exchange (one company)
    participant L as Ledger
    P->>S: POST /api/worlds/{id}/orders
    S->>G: place(order)
    G->>L: reserve the worst-case cost (refused if you cannot afford it)
    G->>X: NewOrder
    X-->>G: events (accepted, trades)
    G->>L: settle each fill, charges as separate entries
    S-->>P: new events and a snapshot
    P->>P: fold the events, redraw
```

**Where the data lives.**

| Data | Where | Kept after a restart |
| --- | --- | --- |
| Cash, shares, taxes and charges | The ledger (SQLite or PostgreSQL), double-entry, entries cannot be edited or deleted | Yes |
| Past days, your trades, news, closing prices | `days` table in the same file (migration 2) | Yes |
| Usernames, secret hashes, sign-in tokens (hashed), wrong-guess counts | `users`, `logins`, `attempts` tables in the same database (migrations 3 and 4) | Yes |
| The day in progress (event logs, open orders) | Server memory, rebuilt from the seed | No: a restart abandons the day |
| What you see on screen | Folded in the browser from the events | Rebuilt from the server |

**Decisions and what they cost.**

| Decision | Why | The cost |
| --- | --- | --- |
| Integer paise and shares everywhere, exact fractions for charges and the index | No rounding drift: your balance equals the sum of your entries | Some formulas need `Fraction` care |
| Seeded simulation, event log with SHA-256 fingerprint | A bug or a result can be replayed exactly | Floating point is only stable on the same machine and Python |
| Client-driven clock | Simple server, no streaming, easy pause and speed | The day only moves while a page is asking |
| One process, one lock, SQLite | Zero setup, easy to reason about | One writer at a time: about 100 comfortable players per process (see the load test), not thousands |
| Twelve independent exchanges plus shared factors | Index and per-company results behave like a real market | Twelve times the events (roughly 60,000 per day) |
| Username plus a word-and-number secret, hashed with scrypt | No email, no extra service, nothing real to leak | Nobody can reset a forgotten secret; a guessable secret is guarded only by the attempt limits |
| Sign-in limits counted in the database, not in memory | Several worker processes share one count | A few extra queries per sign-in attempt |
| Same name always goes to the same worker (name is the front of the token) | A day lives in one worker's memory; routing needs no lookup | A dead worker loses the days it held; a person's load cannot be moved to a quieter worker |
| SQLite by default, PostgreSQL by setting `--db postgresql://...` | Local use stays zero-setup; PostgreSQL gives shared access and survives hosting restarts | Two schema lists (`MIGRATIONS`, `MIGRATIONS_PG`) to keep in step; about 2 ms per ledger posting instead of well under 0.1 ms |
| History outside the append-only books | The books stay simple and provable | History is a convenience, not an audit record |
| News as an extra return in the price process | No change to the exchange or the log format | The news is not an event in the log, so it is rebuilt from the seed and not read from the log |

**Several processes.** `marketlab cluster --workers 4 --db postgresql://...` starts four server processes and a router in
front of them. Money, accounts, history and sign-in limits live in PostgreSQL, so every worker sees the same truth. The
one thing that does not is the day in progress, which lives in the memory of the worker that started it, so the router
sends all of one person's requests to the same worker: it reads the person's name from the front of their sign-in token
(`shivam.k3j...`) and always maps the same name to the same worker. Things that need care when processes share a
database: the shared system accounts (market cash, charges) are updated by everyone, so the ledger always writes a
transaction's entries in the same account order, which stops two workers from deadlocking on each other (a test
reproduces the deadlock without it); two workers spending one person's money at once cannot both succeed (the database
enforces the no-overdraft rule itself); and workers starting together migrate the database one at a time under a lock.
If a worker dies the router starts it again and the days it held are lost, like any restart; if the router is stopped, the
workers stop with it.

**What would change to scale it further.** Done so far, from the load test: no tiny cap on live days, idle days let go after 30 minutes, one request a second, several workers on PostgreSQL. Each person's day is independent, so the natural step beyond that is one worker per day with the
event log published to a stream. That is where a Kafka topic would fit; it is not built, and the current design does
not need it. The ledger would move to Postgres with the same schema and the same two rules (every transaction sums to
zero, entries never change).

See [docs/architecture.md](docs/architecture.md) for the single-company details and the exchange rules.

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
- Simulated traders have no cash limits and there is one instrument. You can place and cancel orders, but not change
  an open order.
- The price process is not calibrated to any real stock and its volatility is constant, so no strategy can be shown
  to work on it. It is for learning how a market works, not for forecasting.
- A day in progress lives in server memory and is abandoned on restart. The ledger (cash and shares) and the saved
  history are in the database file and are not.
- Several workers need PostgreSQL and a machine with spare cores; the router is a single Python process, so it is itself a ceiling (estimated at roughly 500 requests a second, not measured on big hardware). Days held by a worker are lost if it dies.
- Sign-in is deliberately light: no email, so a forgotten secret means a lost account; attempt limits are kept in memory per server process; guest accounts and their data are not cleaned up yet; the login token lives in the browser's local storage. Fine for a practice game of made-up money, not a pattern for a bank.
- Delivery trades only, long only, instant settlement. Charge rates came from secondary sources and need checking
  against a real contract note before anyone relies on them.
- The test fixture for the page is about 0.8 MB.

## Roadmap

Phase 2 (practice accounts, a ledger, Indian trading costs, your own orders, statements) is finished and described
below. Next, in order and only if the project continues: an honest backtester that has to beat simple baselines after
costs, then real announcements with an event study, then a plain-language app for learners. The plan and decisions
are in [SPEC.md](SPEC.md).

## Phase 3: a market of twelve companies

![Twelve made-up companies in four sectors, the Shifty 12 index and how each company moved it](docs/img/market-index.png)

The Practice tab now trades **twelve made-up companies**, three in each of the four sectors an economist names
(primary, secondary, tertiary, quaternary), all on one clock with one seed. Their prices move together because each is
built from a market-wide move, a sector move and its own noise, the way real stocks are. Each day opens at the
previous day's closing prices.

The **Shifty 12** index is worked out with the real formula: the sum of price times shares open to the public, divided by
a fixed divisor. You can switch between by-company-size (Nifty, Sensex), every-company-the-same, and the Dow-style
dearer-shares-count-more, and the Practice tab draws the index through the day under the company chart. The divisor logic is tested with a share split. Your result is shown company by company
(locked in, on paper, charges, net) and against the index.

![The Practice tab: chart, order ticket, price ladder, your orders and what each trade cost](docs/img/practice-light.png)

## Phase 2: practice accounts

![The Practice tab: chart, order ticket, price ladder, your orders and what each trade cost](docs/img/practice-light.png)

The page has a light and a dark look, chosen at the top right (the first visit follows your computer's setting).

![The statement: every trade, each charge line, and the result after charges](docs/img/statement-view.png)

![The same screen in the dark look](docs/img/practice-dark.png)

Open the **Practice** tab, start a day and press play. You can place an order at any moment. The page tells you in
plain words what it would do before you send it ("3 shares already waiting at that price would trade before yours"),
and if you cannot afford it, it says exactly why. Your orders show in yellow in the queue. When one of them trades the
day pauses by itself and explains what happened. The browser keeps the clock; the server only moves the day when asked,
so pausing costs nothing and a day with your orders in it can still be replayed exactly.

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
| 9b | A live practice session: place and cancel orders in a day that moves only when you advance it (API; the page follows in Week 10) | done |
| 10 | The Practice tab: order ticket with a plain-words preview, your account, open orders, a day that pauses when your order trades | done |
| 11 | Statements built from the ledger alone, reconciled against its balances; "what trading has cost you" by charge line | done |
| 12 | Write-up, README, demo script | done |

Scope for now: delivery trades only, long only (no short selling), instant settlement. Each is a simplification
that will be lifted later.

## Layout

```
src/marketlab/core/     order types, validation, order book, auction price, events, the exchange (no I/O)
src/marketlab/codec.py, log.py     events as canonical text, the log file with its fingerprint
src/marketlab/projection.py        the market rebuilt from events alone
src/marketlab/session.py           a practice session: one day, one account, your orders
src/marketlab/costs.py             Indian delivery-trade charges, exact
src/marketlab/ledger/   practice accounts and the double-entry ledger (SQLite), the order gateway, and statements
src/marketlab/sim/      random price process and the simulated traders
src/marketlab/api/      the web server: REST and a WebSocket that plays a day back
src/marketlab/cli.py    the `marketlab` command (run, show, replay, serve)
web/                    the React page (TypeScript, Vite)
benchmarks/             the speed benchmark
docs/                   architecture diagrams, benchmark results, screenshots
tests/unit/             hand-calculated examples
tests/property/         randomised tests against reference models
```
