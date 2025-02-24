from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orderbook.order import Order, OrderStatus

type Price = Decimal


@dataclass
class Transaction:
    """Stores transaction data for matched orders"""

    incoming_order_id: UUID
    standing_order_id: UUID
    fill_quantity: int
    fill_price: Price


@dataclass
class TransactionSummary:
    """Summary statistics return by the Book().match function.
    Displays order status, executed transactions, and order statistics
    including total cost and average price.
    """

    order_id: UUID
    filled: OrderStatus
    transactions: list[Transaction]
    num_transactions: int
    total_cost: float | None
    average_price: float | None

    @classmethod
    def from_order_and_transactions(
        cls, order: Order, transactions: list[Transaction]
    ) -> "TransactionSummary":
        """Class Factory to create transaction summary from incoming order
        and a list of transactions that occured during the matching process.
        :param order: incoming order
        :param transactions: list of transactions that occured during matching
        :returns: Self
        """
        filled: OrderStatus
        if order.quantity == 0:
            filled = OrderStatus.FILLED
        elif order.quantity < order.original_quantity:
            filled = OrderStatus.PARTIAL_FILL
        else:
            filled = OrderStatus.QUEUED
        if not transactions:
            return cls(order.id, filled, transactions, 0, None, None)
        total_cost = round(float(sum(txn.fill_price * txn.fill_quantity for txn in transactions)), 2)
        avg_price = round(float(
            sum(txn.fill_price for txn in transactions) / len(transactions)
        ), 2)
        return cls(order.id, filled, transactions, len(transactions), total_cost, avg_price)
