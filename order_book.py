from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from decimal import Decimal

class Side(Enum):
    BUY = auto()
    SELL = auto()

    @property
    def other(self) -> "Side":
        return Side.BUY if self == Side.SELL else Side.SELL

class OrderStatus(Enum):
    QUEUED = auto()
    PARTIAL_FILL = auto()
    FILLED = auto()


@dataclass
class Order:
    price: Decimal
    quantity: int
    symbol: str
    side: Side
    is_cancelled: bool = False
    id: int = field(init=False)
    original_quantity: int = field(init=False)

    _clock: int = field(init=False, repr=False, default=0)

    def __post_init__(self):
        #increment clock to set new order id
        self._clock += 1
        self.id = self._clock
        # handle float to decimal
        self.price = Decimal(str(self.price))
        # save original quantity for transaction summary
        self.original_quantity = self.quantity


@dataclass
class Transaction:
    incoming_order_id: int
    standing_order_id: int
    quantity: int
    price: Decimal


@dataclass
class TransactionSummary:
    order_id: int
    filled: OrderStatus
    transactions: list[Transaction] | None
    total_cost: Decimal | None
    average_price: Decimal | None

    @classmethod
    def from_order_and_transactions(
        cls, order: Order, transactions: list[Transaction]
    ) -> "TransactionSummary":
        filled: OrderStatus
        if order.quantity == 0:
            filled = OrderStatus.QUEUED
        elif order.quantity < order.original_quantity:
            filled = OrderStatus.PARTIAL_FILL
        else:
            filled = OrderStatus.FILLED
        if not transactions:
            return cls(order.id, filled, transactions, None, None)
        total_cost = Decimal(sum(txn.price * txn.quantity for txn in transactions))
        avg_price = Decimal(sum(txn.price for txn in transactions) / len(transactions))
        return cls(order.id, filled, transactions, total_cost, avg_price)


def price_iterator(price: Decimal, side: Side):
    min_price: Decimal = Decimal("0.0")
    max_price: Decimal = Decimal("1000.0")
    start: Decimal = min_price if side == Side.BUY else max_price
    end: Decimal = price
    step_size: Decimal = Decimal("0.01")
    if side == Side.SELL:
        step_size *= -1
    while start <= end:
        yield start
        start += step_size


class Book:
    def __init__(self) -> None:
        self.levels: defaultdict[str, defaultdict[Side, defaultdict[Decimal, deque[Order]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(deque))
        )
        self.order_map: dict[int, Order] = {}

    def fill(self, standing_order: Order, incoming_order: Order) -> Transaction:
        matched_quantity: int = min(standing_order.quantity, incoming_order.quantity)
        standing_order.quantity -= matched_quantity
        incoming_order.quantity -= matched_quantity
        matched_price: Decimal = (
            standing_order.price
            if incoming_order.side == Side.BUY
            else incoming_order.price
        )
        return Transaction(
            incoming_order.id, standing_order.id, matched_quantity, matched_price
        )

    def process_order(self, incoming_order: Order) -> TransactionSummary:
        print("~~~ Processing", incoming_order)
        transactions: list[Transaction] = []
        standing_orders = self.levels[incoming_order.symbol][incoming_order.side.other]
        for price in price_iterator(incoming_order.price, incoming_order.side):
            while incoming_order.quantity and standing_orders[price]:
                level = standing_orders[price]
                standing_order: Order = level[0]
                if standing_order.is_cancelled:
                    del self.order_map[standing_order.id]
                    level.popleft()
                    continue
                transaction = self.fill(
                    standing_order=standing_order, incoming_order=incoming_order
                )
                transactions.append(transaction)
                if not standing_order.quantity:
                    level.popleft()
        if incoming_order.quantity:
            self.levels[incoming_order.symbol][incoming_order.side][
                incoming_order.price
            ].append(incoming_order)
            self.order_map[incoming_order.id] = incoming_order
        transaction_summary: TransactionSummary = (
            TransactionSummary.from_order_and_transactions(incoming_order, transactions)
        )
        return transaction_summary

    def cancel_order(self, order_id: int) -> bool:
        print("~~~ Processing Cancel Request for Order Id", order_id)
        if order_id not in self.order_map:
            print(f"Order Id {order_id} does not exist or was flushed from the book")
            return False
        order = self.order_map[order_id]
        if order.is_cancelled:
            print(f"Zombie Order Id {order_id} is Already Cancelled")
            return False
        print("Canceled Order Id", order_id)
        order.is_cancelled = True
        return True
