from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from decimal import Decimal
from typing import Generator

DEBUG = True
MIN_ORDER_PRICE: Decimal = Decimal("0")
MAX_ORDER_PRICE: Decimal = Decimal("10_000")
ID_COUNTER: int = 0
type Symbol = str
type Price = Decimal
type Level = deque[Order]
type LevelCollection = defaultdict[Symbol, defaultdict[Side, defaultdict[Price, deque]]]


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
class OrderRange:
    min_price: Decimal = MIN_ORDER_PRICE
    max_price: Decimal = MAX_ORDER_PRICE
    is_valid: bool = False


@dataclass
class Order:
    price: Price
    quantity: int
    symbol: Symbol
    side: Side
    is_cancelled: bool = False
    id: int = field(init=False)
    original_quantity: int = field(init=False)

    def __post_init__(self):
        global ID_COUNTER
        # increment clock to set new order id
        self.id = (ID_COUNTER := ID_COUNTER + 1)
        # handle float to decimal
        self.price = Decimal(str(self.price))
        # save original quantity for transaction summary
        self.original_quantity = self.quantity


@dataclass
class Transaction:
    incoming_order_id: int
    standing_order_id: int
    quantity: int
    price: Price


@dataclass
class TransactionSummary:
    order_id: int
    filled: OrderStatus
    transactions: list[Transaction] | None
    total_cost: Price | None
    average_price: Price | None

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


class Book:
    def __init__(self) -> None:
        self.levels: LevelCollection = defaultdict(
            lambda: defaultdict(lambda: defaultdict(deque))
        )
        self.order_range: defaultdict[Symbol, defaultdict[Side, OrderRange]] = (
            defaultdict(lambda: defaultdict(OrderRange))
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

    def get_level(self, symbol: str, side: Side, price: Decimal) -> Level:
        return self.levels[symbol][side][price]

    def iter_levels(
        self, symbol: str, side: Side, price: Price
    ) -> Generator[Level, None, None]:
        """Get levels for buy or sell levels within order range. For sells, yield levels with open interest
        from best sell (lowest) to worst (highest). For buys, iterate from highest to lowest price.
        """
        order_range: OrderRange = self.order_range[symbol][side]
        if not order_range.is_valid:
            print("No orders", symbol, side)
            return
        step_size: Decimal = Decimal("0.01")
        levels = self.levels[symbol][side]
        if side == side.BUY:
            curr = order_range.max_price
            end = max(price, order_range.min_price)
            while curr >= end:
                yield levels[curr]
                curr -= step_size
        else:
            curr = order_range.min_price
            end = min(price, order_range.max_price)
            while curr <= end:
                yield levels[curr]
                curr += step_size

    def enqueue_order(self, order: Order):
        # add to price level queue
        level = self.get_level(order.symbol, order.side, order.price)
        level.append(order)
        # create order reference in order_map
        self.order_map[order.id] = order
        # update min/max order price for symbol/side
        self.update_order_range(order.symbol, order.side, order.price)

    def flush_cancelled_order(self, order: Order, level: Level):
        del self.order_map[order.id]
        level.popleft()

    def process_order(self, incoming_order: Order) -> TransactionSummary:
        if DEBUG:
            print(
                "~~~ Processing",
                incoming_order,
                "\nOrder range",
                self.order_range[incoming_order.symbol][incoming_order.side.other],
            )
        # stores list of crossed order transactions. Used to compute
        # summary statistics in TransactionSummary object
        transactions: list[Transaction] = []
        for level in self.iter_levels(
            incoming_order.symbol, incoming_order.side.other, incoming_order.price
        ):
            while incoming_order.quantity and level:
                # if we reach this point, we have found the best standing order as of now
                standing_order: Order = level[0]
                if DEBUG:
                    print("Found matching standing", standing_order)

                # flush zombie orders that were previously cancelled
                if standing_order.is_cancelled:
                    self.flush_cancelled_order(standing_order, level)
                    continue

                # update quantities on incoming and standing order and
                # return Transaction object containing sale price and filled quantity
                transaction = self.fill(
                    standing_order=standing_order, incoming_order=incoming_order
                )
                transactions.append(transaction)

                # deque filled standing order
                if not standing_order.quantity:
                    level.popleft()

        # enqueue incoming order if partial or no fill.
        if incoming_order.quantity:
            self.enqueue_order(incoming_order)

        # compute transaction summary statistics
        transaction_summary: TransactionSummary = (
            TransactionSummary.from_order_and_transactions(incoming_order, transactions)
        )
        return transaction_summary

    def update_order_range(self, symbol: Symbol, side: Side, price: Price) -> None:
        order_range = self.order_range[symbol][side]
        if not order_range.is_valid:
            order_range.min_price = price
            order_range.max_price = price
            order_range.is_valid = True
        elif price < order_range.min_price:
            order_range.min_price = price
        elif price > order_range.max_price:
            order_range.max_price = price

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
