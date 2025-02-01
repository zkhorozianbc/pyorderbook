from dataclasses import dataclass, field
from orderbook.order import OrderQueue, Order, Side
from decimal import Decimal

type Price = Decimal

@dataclass(order=True)
class PriceLevel:
    side: Side = field(compare=False)
    price: Price = field(compare=False)
    orders: OrderQueue = field(default_factory=OrderQueue, compare=False)
    sort_key: Price = field(compare=True, init=False)

    def __post_init__(self):
        self.sort_key = self.price * (-1 if self.side == Side.BUY else 1)
