from dataclasses import dataclass, field
from decimal import Decimal
from typing import TypeAlias

from pyorderbook.order import OrderQueue, Side

Price: TypeAlias = Decimal


@dataclass
class PriceLevel:
    side: Side
    price: Price
    orders: OrderQueue = field(default_factory=OrderQueue)

    def __lt__(self, other: "PriceLevel") -> bool:
        """BIDS should be max heap, asks min heap"""
        return self.side.price_comparator(self.price, other.price)

    def get_side(self) -> Side:
        return self.side

    def get_price(self) -> Price:
        return self.price

    def get_orders(self) -> OrderQueue:
        return self.orders
