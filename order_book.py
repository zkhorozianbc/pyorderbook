from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import StrEnum, auto
from decimal import Decimal
from typing import Callable
import logging
import heapq as pq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    is_cancelled: bool = False
    original_quantity: int = field(init=False)

    def __post_init__(self):
        global ID_COUNTER
        # increment clock to set new order id
        self.id = (ID_COUNTER := ID_COUNTER + 1)
        # handle float to decimal
        self.price = Decimal(str(self.price))
        # save original quantity for transaction summary
        self.original_quantity = self.quantity


@dataclass(order=True)
class Level:
    side: Side = field(compare=False)
    price: Decimal = field(compare=False)
    orders: deque[Order] = field(default_factory=deque, compare=False)
    sort_key: Price = field(compare=True, init=False)

    def __post_init__(self):
        self.sort_key = self.price * (-1 if self.side == Side.BUY else 1)


@dataclass
class Transaction:
    """Stores transaction data for matched orders"""

    incoming_order_id: int
    standing_order_id: int
    fill_quantity: int
    fill_price: Price


@dataclass
class TransactionSummary:
    """Summary statistics return by the Book().process_order function.
    Displays order status, executed transactions, and order statistics
    including total cost and average price.
    """

    order_id: int
    filled: OrderStatus
    transactions: list[Transaction]
    num_transactions: int
    total_cost: Decimal | None
    average_price: Decimal | None

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
            return cls(order.id, filled, transactions,0, None, None)
        total_cost = Decimal(
            sum(txn.fill_price * txn.fill_quantity for txn in transactions)
        )
        avg_price = Decimal(
            sum(txn.fill_price for txn in transactions) / len(transactions)
        )
        return cls(order.id, filled, transactions, len(transactions), total_cost, avg_price)


class Book:
    """Main Order Book class. Orchestrates order handling and stores
    orders.
    """

    def __init__(self) -> None:
        """Creates required data structures for order matching"""
        self.levels = defaultdict(lambda: {Side.BUY: [], Side.SELL: []})
        self.level_map = defaultdict(lambda: {Side.BUY: {}, Side.SELL: {}})
        self.order_map: dict[int, Order] = {}

    def fill(
        self,
        incoming_order: Order,
        standing_order: Order,
    ) -> Transaction:
        """Execute order fill. Updates incoming and standing order objects, determines
        transaction price based on side, and matched quantity, and
        returns Transaction object containing transaction metadata.
        :param standing_order: standing order
        :param incoming_order: incoming order
        :returns: Transaction object containing metadata on the matched price/quantity and
        order id of the matched orders
        """
        matched_quantity: int = min(standing_order.quantity, incoming_order.quantity)
        standing_order.quantity -= matched_quantity
        incoming_order.quantity -= matched_quantity
        fill_price = incoming_order.side.calc_fill_price(
            incoming_order.price, standing_order.price
        )
        transaction = Transaction(
            incoming_order.id, standing_order.id, matched_quantity, fill_price
        )
        logger.info("Filled Order: %s", transaction)
        return transaction

    def get_level(self, symbol: str, side: Side, price: Decimal) -> Level | None:
        """Return price level queue for a symbol/side/price
        :param symbol: order symbol
        :param side: order side
        :param price: order price
        :returns: price level (collections.deque[Order])
        """
        return self.level_map[symbol][side].get(price, None)

    def enqueue_order(self, order: Order) -> None:
        """Add order to book.
        - enqueue order to price level
        - add reference to order in order_map
        :param order: order to add to book
        :returns: None
        """
        logger.info("Adding Order to book: %s", order)
        level = self.get_level(order.symbol, order.side, order.price)
        if level is None:
            # create price level
            level = Level(order.side, order.price)
            # add level object to self.levels heap
            pq.heappush(self.levels[order.symbol][order.side], level)
            # add level reference to level map
            self.level_map[order.symbol][order.side][order.price] = level
        level.orders.append(order)
        self.order_map[order.id] = order

    def flush_order(self, order: Order, orders_at_level: deque[Order]) -> None:
        """Flush cancelled or filled standing order from price level and order map when
        order is encountered during order matching.
        :param order: order to cancel
        :param level: current level that the order at the head of
        :returns: None
        """
        logger.debug("Flushing Order Id: %s from book: %s", order.id)
        orders_at_level.popleft()
        self.order_map.pop(order.id)

    def flush_price_level(self, symbol: Symbol, level: Level) -> None:
        """Pop price level from book and deference level in level map
        :param symbol: symbol of security
        :param level: current level to delete
        :returns: None
        """
        logger.info("Flushing Price Level for %s at %s price %s", symbol, str(level.side), level.price)
        self.level_map[symbol][level.side].pop(level.price)
        pq.heappop(self.levels[symbol][level.side])

    def process_order(self, incoming_order: Order) -> TransactionSummary:
        """Main Order procesing function which executes the price-time priority
        matching logic.
        :param incoming_order: incoming order
        :returns: TransactionSummary object containing transaction metadata on the transactions which
        occured during the matching process
        """
        logger.info("~~~ Processing order: %s", incoming_order)
        transactions: list[Transaction] = []
        price_comparator = incoming_order.side.price_comparator
        levels = self.levels[incoming_order.symbol][incoming_order.side.other]
        while incoming_order.quantity and levels:
            level = levels[0]
            orders_at_level = level.orders
            price_at_level = level.price
            if not price_comparator(incoming_order.price, price_at_level):
                break
            while incoming_order.quantity and orders_at_level:
                best_standing_order = orders_at_level[0]
                if best_standing_order.is_cancelled:
                    self.flush_order(best_standing_order, orders_at_level)
                    continue
                transactions.append(
                    self.fill(incoming_order, best_standing_order)
                )
                if not best_standing_order.quantity:
                    self.flush_order(best_standing_order, orders_at_level)

            if not orders_at_level:
                self.flush_price_level(incoming_order.symbol, level)

        if incoming_order.quantity:
            self.enqueue_order(incoming_order)
    
        transaction_summary = TransactionSummary.from_order_and_transactions(
            incoming_order, transactions
        )
        logger.info("%s", transaction_summary)
        return transaction_summary

    def cancel_order(self, order_id: int) -> bool:
        """Cancel Standing Order. Mark order.is_cancelled to true. The order will be flushed
        from the book when it is encountered during the matching process if it's seen
        :param order_id: id field of Order object
        :returns: False if order doesn't exist or if it's already cancelled, True if cancelled successfully.
        """
        logger.info("~~~ Processing Cancel Request for Order Id", order_id)
        order = self.order_map.get(order_id, None)
        if order is None:
            logger.error("Order %s doesnt exist", order_id)
            return False
        elif order.is_cancelled:
            logger.warning(
                "Order %s is already cancelled and hasnt been removed yet", order_id
            )
        order.is_cancelled = True
        return True


def simulate_order_flow():
    """Toy order flow simulation. Feel free to experiment and set
    your desired log level at the top of the file!"""
    book = Book()
    book.process_order(Order(3.6, 70, "GOOG", Side.SELL))
    book.process_order(Order(3.5, 70, "GOOG", Side.SELL))
    book.process_order(Order(3.7, 150, "GOOG", Side.BUY))
    book.process_order(Order(3.1, 140, "GOOG", Side.SELL))
    book.process_order(Order(3.6, 70, "IBM", Side.BUY))
    book.process_order(Order(54.3, 10, "TSLA", Side.SELL))
    book.process_order(Order(3.1, 1430, "GOOG", Side.BUY))
    book.process_order(Order(5.3, 130, "TSLA", Side.BUY))


if __name__ == "__main__":
    simulate_order_flow()
