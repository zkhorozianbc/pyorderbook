from dataclasses import dataclass, field
from decimal import Decimal
from typing import TypeAlias
from uuid import UUID

from pyorderbook.order import Order

Price: TypeAlias = Decimal


@dataclass
class Trade:
    """Stores trade data for matched orders"""

    incoming_order_id: UUID
    standing_order_id: UUID
    fill_quantity: int
    fill_price: Price

    def get_incoming_order_id(self) -> UUID:
        return self.incoming_order_id

    def get_standing_order_id(self) -> UUID:
        return self.standing_order_id

    def get_fill_quantity(self) -> int:
        return self.fill_quantity

    def get_fill_price(self) -> Price:
        return self.fill_price


@dataclass
class TradeBlotter:
    """blotter statistics return by the Book().match function.
    Displays order status, executed trades, and order statistics
    including total cost and average price.
    """

    order: Order
    trades: list[Trade]
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

    def get_order(self) -> Order:
        return self.order

    def get_trades(self) -> list[Trade]:
        return self.trades

    def get_total_cost(self) -> float:
        return self.total_cost

    def get_average_price(self) -> float:
        return self.average_price
