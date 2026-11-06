# How the maths works

Every number on screen comes from a few formulas. This page lists them in the order a trade meets them: how a price moves,
how orders turn into trades, what the index is, what a trade costs, and how your profit and loss is counted. Each part
names the file that does it, so you can check the formula against the code.

All the examples below were produced by the code itself (`index.py`, `costs.py`), not worked out by hand.

## 1. How a company's price moves (`sim/processes.py`, `world.py`, `factors.py`)

Behind each company is a hidden "fair value" $V$ that traders gather around. It moves in small steps of $\Delta t$
seconds:

$$
V_{t+\Delta t} = V_t \cdot \exp\!\Big( \underbrace{\beta_i\, m + s_k + n}_{\text{shared moves}} \;+\; \underbrace{\big(\mu - \tfrac12\sigma^2\big)\Delta t + \sigma \sqrt{\Delta t}\, Z}_{\text{its own move}} \;+\; J \Big)
$$

- $Z$ is a standard normal random number: the ordinary, everyday wobble. This is geometric Brownian motion, the
  standard textbook model of a share price.
- $J$ is an occasional jump: with a small chance each step, a normal random amount is added, which is where sudden moves
  come from.
- $m$ is the **market move**, shared by all twelve companies, and $s_k$ is the **sector move**, shared by the three
  companies in sector $k$. Each is a seeded random walk with its own size per $\sqrt{\text{second}}$
  (market 0.0002, sector 0.00012; the company's own volatility is 0.00015).
- $\beta_i$ is how strongly company $i$ follows the market: 0.7 for primary-sector companies, 1.0 secondary, 1.1 tertiary
  and 1.3 quaternary. A higher beta means bigger swings with the market.
- $n$ is the effect of news (section 6).

So a company's return is part market, part sector, part its own noise. That is why a day where the market falls drags
most companies down together, and why companies in one sector tend to move alike.

The trades you see are not the fair value itself. Market makers, noise traders and value traders place orders around it
and the order book produces the actual prices. Every random number comes from a seed, so the same day number always
gives exactly the same day.

## 2. How orders become trades (`core/book.py`, `core/auction.py`)

**During the day** each company has an order book. A buy and a sell trade when the buyer's price is at least the
seller's. Orders at the same price are served first come, first served. The trade happens at the price of the order that
was already waiting. A market order takes whatever is best.

**At the open** (9:00 to 9:15) orders are collected without trading, then matched together at one price. For each
candidate price $p$:

$$
B(p) = \text{shares people will buy at } p \text{ or lower}, \qquad S(p) = \text{shares people will sell at } p \text{ or higher}
$$

The shares that can trade at $p$ are $\min(B(p), S(p))$. The opening price is chosen by these rules, in order:

1. the price where the most shares trade;
2. if tied, the smallest gap $|B(p) - S(p)|$;
3. if still tied, the price closest to yesterday's close;
4. if still tied, the lower price.

Everyone who trades gets that one price, which is why the auction is fair to early and late orders alike.

## 3. The index (`index.py`)

An index is a single number that stands for a basket of shares. The real Sensex and Nifty do not average prices. Each
company counts in proportion to its **free-float market capitalisation**: its price times the shares actually available
to the public. The level is

$$
\text{Index} = \frac{\sum_i p_i\, q_i}{D}, \qquad D = \frac{\sum_i p_i^{\text{base}}\, q_i}{\text{base value}}
$$

where $p_i$ is the price of company $i$, $q_i$ its weight, and $D$ the **divisor**. The divisor is chosen once so the
index starts at its base value (1,000 here, the Sensex started at 100).

The app shows three kinds. They differ only in what $q_i$ is:

| Kind | $q_i$ | Effect |
| --- | --- | --- |
| Cap-weighted (Nifty, Sensex) | free-float shares | big companies move the index most |
| Price-weighted (the Dow) | 1 | a share that costs more counts more, whatever the company's size |
| Equal-weighted | $1 / (n \cdot p_i^{\text{base}})$ | every company counts the same |

**A worked example.** Two companies, A (100 free shares, base price ₹100) and B (300 free shares, base price ₹200). A rises
10% to ₹110 and B stays at ₹200:

| Kind | Divisor (paise units) | Index after the move |
| --- | --- | --- |
| Cap-weighted | 7,000 | 1,014.29 |
| Price-weighted | 30 | 1,033.33 |
| Equal-weighted | 1/1,000 | 1,050.00 |

The kinds disagree because they ask different questions. Cap-weighted says A is a small part of the market, so the index
moves 1.4%. Equal-weighted says A is one of two equal companies, so the index moves 5%. Price-weighted sees A's price
rise by ₹10 out of ₹300 in total.

**The divisor does a second job.** If something changes that is not a price move (a share split, or a company leaving the
index), the divisor is reset so the level stays exactly where it was. Otherwise the index would jump for no reason. This
is what `after_split` and `rebalance` do.

**Each company's share of the move.** Company $i$ adds $q_i \Delta p_i / D$ to the index change, and these contributions
add up to the total change exactly. The page shows them in "The index" tab.

All of this uses exact fractions, never floating point. Only the final number shown is rounded, half away from zero.

## 4. What a trade costs (`costs.py`)

A delivery trade on the NSE pays, on its value $V$ (all rates are exact fractions):

| Charge | Rate | When |
| --- | --- | --- |
| Securities transaction tax (STT) | 0.1% of $V$ | buy and sell |
| Exchange transaction charge | ₹307 per crore of $V$ | buy and sell |
| SEBI fee | ₹10 per crore of $V$ | buy and sell |
| Stamp duty | 0.015% of $V$ | buy only |
| Brokerage | set by the plan | once per order that trades |
| Demat fee | set by the plan | once per sell order |
| GST | 18% of (brokerage + demat + exchange + SEBI) | buy and sell. It is not charged on STT or stamp duty |

Each amount is rounded to the nearest paisa. Real brokers round in slightly different places, so a real contract note can
differ by a paisa or two.

**A worked example,** buying and then selling ₹10,000 of shares:

| | Zero-brokerage plan | ₹20 flat plan |
| --- | --- | --- |
| Buy | ₹11.88 | ₹35.48 |
| Sell | ₹10.38 | ₹57.58 |

Under the zero plan, STT (₹10.00) is almost all of it. Under the ₹20 plan the brokerage and its GST dominate, which is why
small trades are expensive there. Round trip on ₹10,000: ₹22.26 against ₹93.06, so you need a gain of 0.22% or 0.93% just
to break even.

When one order fills in several pieces, the charges are worked out on everything traded so far and the part already
charged is subtracted, so the pieces always add up to what the whole order costs.

## 5. Your profit and loss (`world.py`, `build_positions`)

For each company the app uses the **average-cost method**. Each purchase adds to a pool of shares and to what the pool
cost. A sale takes shares out at the pool's average cost:

$$
\text{realised} = \text{sale proceeds} - \text{average cost} \times \text{shares sold}
$$

Shares you still hold are valued at today's price, and the difference from their cost is the unrealised result. Charges
are shown on their own and taken off the net. The per-company results add up to your account's total gain **exactly**,
with no rounding; a test checks this.

"Compared with the index" is simply your percentage change in worth minus the index's percentage change over the same
day.

## 6. The news (`news.py`)

A day has six headlines drawn from a box and two silent shocks. Each headline is *major* or *minor*, and rolls two dice:

- does it move the price at all: 75% for major, 15% for minor;
- which way: a major headline with an obvious direction goes that way 80% of the time, otherwise a coin toss. A minor one
  is always a coin toss.

When an item does move a price by $x$ (a size in basis points), the move arrives like this, $s$ seconds after the news:

$$
\text{share of the move done} = \begin{cases} 0.6 \cdot s / 5 & 0 \le s \le 5 \\ 0.6 + 0.4 \cdot (s - 5)/120 & 5 < s \le 125 \\ 1 & s > 125 \end{cases}
$$

That is 60% within five seconds and the rest over two minutes, which is why you cannot react to a headline in time to profit
from it. A market-wide item moves each company by its beta times the size; a sector or company item moves its targets by
the full size.

## 7. The comparison rules (`rules.py`)

After the close the app prices three portfolios from the day's prices, looked at once a simulated minute:

- **Stay in cash:** 0%.
- **Hold all twelve equally:** the average of each company's close divided by its open.
- **Follow the trend:** each minute, for each company, hold it for the next minute only if its price is above the average
  of its last three looks. Otherwise sit in cash. The twelve are averaged and compounded minute by minute.

These ignore charges and never trade in the market, so they are a yardstick, not a promise.

## 8. Why it can be trusted

- **Money is whole numbers.** Prices and balances are integers in paise, and shares are whole. Rates and the index use exact
  fractions. There is no floating-point drift in anything that is a balance.
- **Every transaction sums to zero.** The ledger is double-entry: whatever one account loses, another gains, and a database
  trigger refuses to edit or delete an entry.
- **The same seed gives the same day.** The event log of each company is fingerprinted with SHA-256, and a replay from the
  seed must reproduce it. The one place floating point is used, the price process, is only stable on the same machine and
  Python version.
