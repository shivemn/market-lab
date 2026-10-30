"""Commands: what a trader (or a simulated agent) can ask the exchange to do."""

from __future__ import annotations

from dataclasses import dataclass

from marketlab.core.types import Order


@dataclass(frozen=True, slots=True)
class NewOrder:
    order: Order


@dataclass(frozen=True, slots=True)
class CancelOrder:
    order_id: int


@dataclass(frozen=True, slots=True)
class ModifyOrder:
    """Change a resting order. `new_quantity` is the new total quantity, including anything already filled.

    Give a new price, a new quantity, or both. Lowering only the quantity keeps the order's place in the
    queue. A new price, or a higher quantity, sends it to the back of the queue.
    """

    order_id: int
    new_quantity: int | None = None
    new_price: int | None = None


Command = NewOrder | CancelOrder | ModifyOrder
