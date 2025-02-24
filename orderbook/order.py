import operator
from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum, auto
from uuid import UUID, uuid4
from functools import partial
type Symbol = str
type Price = Decimal


class Side(StrEnum):
    """Enum to represent BID or ASK Order"""

    BID = auto()
    ASK = auto()

    @property
    def other(self) -> "Side":
        """Return the opposite side of the order"""
        return Side.BID if self == Side.ASK else Side.ASK

    @property
    def price_comparator(self) -> Callable[[Price, Price], bool]:
        """Return the price comparator function for the side.
        Best price for BID is the lowest price, and vice versa for ASK.
        """
        return operator.le if self == Side.ASK else operator.ge

    @property
    def calc_fill_price(self) -> Callable[[Price, Price], Price]:
        """Return the fill price calculation function for the side.
        For BID, the fill price is the max of the two prices.
        For ASK, the fill price is the min of the two prices.
        """
        return max if self == Side.ASK else min


class OrderStatus(StrEnum):
    """Enum for Order Status after matching occurs"""

    QUEUED = auto()
    PARTIAL_FILL = auto()
    FILLED = auto()


class Order:
    def __init__(self, side: Side, symbol: Symbol, price: float, quantity: int) -> None:
        self.id = uuid4()
        self.price: Price = Decimal(str(price))
        self.quantity = quantity
        self.symbol = symbol
        self.side = side
        self.original_quantity = quantity

bid = partial(Order, Side.BID)
ask = partial(Order, Side.ASK)


class OrderQueue(dict[UUID, Order]):
    def append_order(self, order: Order) -> None:
        self[order.id] = order

    def peek(self) -> Order:
        if not self:
            raise ValueError("Order Queue is Empty!")
        first_key = next(iter(self))
        return self[first_key]

    def popleft(self) -> None:
        self.pop(self.peek().id)
