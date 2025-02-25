from dataclasses import dataclass, field
from decimal import Decimal
from typing import TypeAlias
from uuid import UUID

from orderbook.order import Order

Price: TypeAlias = Decimal


@dataclass
class Trade:
    """Stores trade data for matched orders"""

    incoming_order_id: UUID
    standing_order_id: UUID
    fill_quantity: int
    fill_price: Price


@dataclass
class TradeBlotter:
    """blotter statistics return by the Book().match function.
    Displays order status, executed trades, and order statistics
    including total cost and average price.
    """

    order: Order
    trades: list[Trade]
    num_trades: int = field(default=0, init=False)
    total_cost: float = field(default=0, init=False)
    average_price: float = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.trades:
            self.total_cost = round(
                float(sum(trade.fill_price * trade.fill_quantity for trade in self.trades)), 2
            )
            self.average_price = round(
                float(sum(trade.fill_price for trade in self.trades) / len(self.trades)), 2
            )
