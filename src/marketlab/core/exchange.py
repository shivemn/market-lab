"""The exchange for one instrument: validation, the pre-open auction, continuous matching, cancel, modify and
the session clock.

The caller supplies the logical time with every command. The exchange never reads a real clock, which is what
will make exact replay possible. Every call returns the list of events it caused, numbered without gaps.

Sessions: CLOSED -> PRE_OPEN -> OPEN -> CLOSED. Opening straight from CLOSED to OPEN is also allowed and simply
skips the auction.

- PRE_OPEN: orders are collected and nothing trades. Limit orders sit on the book (which may overlap, because
  nothing has matched yet) and market orders wait in a separate list. Cancel and modify are allowed.
- Moving from PRE_OPEN to OPEN runs the opening auction: one price, chosen by `compute_auction`, at which every
  executable order trades. Events come in this order: AuctionResult, the Trades, cancellations of whatever market
  and IOC orders were left unfilled, then SessionChanged(OPEN). Unfilled DAY limit orders stay on the book.
- OPEN: continuous matching by price-time priority.
"""

from __future__ import annotations

from marketlab.core.auction import compute_auction
from marketlab.core.book import OrderBook
from marketlab.core.commands import CancelOrder, Command, ModifyOrder, NewOrder
from marketlab.core.events import (
    AuctionResult,
    CancelReason,
    Event,
    OrderAccepted,
    OrderCancelled,
    OrderExpired,
    OrderModified,
    OrderRejected,
    SessionChanged,
    Trade,
)
from marketlab.core.types import (
    Instrument,
    Order,
    OrderType,
    RejectReason,
    Session,
    Side,
    TimeInForce,
)
from marketlab.core.validation import validate_order


class Exchange:
    def __init__(self, instrument: Instrument, session: Session = Session.CLOSED) -> None:
        self.instrument = instrument
        self.session = session
        self.book = OrderBook(instrument.symbol)
        self._seq = 0
        self._trade_id = 0
        self._clock = 0
        self._seen_ids: set[int] = set()
        # Market orders collected during PRE_OPEN, in arrival order. They cannot rest on the book.
        self._auction_market: list[Order] = []

    # ---- public API ----

    def submit(self, command: Command, sim_time: int) -> list[Event]:
        self._advance_clock(sim_time)
        events: list[Event] = []
        match command:
            case NewOrder(order=order):
                self._new_order(order, sim_time, events)
            case CancelOrder(order_id=order_id):
                self._cancel(order_id, sim_time, events)
            case ModifyOrder():
                self._modify(command, sim_time, events)
        return events

    def set_session(self, session: Session, sim_time: int) -> list[Event]:
        """Move the market to the next session.

        Allowed: CLOSED to PRE_OPEN, PRE_OPEN to OPEN (runs the auction), CLOSED to OPEN (no auction),
        and OPEN or PRE_OPEN to CLOSED (every resting order expires).
        """
        if session is self.session:
            raise ValueError(f"session is already {session.value}")
        if session is Session.PRE_OPEN and self.session is not Session.CLOSED:
            raise ValueError("pre-open can only start from a closed market")
        self._advance_clock(sim_time)
        events: list[Event] = []

        if self.session is Session.PRE_OPEN and session is Session.OPEN:
            self._run_auction(sim_time, events)
            self.session = Session.OPEN
            events.append(SessionChanged(self._next_seq(), sim_time, session))
            return events

        self.session = session
        events.append(SessionChanged(self._next_seq(), sim_time, session))
        if session is Session.CLOSED:
            for market_order in self._auction_market:
                events.append(OrderExpired(self._next_seq(), sim_time, market_order.order_id, market_order.remaining))
            self._auction_market = []
            for order in self.book.all_orders():
                self.book.cancel(order.order_id)
                events.append(OrderExpired(self._next_seq(), sim_time, order.order_id, order.remaining))
        return events

    # ---- new orders ----

    def _new_order(self, order: Order, t: int, events: list[Event]) -> None:
        order.entered_at = t
        reason = validate_order(order, self.instrument, self.session)
        if reason is None and order.order_id in self._seen_ids:
            reason = RejectReason.DUPLICATE_ORDER_ID
        if (
            reason is None
            and order.type is OrderType.MARKET
            and self.session is Session.OPEN
            and self.book.peek_best(_opposite(order.side)) is None
        ):
            reason = RejectReason.NO_LIQUIDITY
        if reason is not None:
            events.append(OrderRejected(self._next_seq(), t, order.order_id, reason))
            return

        self._seen_ids.add(order.order_id)
        events.append(
            OrderAccepted(
                self._next_seq(),
                t,
                order.order_id,
                order.account_id,
                order.symbol,
                order.side,
                order.type,
                order.quantity,
                order.limit_price,
                order.tif,
            )
        )
        self._match_and_place(order, t, events)

    def _match_and_place(self, order: Order, t: int, events: list[Event]) -> None:
        """Trade the order against the book, then rest or cancel whatever is left.

        During PRE_OPEN nothing trades: the order is only collected for the opening auction.
        """
        if self.session is Session.PRE_OPEN:
            if order.type is OrderType.LIMIT:
                self.book.rest(order)
            else:
                self._auction_market.append(order)
            return

        opposite = _opposite(order.side)
        while order.remaining > 0:
            resting = self.book.peek_best(opposite)
            if resting is None or not _crosses(order, resting):
                break
            assert resting.limit_price is not None
            quantity = min(order.remaining, resting.remaining)
            self.book.fill(resting.order_id, quantity)
            order.remaining -= quantity
            self._trade_id += 1
            buyer, seller = (order, resting) if order.side is Side.BUY else (resting, order)
            events.append(
                Trade(
                    self._next_seq(),
                    t,
                    self._trade_id,
                    self.instrument.symbol,
                    resting.limit_price,  # the trade happens at the resting order's price
                    quantity,
                    buyer.order_id,
                    seller.order_id,
                    buyer.account_id,
                    seller.account_id,
                    order.side,
                )
            )

        if order.remaining == 0:
            return
        if order.type is OrderType.LIMIT and order.tif is TimeInForce.DAY:
            self.book.rest(order)
        else:
            cancel_reason = (
                CancelReason.MARKET_REMAINDER if order.type is OrderType.MARKET else CancelReason.IOC_REMAINDER
            )
            events.append(OrderCancelled(self._next_seq(), t, order.order_id, order.remaining, cancel_reason))

    # ---- the opening auction ----

    def _run_auction(self, t: int, events: list[Event]) -> None:
        instrument = self.instrument
        # Limit orders in priority order: best price first, then earliest. The book already keeps that order.
        limit_buys = self._limit_orders(Side.BUY)
        limit_sells = self._limit_orders(Side.SELL)
        market_buys = [o for o in self._auction_market if o.side is Side.BUY]
        market_sells = [o for o in self._auction_market if o.side is Side.SELL]

        outcome = compute_auction(
            buy_limits=[(_price(o), o.remaining) for o in limit_buys],
            sell_limits=[(_price(o), o.remaining) for o in limit_sells],
            market_buy=sum(o.remaining for o in market_buys),
            market_sell=sum(o.remaining for o in market_sells),
            reference_price=instrument.reference_price,
            tick_size=instrument.tick_size,
            band_low=instrument.band_low,
            band_high=instrument.band_high,
        )
        opening_price = outcome.price if outcome.price is not None else instrument.reference_price
        events.append(
            AuctionResult(
                self._next_seq(),
                t,
                outcome.price,
                outcome.volume,
                opening_price,
                outcome.buy_eligible - outcome.volume,
                outcome.sell_eligible - outcome.volume,
            )
        )

        if outcome.price is not None:
            price = outcome.price
            # Who may trade at this price. Market orders come first (they accept any price), then limit orders
            # from the best price down, and within one price the earliest first.
            buyers = market_buys + [o for o in limit_buys if _price(o) >= price]
            sellers = market_sells + [o for o in limit_sells if _price(o) <= price]
            b = s = 0
            while b < len(buyers) and s < len(sellers):
                buyer, seller = buyers[b], sellers[s]
                quantity = min(buyer.remaining, seller.remaining)
                self._take(buyer, quantity)
                self._take(seller, quantity)
                self._trade_id += 1
                events.append(
                    Trade(
                        self._next_seq(),
                        t,
                        self._trade_id,
                        instrument.symbol,
                        price,
                        quantity,
                        buyer.order_id,
                        seller.order_id,
                        buyer.account_id,
                        seller.account_id,
                        None,  # nobody is the aggressor in an auction
                    )
                )
                if buyer.remaining == 0:
                    b += 1
                if seller.remaining == 0:
                    s += 1

        # Leftovers: market orders and IOC orders do not survive the auction. DAY limit orders stay.
        for market_order in self._auction_market:
            if market_order.remaining > 0:
                events.append(
                    OrderCancelled(
                        self._next_seq(),
                        t,
                        market_order.order_id,
                        market_order.remaining,
                        CancelReason.MARKET_REMAINDER,
                    )
                )
        self._auction_market = []
        for order in self.book.all_orders():
            if order.tif is TimeInForce.IOC:
                self.book.cancel(order.order_id)
                events.append(
                    OrderCancelled(self._next_seq(), t, order.order_id, order.remaining, CancelReason.IOC_REMAINDER)
                )
        assert not self.book.is_crossed(), "the auction left a crossed book"

    def _limit_orders(self, side: Side) -> list[Order]:
        orders: list[Order] = []
        for view in self.book.depth(side):
            orders.extend(self.book.orders_at(side, view.price))
        return orders

    def _take(self, order: Order, quantity: int) -> None:
        """Remove `quantity` from an order that traded in the auction."""
        if order.type is OrderType.LIMIT:
            self.book.fill(order.order_id, quantity)
        else:
            order.remaining -= quantity

    # ---- cancel ----

    def _cancel(self, order_id: int, t: int, events: list[Event]) -> None:
        if self.session is Session.CLOSED:
            events.append(OrderRejected(self._next_seq(), t, order_id, RejectReason.MARKET_CLOSED))
            return
        order = self.book.cancel(order_id)
        if order is None:
            order = self._take_market_order(order_id)
        if order is None:
            events.append(OrderRejected(self._next_seq(), t, order_id, RejectReason.UNKNOWN_ORDER))
            return
        events.append(OrderCancelled(self._next_seq(), t, order_id, order.remaining, CancelReason.USER))

    def _take_market_order(self, order_id: int) -> Order | None:
        for order in self._auction_market:
            if order.order_id == order_id:
                self._auction_market.remove(order)
                return order
        return None

    # ---- modify ----

    def _modify(self, command: ModifyOrder, t: int, events: list[Event]) -> None:
        reason = self._modify_problem(command)
        if reason is not None:
            events.append(OrderRejected(self._next_seq(), t, command.order_id, reason))
            return

        order = self.book.get(command.order_id)
        assert order is not None and order.limit_price is not None
        filled = order.quantity - order.remaining
        new_price = command.new_price if command.new_price is not None else order.limit_price
        new_quantity = command.new_quantity if command.new_quantity is not None else order.quantity
        lost_priority = new_price != order.limit_price or new_quantity > order.quantity

        if not lost_priority:
            # Only the quantity went down: the order keeps its place in the queue.
            self.book.reduce(order.order_id, new_quantity - filled)
            order.quantity = new_quantity
            events.append(
                OrderModified(self._next_seq(), t, order.order_id, new_quantity, new_price, order.remaining, False)
            )
            return

        # A new price or a larger quantity: take the order off the book and treat it like a new arrival.
        self.book.cancel(order.order_id)
        order.quantity = new_quantity
        order.remaining = new_quantity - filled
        order.limit_price = new_price
        order.entered_at = t
        events.append(
            OrderModified(self._next_seq(), t, order.order_id, new_quantity, new_price, order.remaining, True)
        )
        self._match_and_place(order, t, events)

    def _modify_problem(self, command: ModifyOrder) -> RejectReason | None:
        if self.session is Session.CLOSED:
            return RejectReason.MARKET_CLOSED
        order = self.book.get(command.order_id)
        if order is None:
            if any(o.order_id == command.order_id for o in self._auction_market):
                return RejectReason.BAD_ORDER  # a market order has no price or size to change: cancel it
            return RejectReason.UNKNOWN_ORDER
        if command.new_quantity is None and command.new_price is None:
            return RejectReason.BAD_ORDER
        assert order.limit_price is not None
        new_price = command.new_price if command.new_price is not None else order.limit_price
        new_quantity = command.new_quantity if command.new_quantity is not None else order.quantity
        filled = order.quantity - order.remaining
        if new_quantity <= filled:
            return RejectReason.BAD_QUANTITY  # to remove an order, cancel it instead
        if new_quantity % self.instrument.lot_size != 0:
            return RejectReason.BAD_LOT
        if new_price % self.instrument.tick_size != 0:
            return RejectReason.BAD_TICK
        if new_price < self.instrument.band_low or new_price > self.instrument.band_high:
            return RejectReason.OUTSIDE_BAND
        if new_price == order.limit_price and new_quantity == order.quantity:
            return RejectReason.BAD_ORDER  # nothing would change
        return None

    # ---- internals ----

    def _advance_clock(self, sim_time: int) -> None:
        if sim_time < self._clock:
            raise ValueError(f"time cannot go backwards: {sim_time} is before {self._clock}")
        self._clock = sim_time

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq


def _opposite(side: Side) -> Side:
    return Side.SELL if side is Side.BUY else Side.BUY


def _price(order: Order) -> int:
    assert order.limit_price is not None
    return order.limit_price


def _crosses(order: Order, resting: Order) -> bool:
    """Would the incoming order trade with this resting order?"""
    if order.type is OrderType.MARKET:
        return True
    assert order.limit_price is not None and resting.limit_price is not None
    if order.side is Side.BUY:
        return resting.limit_price <= order.limit_price
    return resting.limit_price >= order.limit_price
