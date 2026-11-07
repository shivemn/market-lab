# Load test: how many people can play at once?

Written before any login code, so the design that follows is built around measured numbers, not guesses.

## What was tested

`tools/loadtest.py` makes N fake users (`lt00001`, `lt00002`, ...). Each one does what the page does:
starts a practice day, then every 250 ms asks the server to move the clock on by `speed x 0.25` simulated
seconds, and places a market order every 6 seconds. Every request is timed. `tools/serve_for_loadtest.py`
starts the real server with only one thing changed: the live-day cap (see finding 1) can be raised.

```
python tools/serve_for_loadtest.py --db load.db --port 8100 --cap 5000
python tools/loadtest.py --users 50 --seconds 25 --speed 1 --server-pid <pid of the server>
```

Setup of the runs below: a 2-core cloud sandbox, server and fake users on the **same** machine (so the
numbers are slightly pessimistic for the server), one server process, 25 seconds of play per user.
"Wanted" is how many requests per second the pages would send (users / 0.25 s).

## Results

Playback speed 1 (the default):

| Users | Requests/s wanted | Requests/s served | Median | Slowest 5% | Server CPU | Memory |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 3.6 | 5 ms | 7 ms | 2% | 58 MB |
| 10 | 40 | 37.5 | 4 ms | 7 ms | 13% | 65 MB |
| 25 | 100 | 91 | 6 ms | 13 ms | 32% | 77 MB |
| 50 | 200 | 182 | 15 ms | 57 ms | 68% | 97 MB |
| 75 | 300 | 203 | 326 ms | 381 ms | 81% | 110 MB |
| 100 | 400 | 170 | 456 ms | 630 ms | 73% | 117 MB |
| 200 | 800 | 84 | 999 ms | 5.5 s | 48% | 145 MB |

Playback speed 10 (each request simulates 2.5 s of market instead of 0.25 s):

| Users | Median | Slowest 5% | Server CPU | Memory |
|---:|---:|---:|---:|---:|
| 5 | 10 ms | 17 ms | 14% | 81 MB |
| 10 | 11 ms | 20 ms | 30% | 106 MB |
| 25 | 33 ms | 272 ms | 77% | 176 MB |

## What this says

1. **The shipped server keeps at most 4 live days (`MAX_WORLDS_KEPT = 4`).** A fifth person starting a day
   silently ends the oldest person's day. With 8 users, 4 lost their day (404 on the next tick).
   Fine for one laptop; the first thing a crowd breaks.
2. **One server process handles roughly 50 comfortable users at normal speed, about 25 at speed 10.**
   One request costs about 4-5 ms of CPU, and the server does one at a time (one process, one global
   lock), so it tops out near 200 requests/s. Past that, requests queue: delay jumps from tens of
   milliseconds to hundreds, then seconds. Adding more cores does not help while it is one process.
3. **Most of that load is the 250 ms polling, not the trading.** 100 users send 400 requests a second to
   move 100 clocks. Sending one request per second instead would cut the number of requests four times (the
   simulation work itself stays the same; see "After step 1").
4. **Memory grows with how much of the day has been played**, because each day keeps its full event list.
   Speed 10 used about 4 MB per user after 25 s (40% of a day), so a full day is roughly 10 MB.
   500 people mid-day is on the order of 5 GB; a free 512 MB host holds about 40 players.
   (Estimate from two short runs, not a measurement of full days.)
5. **A restart loses every day in progress.** Only finished or abandoned days reach the database.

## What changes because of this

- Raise the live-day cap and expire idle days after a timeout instead. **Done** (500 live days, idle 30 minutes).
- Poll once a second, not four times. **Done** (see below).
- Run several server processes, with each user always sent to the same one (their day lives in memory).
- Move the database from SQLite to Postgres, since many processes cannot share one SQLite writer comfortably.
- Free 512 MB hosting is a demo, not a crowd: plan for tens of players there, hundreds only on a bigger box.

Caveat: fake users are polite and identical. Real people open extra tabs, pause, and leave days
half-finished, which the idle timeout has to handle.

## After step 1 (cap raised, idle days let go, polling once a second)

Same machine, same test (`--tick 1.0` is now the default because the page now asks once a second):

| Users | Speed | Requests/s served | Median | Slowest 5% | Server CPU | Memory |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1 | 92 of 100 | 10 ms | 33 ms | 53% | 145 MB |
| 200 | 1 | 106 of 200 | 1.4 s | 1.9 s | 84% | 195 MB |
| 400 | 1 | 37 of 400 | 4.7 s | 9.8 s | 47% | 234 MB |
| 50 | 10 | 39 of 50 | 0.9 s | 1.5 s | 88% | 303 MB |

- At normal speed, 100 users are now smooth (before: 456 ms median at 100 users). One process holds
  roughly **100 comfortable players, up from about 50**. Not four times: each request now carries four
  times as much simulated market, so the total simulation work is unchanged; only the per-request
  overhead (building the page snapshot, JSON) shrank.
- At speed 10 the simulation itself is the cost, so the gain is small: about 25-30 comfortable players.
- Past the limit the server does not crash; it queues. At 400 users a few requests were cut off by the
  test's own client (ReadError), and the fake client shares the CPUs, so treat 200+ as "over the limit",
  not as exact figures.
- The page now moves in one-second steps instead of quarter-second steps (the clock and chart jump
  once a second at speed 1, ten simulated seconds at a time at speed 10). Trades still pause the day
  exactly when they happen.
- Further gains need more than one process (step 3 of the plan): the next wall is one core.

## What signing in costs

A secret is checked with scrypt, which is slow on purpose: about 50 ms of CPU each. Measured on the same
machine, 20 people signing in at the same moment all finished in 0.6 s, and 100 at once in 2.8 s (about
35 sign-ins a second). That is fine, because someone signs in once per visit; a rush of hundreds in one second
would wait a few seconds and slow other players a little while it lasts. The load test above does not sign in
(it runs the server with sign-in off), so its numbers are for playing, not for signing in.

## Several workers on PostgreSQL (step 3)

Setup: the same 2-core machine, but now **everything shares those two cores**: the fake users, the router, the
workers and the PostgreSQL server. Speed 1, 30 seconds of play, users signed in directly in the database
(`--db`), so the router can send each one to a fixed worker. Each row is one run, so expect noise of a factor
of two in the slow cases.

| Setup | Users | Served per second (wanted) | Median | Slowest 5% | Server CPU (100 = one core) |
|---|---:|---:|---:|---:|---:|
| One process, SQLite (step 1) | 100 | 92 (100) | 10 ms | 33 ms | 53% |
| One process, PostgreSQL | 100 | 91 (100) | 122-137 ms | 531-909 ms | 73% |
| Router + 1 worker | 100 | 91 (100) | 172 ms | 643 ms | 91% |
| Router + 2 workers | 100 | 92 (100) | 18 ms | 50 ms | 88% |
| Router + 4 workers | 100 | 92 (100) | 17 ms | 39 ms | 88% |
| One process, PostgreSQL | 150 | 50 (150) | 1.4 s | 5.5 s | 48% |
| Router + 2 workers | 150 | 79 (150) | 0.6 s | 4.3 s | 84% |
| Router + 4 workers | 150 | 77 (150) | 0.8 s | 4.2 s | 83% |

At 200 users every setup collapsed to 48-61 requests a second.

What this says, and what it does not:

1. **PostgreSQL costs more per request than SQLite.** A request cost about 8 ms of server CPU on PostgreSQL against
   about 6 ms on SQLite, because each page snapshot reads the ledger through a network connection. A single ledger
   posting (one fill) took about 2 ms against well under 0.1 ms on SQLite. Fills are rare compared with clock ticks, so
   it shows up as the ~40% difference above, not as slow trading.
2. **The router costs about 2 ms of CPU per request** and is one Python process, so it is itself a ceiling. Router plus
   one worker is slower than a plain process: the router only pays off when it fronts several workers.
3. **Two workers beat one process at 100 users** (median 137 ms to 18 ms, slowest 5% 909 ms to 50 ms), because one
   process on PostgreSQL is already close to using its whole core at that load.
4. **Four workers did no better than two, because this machine has two cores.** That is a limit of where I tested, not
   of the design; I could not show more than two-fold scaling here.
5. **Above about 150 users I cannot say where the server's own limit is.** The fake users share the cores and parse
   every reply, so at 150-200 I was partly measuring the test client. The same caveat applies to the 200-user rows
   earlier in this document. A real answer needs the server on a machine with at least 4 spare cores and the fake users
   on another machine.
6. **My rough estimate, not a measurement:** at about 8-10 ms of CPU per request and one request per second per player,
   each worker core serves around 100-120 players, so N spare cores should serve roughly N x 100, until the single router
   process (about 2 ms per request, so around 500 requests a second) becomes the limit. Worth checking on real hardware
   before relying on it.

Correctness under several workers is tested separately and does not depend on the machine: two servers starting
together, two servers spending the same money at once (exactly one succeeds), and a deadlock between workers on the
shared system accounts, which the test provokes on demand and which the ledger's fixed account order prevents
(`tests/unit/test_ledger_postgres.py`, `tests/unit/test_cluster.py`).

Reproduce: `python tools/loadtest.py --url http://127.0.0.1:8000 --db postgresql://... --users 100 --server-pid <pid>`
against `marketlab serve` or `marketlab cluster` using the same database.
