from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum, auto
from uuid import UUID, uuid4

type Symbol = str
type Price = Decimal


class Side(StrEnum):
    """Enum to represent BUY or SELL Order"""

    BUY = auto()
    SELL = auto()

    @property
    def other(self) -> "Side":
        return Side.BUY if self == Side.SELL else Side.SELL

    @property
    def price_comparator(self) -> Callable[[Price, Price], bool]:
        if self == Side.BUY:
            return lambda buy_price, sell_price: buy_price >= sell_price
        return lambda sell_price, buy_price: sell_price <= buy_price

    @property
    def calc_fill_price(self) -> Callable[[Price, Price], Price]:
        if self == Side.BUY:
            return lambda buy_price, sell_price: min(buy_price, sell_price)
        return lambda sell_price, buy_price: max(sell_price, buy_price)


class OrderStatus(StrEnum):
    """Enum for Order Status after matching occurs"""

    QUEUED = auto()
    PARTIAL_FILL = auto()
    FILLED = auto()


@dataclass
class Order:
    """Order object"""

    id: UUID = field(init=False, default_factory=uuid4)
    price: Price
    quantity: int
    symbol: Symbol
    side: Side
    original_quantity: int = field(init=False)

    def __post_init__(self) -> None:
        # save original quantity for transaction summary
        self.original_quantity = self.quantity


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
