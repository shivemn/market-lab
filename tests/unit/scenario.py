"""A fixed, hand-written trading day used by the projection and golden-log tests. Integers only, no randomness.

Prices are in paise: 250_000 is 2,500.00 rupees. The pre-open session produces an auction at 2,500.00 that
trades 130 shares and leaves 70 of order 4 resting. The rest of the day is described next to each step.
"""

from __future__ import annotations

from marketlab.core import CancelOrder, Event, Exchange, ModifyOrder, NewOrder, Session, Side, TimeInForce
from tests.helpers import DEMO, limit, market


def scripted_day() -> tuple[list[Event], dict[str, int]]:
    """Returns every event of the day, and the event count after each named step."""
    ex = Exchange(DEMO)
    events: list[Event] = []
    marks: dict[str, int] = {}

    def step(label: str, new: list[Event]) -> None:
        events.extend(new)
        marks[label] = len(events)

    step("pre_open", ex.set_session(Session.PRE_OPEN, 0))
    step("o1", ex.submit(NewOrder(limit(1, Side.BUY, 250_100, 100, account="A")), 10))
    step("o2", ex.submit(NewOrder(limit(2, Side.BUY, 250_050, 50, account="B")), 20))
    step("o3", ex.submit(NewOrder(limit(3, Side.SELL, 249_950, 80, account="C")), 30))
    step("o4", ex.submit(NewOrder(limit(4, Side.SELL, 250_000, 120, account="D")), 40))
    step("o5", ex.submit(NewOrder(market(5, Side.BUY, 30, account="E")), 50))
    step("cancel2", ex.submit(CancelOrder(2), 60))
    step("open", ex.set_session(Session.OPEN, 1_000))  # the auction runs here
    step("o6", ex.submit(NewOrder(limit(6, Side.BUY, 249_900, 40, account="F")), 1_100))
    step("o7", ex.submit(NewOrder(limit(7, Side.BUY, 249_900, 60, account="G")), 1_200))
    step("o8", ex.submit(NewOrder(limit(8, Side.BUY, 249_950, 20, account="H")), 1_300))
    step("shrink7", ex.submit(ModifyOrder(7, new_quantity=30), 1_400))  # smaller: keeps its place
    step("move6", ex.submit(ModifyOrder(6, new_price=249_950), 1_500))  # new price: back of the queue
    step("ioc9", ex.submit(NewOrder(limit(9, Side.SELL, 249_950, 20, account="I", tif=TimeInForce.IOC)), 1_600))
    step("bad10", ex.submit(NewOrder(limit(10, Side.BUY, 250_003, 5, account="J")), 1_700))  # off the tick grid
    step("mkt11", ex.submit(NewOrder(market(11, Side.SELL, 25, account="K")), 1_800))
    step("cancel99", ex.submit(CancelOrder(99), 1_900))  # unknown order
    step("mkt12", ex.submit(NewOrder(market(12, Side.BUY, 30, account="L")), 2_000))
    step("close", ex.set_session(Session.CLOSED, 3_000))
    return events, marks
