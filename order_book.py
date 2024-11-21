from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from decimal import Decimal
from typing import Generator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


type Symbol = str
type Price = Decimal
type Level = deque[Order]
type LevelCollection = defaultdict[Symbol, defaultdict[Side, defaultdict[Price, Level]]]

ID_COUNTER: int = 0
DEBUG = False
MIN_ORDER_PRICE: Price = Decimal("0")
MAX_ORDER_PRICE: Price = Decimal("10_000")


class Side(Enum):
    """Enum to represent BUY or SELL Order"""

    BUY = auto()
    SELL = auto()

    @property
    def other(self) -> "Side":
        return Side.BUY if self == Side.SELL else Side.SELL


class OrderStatus(Enum):
    """Enum for Order Status after matching occurs"""

    QUEUED = auto()
    PARTIAL_FILL = auto()
    FILLED = auto()


@dataclass
class PriceRange:
    """Stores min and max price for a symbol/side. Used to efficiently iterate
    over price levels
    """

    min_price: Price = MIN_ORDER_PRICE
    max_price: Price = MAX_ORDER_PRICE
    # marked true after first order arrives
    is_valid: bool = False


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
    transactions: list[Transaction] | None
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
            filled = OrderStatus.QUEUED
        elif order.quantity < order.original_quantity:
            filled = OrderStatus.PARTIAL_FILL
        else:
            filled = OrderStatus.FILLED
        if not transactions:
            return cls(order.id, filled, transactions, None, None)
        total_cost = Decimal(
            sum(txn.fill_price * txn.fill_quantity for txn in transactions)
        )
        avg_price = Decimal(
            sum(txn.fill_price for txn in transactions) / len(transactions)
        )
        return cls(order.id, filled, transactions, total_cost, avg_price)


class Book:
    """Main Order Book class. Orchestrates order handling and stores
    orders.
    """

    def __init__(self) -> None:
        """Creates required data structures for order matching"""
        self.levels: LevelCollection = defaultdict(
            lambda: defaultdict(lambda: defaultdict(deque))
        )
        self.price_range_map: defaultdict[Symbol, defaultdict[Side, PriceRange]] = (
            defaultdict(lambda: defaultdict(PriceRange))
        )
        self.order_map: dict[int, Order] = {}

    def fill(self, standing_order: Order, incoming_order: Order) -> Transaction:
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
        matched_price: Decimal = (
            standing_order.price
            if incoming_order.side == Side.BUY
            else incoming_order.price
        )
        transaction = Transaction(
            incoming_order.id, standing_order.id, matched_quantity, matched_price
        )
        logger.info("Filled Order: %s", transaction)
        return transaction

    def get_level(self, symbol: str, side: Side, price: Decimal) -> Level:
        """Return price level queue for a symbol/side/price
        :param symbol: order symbol
        :param side: order side
        :param price: order price
        :returns: price level (collections.deque[Order])
        """
        return self.levels[symbol][side][price]

    def iter_levels(
        self, symbol: str, side: Side, price: Price
    ) -> Generator[Level, None, None]:
        """Get levels for buy or sell levels within order range. For sells, yield levels with open interest
        from best sell (lowest) to worst (highest). For buys, iterate from highest to lowest price.
        :param symbol: incoming order symbol
        :param side: order side to iterate through. When this function is called in the process_order function,
        the opposite of the incoming order symbol (BUY -> SELL, SELL -> BUY) is provided to iterate over potential matching
        orders
        :param price: incoming order price, used to constrain iterator based on order side
        :returns: generator yielding Level types for all matching price levels
        """
        price_range: PriceRange = self.price_range_map[symbol][side]
        if not price_range.is_valid:
            return
        step_size: Decimal = Decimal("0.01")
        levels = self.levels[symbol][side]
        if side == side.BUY:
            curr = price_range.max_price
            end = max(price, price_range.min_price)
            logger.debug("Generating levels from price %s to %s", curr, end)
            while curr >= end:
                yield levels[curr]
                curr -= step_size
        else:
            curr = price_range.min_price
            end = min(price, price_range.max_price)
            logger.debug("Generating levels from price %s to %s", curr, end)
            while curr <= end:
                yield levels[curr]
                curr += step_size

    def enqueue_order(self, order: Order) -> None:
        """Add order to book.
        - enqueue order to price level
        - add reference to order in order_map
        - add/update price range for symbol/side
        :param order: order to add to book
        :returns: None
        """
        logger.info("Adding Order to book: %s", order)
        self.get_level(order.symbol, order.side, order.price).append(order)
        self.order_map[order.id] = order
        self.update_price_range(order.symbol, order.side, order.price)

    def flush_cancelled_order(self, order: Order, level: Level) -> None:
        """Flush cancelled order from price level and order map when
        order is encountered during order matching.
        :param order: order to cancel
        :param level: current level that the order at the head of
        :returns: None
        """
        logger.debug("Flushing canceled Order Id: %s from book: %s", order.id)
        del self.order_map[order.id]
        level.popleft()

    def process_order(self, incoming_order: Order) -> TransactionSummary:
        """Main Order procesing function which executes the price-time priority
        matching logic.
        :param incoming_order: incoming order
        :returns: TransactionSummary object containing transaction metadata on the transactions which
        occured during the matching process
        """
        logger.info("~~~ Processing order: %s", incoming_order)
        # stores list of crossed order transactions. Used to compute
        # summary statistics in TransactionSummary object
        transactions: list[Transaction] = []
        for level in self.iter_levels(
            incoming_order.symbol, incoming_order.side.other, incoming_order.price
        ):
            # exhaust price level until standing orders are filled or
            # incoming order quantity is filled
            while incoming_order.quantity and level:
                # if we reach this point, we have found the best standing order for the
                # incoming order price
                standing_order: Order = level[0]
                logger.debug("Found matching standing order: %s", standing_order)

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
        logger.info("Transaction Summary: %s", transaction_summary)
        return transaction_summary

    def update_price_range(self, symbol: Symbol, side: Side, price: Price) -> None:
        """Update min/max price in the PriceRange object for the symbol/side.
        This occurs when an order to added to the book.
        :param symbol: standing order symbol
        :param side: standing order side
        :param price: standing order price:
        :returns: None
        """
        logger.debug(
            "Updating price range for Symbol:Side %s:%s with new price: %s",
            symbol,
            side,
            price,
        )
        price_range = self.price_range_map[symbol][side]
        if not price_range.is_valid:
            price_range.min_price = price
            price_range.max_price = price
            price_range.is_valid = True
        elif price < price_range.min_price:
            price_range.min_price = price
        elif price > price_range.max_price:
            price_range.max_price = price

    def cancel_order(self, order_id: int) -> bool:
        """Cancel Standing Order
        :param order_id: id field of Order object
        :returns: False if order doesn't exist or if it's already cancelled, True if cancelled successfully.
        """
        logger.info("~~~ Processing Cancel Request for Order Id", order_id)
        if order_id not in self.order_map:
            logger.debug(
                f"Order Id {order_id} does not exist or was flushed from the book"
            )
            return False
        order = self.order_map[order_id]
        if order.is_cancelled:
            logger.debug(f"Zombie Order Id {order_id} is Already Cancelled")
            return False
        logger.debug("Canceled Order Id", order_id)
        order.is_cancelled = True
        return True


def simulate_order_flow():
    """Toy order flow simulation. Feel free to experiment and set 
    your desired log level at the top of the file!"""
    book = Book()
    book.process_order(Order(3.5, 70, "GOOG", Side.BUY))
    book.process_order(Order(3.6, 70, "GOOG", Side.BUY))
    book.process_order(Order(54.3, 140, "GOOG", Side.SELL))
    book.process_order(Order(3.1, 140, "GOOG", Side.SELL))
    book.process_order(Order(3.6, 70, "IBM", Side.BUY))
    book.process_order(Order(54.3, 10, "TSLA", Side.SELL))
    book.process_order(Order(3.1, 1430, "GOOG", Side.SELL))
    book.process_order(Order(5.3, 130, "TSLA", Side.BUY))

if __name__ == "__main__":
    simulate_order_flow()
