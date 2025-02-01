from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from enum import StrEnum
from enum import auto

type Symbol = str
type Price = Decimal
ID_COUNTER: int = 0


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

    id: int = field(init=False)
    price: Price
    quantity: int
    symbol: Symbol
    side: Side
    original_quantity: int = field(init=False)

    def __post_init__(self):
        global ID_COUNTER
        # increment clock to set new order id
        self.id = (ID_COUNTER := ID_COUNTER + 1)
        # handle float to decimal
        self.price = Decimal(str(self.price))
        # save original quantity for transaction summary
        self.original_quantity = self.quantity


class OrderQueue(dict):
    def append_order(self, order: Order) -> None:
        self[order.id] = order

    def peek(self):
        if not self:
            raise ValueError("Order Queue is Empty!")
        first_key = next(iter(self))
        return self[first_key]

    def popleft(self):
        self.pop(self.peek().id)
