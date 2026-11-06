"""A whole market: twelve companies in four sectors, trading at once on one clock.

Each company is its own exchange with its own order book, its own traders and its own random stream. What ties
them together is time (everything moves on one clock) and the shared moves in `factors`: a market-wide move and a
move for each sector, so stocks rise and fall together the way real ones do. One seed determines the whole day.

The four sectors are the economist's classic split:

    Primary     takes things from the ground, the sea and the farm
    Secondary   turns raw materials into goods and power
    Tertiary    sells services: money, shops, delivery
    Quaternary  knowledge work: software, advice, research

The company names are jokes on purpose. All the prices, companies and people here are made up.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction

from marketlab.codec import hash_events
from marketlab.core import CancelOrder, Event, NewOrder, Order, OrderType, Side, TimeInForce, Trade
from marketlab.costs import PLANS, CostModel, schedule_on
from marketlab.factors import FactorPath, derive_seed
from marketlab.index import KINDS, Index, Kind, Member, hundredths
from marketlab.ledger import (
    STARTING_CASH,
    Gateway,
    Ledger,
    OrderRefused,
    Statement,
    build_statement,
    locked_account,
    reserved_account,
)
from marketlab.news import NewsItem, affects, news_change, schedule
from marketlab.rules import benchmarks as run_benchmarks
from marketlab.sim import SimConfig, Simulation, replay_with_commands

MICROS = 1_000_000
CHUNK = 200_000  # the day moves in steps of this many microseconds, so a fill in any company stops them all together

SECTORS: tuple[tuple[str, str], ...] = (
    ("primary", "Primary: farm, sea and mine"),
    ("secondary", "Secondary: factories and power"),
    ("tertiary", "Tertiary: services"),
    ("quaternary", "Quaternary: knowledge"),
)
# How strongly each sector follows the whole market (1 means exactly as much as the market).
SECTOR_BETA = {"primary": 0.7, "secondary": 1.0, "tertiary": 1.1, "quaternary": 1.3}
MARKET_SD = 0.00020  # shared market move, per square root of a second
SECTOR_SD = 0.00012  # extra move shared inside one sector
OWN_VOLATILITY = 0.00015  # what is left for the company alone
STALE_FRACTION = 0.004  # a trader pulls an order that sits more than 0.4% away from the price


@dataclass(frozen=True, slots=True)
class Company:
    symbol: str
    name: str
    sector: str
    price: int  # paise: yesterday's close
    free_float_shares: int

    @property
    def beta(self) -> float:
        return SECTOR_BETA[self.sector]


CATALOGUE: tuple[Company, ...] = (
    Company("BHINDI", "Bhindi Bazaar Agro", "primary", 18_240, 250_000_000),
    Company("KALASONA", "Kala Sona Coal & Minerals", "primary", 46_215, 600_000_000),
    Company("MACHLI", "Machli Pani Fisheries", "primary", 6_835, 150_000_000),
    Company("JUGAAD", "Jugaad Motors", "secondary", 128_460, 420_000_000),
    Company("PAKKA", "Pakka Pucca Cement", "secondary", 271_630, 180_000_000),
    Company("BIJLI", "Bijli Bachao Power", "secondary", 31_275, 900_000_000),
    Company("UDHAAR", "Udhaar Bank of India", "tertiary", 164_220, 700_000_000),
    Company("KIRANA", "Kirana King Retail", "tertiary", 390_550, 120_000_000),
    Company("DERAAYE", "Der Aaye Couriers", "tertiary", 9_480, 300_000_000),
    Company("BUGFIX", "Bugfix Technologies", "quaternary", 412_890, 260_000_000),
    Company("CHARCHA", "Chai Pe Charcha Consulting", "quaternary", 81_245, 90_000_000),
    Company("DAWAI", "Dr. Dawai Biotech Research", "quaternary", 197_505, 200_000_000),
)
BY_SYMBOL = {c.symbol: c for c in CATALOGUE}

INDEX_NAME = "Shifty 12"
INDEX_NAMES: dict[str, str] = {
    "cap": f"{INDEX_NAME} (by company size)",
    "equal": f"{INDEX_NAME} Equal (every company counts the same)",
    "price": f"{INDEX_NAME} Price (dearer shares count more)",
}


@dataclass(frozen=True)
class WorldConfig:
    seed: int = 1
    pre_open_seconds: int = 60
    open_seconds: int = 600
    market_makers: int = 2
    noise_traders: int = 8
    value_traders: int = 2


class World:
    """Twelve simulated companies on one clock."""

    def __init__(
        self,
        config: WorldConfig,
        companies: tuple[Company, ...] = CATALOGUE,
        previous_close: dict[str, int] | None = None,
    ) -> None:
        """`companies` carry the base prices the indices are measured from. When `previous_close` is given, the day
        opens at those prices instead (yesterday's closes), and the index carries on from where it ended."""
        self.config = config
        self.base_prices = {c.symbol: c.price for c in companies}
        if previous_close is not None:
            missing = {c.symbol for c in companies} - set(previous_close)
            if missing:
                raise ValueError(f"no previous close for {sorted(missing)}")
            companies = tuple(replace(c, price=previous_close[c.symbol]) for c in companies)
        self.companies = companies
        horizon = config.pre_open_seconds + config.open_seconds + 1
        self._market = FactorPath(derive_seed(config.seed, "market"), MARKET_SD, horizon)
        self._sectors = {
            key: FactorPath(derive_seed(config.seed, f"sector:{key}"), SECTOR_SD, horizon) for key, _ in SECTORS
        }
        self.news: list[NewsItem] = schedule(
            config.seed, [(c.symbol, c.name, c.sector) for c in companies], self.open_at, self.close_at
        )
        self.sims: dict[str, Simulation] = {
            c.symbol: Simulation(self.sim_config(c), self._common(c), STALE_FRACTION) for c in companies
        }
        self.now = 0

    # -- building ---------------------------------------------------------------------------------------------

    def sim_config(self, company: Company) -> SimConfig:
        return SimConfig(
            seed=derive_seed(self.config.seed, f"company:{company.symbol}"),
            symbol=company.symbol,
            reference_price=company.price,
            pre_open_seconds=self.config.pre_open_seconds,
            open_seconds=self.config.open_seconds,
            market_makers=self.config.market_makers,
            noise_traders=self.config.noise_traders,
            value_traders=self.config.value_traders,
            volatility=OWN_VOLATILITY,
        )

    def _common(self, company: Company) -> Callable[[int, int], float]:
        market, sector, beta = self._market, self._sectors[company.sector], company.beta
        # a market-wide item moves each company by its beta; a sector or company item moves it by the full amount
        mine = [
            (n, beta if n.scope == "market" else 1.0) for n in self.news if affects(n, company.symbol, company.sector)
        ]

        def shared(start: int, end: int) -> float:
            return beta * market.change(start, end) + sector.change(start, end) + news_change(mine, start, end)

        return shared

    # -- the day ----------------------------------------------------------------------------------------------

    @property
    def open_at(self) -> int:
        return self.config.pre_open_seconds * MICROS

    @property
    def close_at(self) -> int:
        return self.open_at + self.config.open_seconds * MICROS

    @property
    def finished(self) -> bool:
        return all(sim.finished for sim in self.sims.values())

    def advance_to(
        self, until: int, stop: Callable[[str, list[Event]], bool] | None = None
    ) -> tuple[dict[str, list[Event]], bool]:
        """Move every company forward to `until`. Returns each company's new events, and whether it stopped early.

        With `stop`, the day pauses at the end of the first small step in which `stop(symbol, events)` is true for
        some company. Every company is then at exactly the same moment.
        """
        until = min(until, self.close_at)
        if until < self.now:
            raise ValueError("cannot go back in time")
        new: dict[str, list[Event]] = {symbol: [] for symbol in self.sims}
        stopped = False
        while self.now < until and not self.finished:
            target = min(until, self.now + CHUNK)
            hit = False
            for symbol, sim in self.sims.items():
                events = sim.advance_to(target)
                new[symbol].extend(events)
                if stop is not None and stop(symbol, events):
                    hit = True
            self.now = target
            if hit and self.now < until:
                stopped = True
                break
        return new, stopped

    # -- looking ----------------------------------------------------------------------------------------------

    def prices(self) -> dict[str, int]:
        """The last traded price of each company (yesterday's close before its first trade)."""
        return {s: sim.state.last_price or sim.instrument.reference_price for s, sim in self.sims.items()}

    def reference_prices(self) -> dict[str, int]:
        return {c.symbol: c.price for c in self.companies}

    def members(self, sector: str | None = None) -> list[Member]:
        return [Member(c.symbol, c.free_float_shares) for c in self.companies if sector in (None, c.sector)]

    def index(self, kind: Kind, sector: str | None = None) -> Index:
        """An index that reads 1000 at the base prices, and so reads the previous close's level when the day opens."""
        return Index.create(kind, self.members(sector), self.base_prices)

    def fingerprints(self) -> dict[str, str]:
        return {s: hash_events(sim.events) for s, sim in self.sims.items()}

    def replay(self) -> dict[str, Simulation]:
        """Re-run every company's day from its seed and the commands sent to it. Must match exactly."""
        return {
            c.symbol: replay_with_commands(
                self.sim_config(c), self.sims[c.symbol].script, self._common(c), STALE_FRACTION
            )
            for c in self.companies
        }


# -- positions: how each company has done for one account ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    shares: int
    average_cost: int  # paise a share, rounded; 0 when no shares are held
    bought: int  # paise spent on this company's shares, ever
    sold: int  # paise received
    charges: int  # taxes and charges paid on this company's trades
    realised: int  # profit or loss locked in by selling, before charges
    unrealised: int  # profit or loss on shares still held, at the given price, before charges
    net: int  # realised + unrealised - charges
    net_exact: Fraction  # the same, without rounding, so totals can be checked exactly


def build_positions(statement: Statement, prices: dict[str, int]) -> dict[str, Position]:
    """Profit and loss per company using the average-cost method.

    Each purchase adds to a pool of shares and to what they cost. A sale takes shares out of the pool at the
    pool's average cost; the difference from what they sold for is the profit or loss that sale locked in.
    Shares still in the pool are valued at today's price. Charges are shown on their own and taken off the net.
    """
    shares: dict[str, int] = {}
    cost: dict[str, Fraction] = {}
    bought: dict[str, int] = {}
    sold: dict[str, int] = {}
    charges: dict[str, int] = {}
    realised: dict[str, Fraction] = {}
    for row in statement.rows:
        if row.symbol is None:
            continue
        s = row.symbol
        shares.setdefault(s, 0)
        cost.setdefault(s, Fraction(0))
        bought.setdefault(s, 0)
        sold.setdefault(s, 0)
        charges.setdefault(s, 0)
        realised.setdefault(s, Fraction(0))
        charges[s] += row.total_charges
        if row.kind == "grant":
            shares[s] += row.shares_change
        elif row.kind == "buy":
            shares[s] += row.shares_change
            cost[s] += row.value
            bought[s] += row.value
        elif row.kind == "sell":
            out = -row.shares_change
            average = cost[s] / shares[s] if shares[s] else Fraction(0)
            realised[s] += row.value - average * out
            cost[s] -= average * out
            shares[s] -= out
            sold[s] += row.value
    result: dict[str, Position] = {}
    for s in shares:
        if s not in prices:  # a company that is no longer listed: nothing to value it with
            continue
        held = shares[s]
        average = cost[s] / held if held else Fraction(0)
        unrealised = held * prices[s] - cost[s] if held else Fraction(0)
        net = realised[s] + unrealised - charges[s]
        result[s] = Position(
            s,
            held,
            round(average),
            bought[s],
            sold[s],
            charges[s],
            round(realised[s]),
            round(unrealised),
            round(net),
            net,
        )
    return result


# -- a practice account in the world -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenOrder:
    symbol: str
    order_id: int
    side: Side
    quantity: int
    remaining: int
    limit_price: int | None


@dataclass(frozen=True, slots=True)
class Holding:
    shares: int  # free to sell
    locked: int  # set aside for open sell orders


@dataclass(frozen=True, slots=True)
class WorldPortfolio:
    cash: int
    reserved: int
    holdings: dict[str, Holding]
    open_orders: tuple[OpenOrder, ...]


@dataclass(frozen=True, slots=True)
class WorldAdvance:
    events: dict[str, list[Event]]
    now: int
    stopped_for_fill: bool
    finished: bool


class PracticeWorld:
    """One practice account trading in all twelve companies. As in `PracticeSession`, the server keeps no clock."""

    def __init__(
        self,
        config: WorldConfig,
        ledger: Ledger,
        owner: str,
        *,
        plan: str = "zero",
        trading_date: date | None = None,
        starting_cash: int = STARTING_CASH,
        previous_close: dict[str, int] | None = None,
    ) -> None:
        self.config = config
        self.owner = owner
        self.ledger = ledger
        self.world = World(config, previous_close=previous_close)
        ledger.open_account(owner, starting_cash=starting_cash)
        self.costs = CostModel(schedule_on(trading_date or date.today()), PLANS[plan])
        self.gateways = {s: Gateway(ledger, owner, sim.instrument, self.costs) for s, sim in self.world.sims.items()}
        for gateway in self.gateways.values():
            gateway.recover()
        self._sent: dict[tuple[str, int], Order] = {}
        for symbol, gateway in self.gateways.items():
            gateway.settle(self.world.sims[symbol].events)
        self._baseline = {s: p.net_exact for s, p in self.positions(self.world.reference_prices()).items()}
        self.start_worth = self.worth()
        self.start_charges = self.statement().total_charges

    @property
    def now(self) -> int:
        return self.world.now

    @property
    def finished(self) -> bool:
        return self.world.finished

    def _mine(self, _symbol: str, events: list[Event]) -> bool:
        return any(isinstance(e, Trade) and self.owner in (e.buy_account_id, e.sell_account_id) for e in events)

    def advance(self, seconds: float, *, pause_on_fill: bool = True) -> WorldAdvance:
        if seconds < 0:
            raise ValueError("cannot move the day backwards")
        target = self.world.now + round(seconds * MICROS)
        events, stopped = self.world.advance_to(target, self._mine if pause_on_fill else None)
        for symbol, new in events.items():
            self.gateways[symbol].settle(new)
        return WorldAdvance(events, self.world.now, stopped, self.world.finished)

    def place(
        self,
        symbol: str,
        side: Side,
        quantity: int,
        limit_price: int | None = None,
        tif: TimeInForce = TimeInForce.DAY,
    ) -> tuple[int, list[Event]]:
        """Check, set aside, send. Raises OrderRefused (changing nothing) when the order cannot be placed."""
        sim = self.world.sims.get(symbol)
        if sim is None:
            raise OrderRefused(f"there is no company with the symbol {symbol}")
        if sim.finished:
            raise OrderRefused("the market is closed for the day")
        if quantity <= 0:
            raise OrderRefused("the quantity must be at least 1 share")
        order = Order(
            order_id=sim.new_user_order_id(),
            account_id=self.owner,
            symbol=symbol,
            side=side,
            type=OrderType.LIMIT if limit_price is not None else OrderType.MARKET,
            quantity=quantity,
            limit_price=limit_price,
            tif=tif,
            entered_at=sim.now,
        )
        gateway = self.gateways[symbol]
        gateway.reserve(order)
        self._sent[(symbol, order.order_id)] = order
        events = sim.inject(NewOrder(order))
        gateway.settle(events)
        return order.order_id, events

    def cancel(self, symbol: str, order_id: int) -> list[Event]:
        sim = self.world.sims.get(symbol)
        if sim is None:
            raise OrderRefused(f"there is no company with the symbol {symbol}")
        if sim.finished:
            raise OrderRefused("the market is closed for the day")
        gateway = self.gateways[symbol]
        if order_id not in gateway.open_order_ids():
            raise OrderRefused(f"order {order_id} is not open")
        events = sim.inject(CancelOrder(order_id))
        gateway.settle(events)
        return events

    def end_early(self) -> None:
        for gateway in self.gateways.values():
            gateway.abandon()

    # -- looking ----------------------------------------------------------------------------------------------

    def portfolio(self) -> WorldPortfolio:
        holdings: dict[str, Holding] = {}
        orders: list[OpenOrder] = []
        for symbol, sim in self.world.sims.items():
            holdings[symbol] = Holding(
                self.ledger.shares(self.owner, symbol), self.ledger.balance(locked_account(self.owner, symbol))
            )
            resting = {o.order_id: o for o in sim.exchange.book.all_orders() if o.account_id == self.owner}
            for order_id in self.gateways[symbol].open_order_ids():
                sent = self._sent[(symbol, order_id)]
                left = (
                    resting[order_id].remaining
                    if order_id in resting
                    else sim.state.pending_market.get(order_id, sent.quantity)
                )
                orders.append(OpenOrder(symbol, order_id, sent.side, sent.quantity, left, sent.limit_price))
        return WorldPortfolio(
            cash=self.ledger.cash(self.owner),
            reserved=self.ledger.balance(reserved_account(self.owner)),
            holdings=holdings,
            open_orders=tuple(orders),
        )

    def statement(self) -> Statement:
        return build_statement(self.ledger, self.owner)

    def positions(
        self, prices: dict[str, int] | None = None, statement: Statement | None = None
    ) -> dict[str, Position]:
        return build_positions(statement or self.statement(), prices or self.world.prices())

    def today(self, positions: dict[str, Position]) -> dict[str, int]:
        """Each company's net result since this day began."""
        return {s: round(p.net_exact - self._baseline.get(s, Fraction(0))) for s, p in positions.items()}

    def price_paths(self) -> dict[str, list[int]]:
        """Each company's price at the open and at every simulated minute after it, from the trades."""
        marks = [self.world.open_at + k * 60 * MICROS for k in range(0, self.config.open_seconds // 60 + 1)]
        out: dict[str, list[int]] = {}
        for symbol, sim in self.world.sims.items():
            price = sim.instrument.reference_price
            path: list[int] = []
            trades = [e for e in sim.events if isinstance(e, Trade)]
            i = 0
            for mark in marks:
                while i < len(trades) and trades[i].sim_time <= mark:
                    price = trades[i].price
                    i += 1
                path.append(price)
            out[symbol] = path
        return out

    def benchmarks_view(self) -> list[dict[str, object]]:
        """The comparison rules, once the day is over (before that they would only be a peek at the answer)."""
        if not self.world.finished:
            return []
        return [
            {"key": b.key, "label": b.label, "bp": b.basis_points, "note": b.note}
            for b in run_benchmarks(self.price_paths())
        ]

    def news_view(self) -> list[dict[str, object]]:
        """The news that is out so far. Nothing is shown before its time, silent shocks (moves with no headline) stay
        hidden until the day has finished, and so does what each item did to the price: knowing it in advance would
        turn the news into a cheat sheet."""
        out: list[dict[str, object]] = []
        done = self.world.finished
        for n in self.world.news:
            if n.at > self.world.now:
                break
            if n.kind == "silent" and not done:
                continue
            out.append(
                {
                    "id": n.id,
                    "at": n.at,
                    "scope": n.scope,
                    "target": n.target,
                    "headline": n.headline,
                    "silent": n.kind == "silent",
                    "impact_bp": n.impact_bp if done else None,
                }
            )
        return out

    def fills(self) -> list[dict[str, object]]:
        """Every trade this person made today, in order: which company, bought or sold, how many, at what price."""
        out: list[dict[str, object]] = []
        for symbol, sim in self.world.sims.items():
            for e in sim.events:
                if isinstance(e, Trade) and self.owner in (e.buy_account_id, e.sell_account_id):
                    side = "BUY" if e.buy_account_id == self.owner else "SELL"
                    out.append(
                        {"symbol": symbol, "side": side, "quantity": e.quantity, "price": e.price, "at": e.sim_time}
                    )
        out.sort(key=lambda f: int(str(f["at"])))
        return out

    def day_summary(self) -> dict[str, object]:
        """What the history keeps about a day: the result, how each company did for this person, and every fill."""
        statement = self.statement()
        prices = self.world.prices()
        positions = self.positions(prices, statement)
        today = self.today(positions)
        worth = statement.money + sum(q * prices[s] for s, q in statement.holdings if s in prices)
        indices = self.indices(prices)
        return {
            "start_worth": self.start_worth,
            "end_worth": worth,
            "result": worth - self.start_worth,
            "charges": statement.total_charges - self.start_charges,
            "companies": [
                {"symbol": c.symbol, "name": c.name, "today": today.get(c.symbol, 0)}
                for c in CATALOGUE
                if today.get(c.symbol, 0) != 0
            ],
            "index": {
                kind: {"open": v["open"], "level": v["level"], "change": v["change"]}
                for kind, v in indices.items()
                if kind in KINDS
            },
            "fills": self.fills(),
            "news": self.news_view(),
            "benchmarks": self.benchmarks_view(),
        }

    def worth(self) -> int:
        statement, prices = self.statement(), self.world.prices()
        return statement.money + sum(qty * prices[s] for s, qty in statement.holdings if s in prices)

    def indices(self, prices: dict[str, int] | None = None) -> dict[str, dict[str, object]]:
        """Every index level and what moved it, as whole numbers (hundredths of a point; paise)."""
        prices, base = prices or self.world.prices(), self.world.reference_prices()
        out: dict[str, dict[str, object]] = {}
        for kind in KINDS:
            index = self.world.index(kind)
            level = index.level(prices)
            weights = index.weights(prices)
            moved = index.contributions(prices, base)
            out[kind] = {
                "name": INDEX_NAMES[kind],
                "level": hundredths(level),
                "open": hundredths(index.level(base)),
                "change": hundredths(level - index.level(base)),
                "members": {
                    s: {"weight_bp": round(weights[s] * 10_000), "points": hundredths(moved[s])} for s in weights
                },
            }
        sectors: dict[str, object] = {}
        for key, label in SECTORS:
            sector_index = self.world.index("cap", key)
            sectors[key] = {
                "label": label,
                "level": hundredths(sector_index.level(prices)),
                "open": hundredths(sector_index.level(base)),
                "change": hundredths(sector_index.level(prices) - sector_index.level(base)),
            }
        out["sectors"] = sectors
        return out

    def fingerprints(self) -> dict[str, str]:
        return self.world.fingerprints()
