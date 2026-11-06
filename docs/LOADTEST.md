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
   move 100 clocks. Sending one request per second, with the server returning a batch, would cut the load
   about four times for the same experience.
4. **Memory grows with how much of the day has been played**, because each day keeps its full event list.
   Speed 10 used about 4 MB per user after 25 s (40% of a day), so a full day is roughly 10 MB.
   500 people mid-day is on the order of 5 GB; a free 512 MB host holds about 40 players.
   (Estimate from two short runs, not a measurement of full days.)
5. **A restart loses every day in progress.** Only finished or abandoned days reach the database.

## What changes because of this

- Raise or remove the live-day cap and expire idle days after a timeout instead.
- Poll once a second, not four times (biggest single win).
- Run several server processes, with each user always sent to the same one (their day lives in memory).
- Move the database from SQLite to Postgres, since many processes cannot share one SQLite writer comfortably.
- Free 512 MB hosting is a demo, not a crowd: plan for tens of players there, hundreds only on a bigger box.

Caveat: fake users are polite and identical. Real people open extra tabs, pause, and leave days
half-finished, which the idle timeout has to handle.
