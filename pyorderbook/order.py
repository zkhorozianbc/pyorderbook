import operator
from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum, auto
from functools import partial
from typing import TypeAlias
from uuid import UUID, uuid4

Symbol: TypeAlias = str
Price: TypeAlias = Decimal


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
        if quantity <= 0:
            raise ValueError("Order quantity must be greater than zero")
        self.id: UUID = uuid4()
        self.price: Price = Decimal(str(price))
        self.quantity: int = quantity
        self.symbol: Symbol = symbol
        self.side: Side = side
        self.original_quantity: int = quantity

    @property
    def status(self) -> OrderStatus:
        if self.quantity == 0:
            return OrderStatus.FILLED
        elif self.quantity < self.original_quantity:
            return OrderStatus.PARTIAL_FILL
        return OrderStatus.QUEUED

    def get_id(self) -> UUID:
        return self.id

    def get_price(self) -> Price:
        return self.price

    def get_quantity(self) -> int:
        return self.quantity

    def get_symbol(self) -> Symbol:
        return self.symbol

    def get_side(self) -> Side:
        return self.side

    def get_original_quantity(self) -> int:
        return self.original_quantity

    def get_status(self) -> OrderStatus:
        return self.status


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
