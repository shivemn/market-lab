# Building Market Lab

Market Lab is a practice stock market. A simulated exchange matches orders, a ledger keeps a learner's pretend
₹1,00,000, and a web page shows the day as a price chart and a queue of waiting orders. This note explains the
choices that shaped it, how I tested it, what went wrong along the way, and what it cannot do. Everything in the
market is simulated and nothing here is investment advice.

## The idea that shaped everything: the log is the truth

The exchange does not store "the state of the market". It appends events: an order was accepted, a trade happened,
the session changed. The order book, the price chart and the opening auction are all worked out by reading those
events in order. This has three consequences I came to rely on.

- **Replay is exact.** A day is fully described by its seed and the commands sent to it. Replaying them must give the
  same SHA-256 fingerprint, and that check runs in tests, including for practice sessions with orders placed by a
  person.
- **The web page can recompute the market itself.** It folds the same events in TypeScript, so pausing, speeding up
  and scrubbing need no round trips. The cost is that the rules exist twice. I handle that by having Python write a
  fixture that the TypeScript tests must reproduce, including the opening price on 40 simulated mornings.
- **The server never owns a clock.** It moves time only when the browser asks. That is why a day can pause by itself
  the moment one of your orders trades.

## Money is handled like money

Prices are whole paise, quantities are whole shares, and time is a logical counter in microseconds, so there is no
floating-point arithmetic in the exchange or the ledger. Rates for taxes and charges are exact fractions rounded half
up, in dated schedules that record where each rate came from.

The ledger is double-entry in SQLite. Every transaction's entries add up to zero. The database itself enforces what it
can: entries cannot be edited or deleted, and an account that may not go negative cannot be pushed below zero by any
statement. A `verify()` audit recomputes every balance from the entries and does not trust the stored ones.

An order goes through a gateway. Before it reaches the exchange, the gateway moves the worst-case cost (for a market
buy, the top of the price band plus the highest possible charges) from cash to a reserved account, or locks the
shares for a sale. Each fill is then settled from that reserved money, with one ledger account per kind of charge.
When the order ends, whatever is left goes back to cash. This is why a person cannot spend money they do not have,
and why a statement can show what each charge paid for.

## How I tested it

The rule was that a test is only worth having if it can fail.

- **Hand-worked examples** whose expected numbers I calculated myself rather than copying from output.
- **Randomised tests against simple reference models.** Hypothesis generates long sequences of operations, and a
  deliberately simple version of the book, the exchange, the ledger and the gateway must agree with the real one at
  every step.
- **Reconciliation.** The ledger of a whole simulated day is compared with the event log. The live gateway's ledger
  must equal one rebuilt from the log, and a statement built from transactions must equal the ledger's stored
  balances on 15 random days.
- **Deliberate bugs.** I put mistakes into the code on purpose (break time priority, flip the sign of a charge, swap
  buy and sell) and confirmed the tests fail each time.
- **A pinned day.** A scripted integer-only day must always give the same fingerprint, so any change in behaviour
  shows up as a changed hash.
- **A real browser.** Playwright starts the real server, plays a day, places an order and checks the page.

At the end there are 345 Python tests and 48 web tests, with `ruff` and `mypy --strict` clean, and CI on Python
3.11 to 3.13.

## What went wrong, and what I learned from it

- **A deliberate-bug check passed when it should have failed.** One injected bug survived because the code formatter
  had rewrapped the line I was editing, so I had changed a line that no longer mattered. I re-applied the bug to the
  right line and confirmed it was caught. Lesson: a check that never fails has not been shown to work.
- **A property test found a case I had not thought of.** A random operation that paid an account from itself nets to
  zero and the ledger rightly refused it. The fix was in the test generator, not the ledger, and I wrote down why.
- **Posting trades twice tried to recreate accounts.** The ledger correctly refused to open an account again with
  different settings. The fix was to create only the accounts that are missing.
- **Some of my own expected numbers were wrong.** A test expected brokerage on three orders to be 8,000 paise; the
  right answer was 6,000. The code was right and my arithmetic was not. I now work the number out by hand before
  reading the output.
- **Plain words need testing too.** Early refusal messages showed paise and no Indian digit grouping. Learners read
  these, so I added a `rupees()` helper and tests for the wording.

## Numbers

On a Windows laptop with pure Python, the exchange processed about 242,000 commands per second on a realistic mix
(median 3.4 µs per command), and speed did not change with how full the book was. A simulated day of about 5,000
events takes roughly 0.135 s, and most of that is spent encoding and hashing events and on the traders' decisions, not
on matching. Method and the full table are in [benchmark-results.md](benchmark-results.md).

## What it cannot do

- The price process (a random walk with occasional jumps, with constant volatility) is not calibrated to any real
  stock. By construction the market is close to unpredictable, so no trading strategy can be shown to work on it. It
  teaches how a market works, not how to beat one.
- Delivery trades only, long only, instant settlement. No order modification.
- Charge rates came from secondary sources. They need to be checked against a real contract note and the current
  rules before anyone relies on them.
- Floating-point results in the price process match for the same seed on the same machine and Python, but are not
  guaranteed across different CPUs or Python builds.
- Practice sessions are held in server memory. The ledger is a file and survives restarts.

## What I would do next

An honest backtester that has to beat simple baselines after costs, then real company announcements with an event
study, then a plain-language app for learners. Each depends on the ledger and the cost model being trusted, which is
why they come after this work.
