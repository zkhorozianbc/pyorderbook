from dataclasses import dataclass, field
from decimal import Decimal

from orderbook.order import OrderQueue, Side

type Price = Decimal


@dataclass
class PriceLevel:
    side: Side = field(compare=False)
    price: Price = field(compare=False)
    orders: OrderQueue = field(default_factory=OrderQueue, compare=False)

    def __lt__(self, other: "PriceLevel") -> bool:
        """Buys should be max heap, sells min heap"""
        return self.side.price_comparator(self.price, other.price)
