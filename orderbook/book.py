import heapq as pq
import logging
from collections import defaultdict
from decimal import Decimal

from orderbook.level import PriceLevel
from orderbook.order import Order
from orderbook.order import Side
from orderbook.transaction import Transaction
from orderbook.transaction import TransactionSummary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


type Symbol = str
type Price = Decimal
type PriceLevelHeap = list[PriceLevel]


class Book:
    """Main Order Book class. Orchestrates order handling and stores
    orders.
    """

    def __init__(self) -> None:
        """Creates required data structures for order matching"""
        self.levels: defaultdict[str, dict[Side, PriceLevelHeap]] = defaultdict(
            lambda: {Side.BUY: [], Side.SELL: []}
        )
        self.level_map: defaultdict[str, dict[Side, dict[Price, PriceLevel]]] = defaultdict(
            lambda: {Side.BUY: {}, Side.SELL: {}}
        )
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
        fill_price = incoming_order.side.calc_fill_price(incoming_order.price, standing_order.price)
        transaction = Transaction(
            incoming_order.id, standing_order.id, matched_quantity, fill_price
        )
        logger.info("Filled Order: %s", transaction)
        return transaction

    def get_level(self, symbol: str, side: Side, price: Decimal) -> PriceLevel | None:
        """Return price level queue for a symbol/side/price
        :param symbol: order symbol
        :param side: order side
        :param price: order price
        :returns: price level (OrderQueue)
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
            level = PriceLevel(order.side, order.price)
            # add level object to self.levels heap
            pq.heappush(self.levels[order.symbol][order.side], level)
            # add level reference to level map
            self.level_map[order.symbol][order.side][order.price] = level
        level.orders.append_order(order)
        self.order_map[order.id] = order

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
            if not price_comparator(incoming_order.price, level.price):
                break
            while incoming_order.quantity and level.orders:
                best_standing_order = level.orders.peek()
                transaction: Transaction = self.fill(incoming_order, best_standing_order)
                transactions.append(transaction)
                if not best_standing_order.quantity:
                    logger.debug(
                        "Filled standing Order Id: %s from book: %s",
                        best_standing_order.id,
                    )
                    level.orders.popleft()
                    self.order_map.pop(best_standing_order.id)

            if not level.orders:
                logger.info(
                    "Flushing Price Level for %s at %s price %s",
                    incoming_order.symbol,
                    str(level.side),
                    level.price,
                )
                self.level_map[incoming_order.symbol][level.side].pop(level.price)
                pq.heappop(self.levels[incoming_order.symbol][level.side])

        if incoming_order.quantity:
            self.enqueue_order(incoming_order)

        transaction_summary = TransactionSummary.from_order_and_transactions(
            incoming_order, transactions
        )
        logger.info("%s", transaction_summary)
        return transaction_summary

    def cancel_order(self, order_id: int) -> bool:
        """Cancel Standing Order. Remove order from its price level and delete
        reference in order id map
        :param order_id: id field of Order object
        :returns: False if order doesn't exist or if it's already cancelled, True if cancelled successfully.
        """
        logger.info("~~~ Processing Cancel Request for Order Id", order_id)
        order = self.order_map.pop(order_id, None)
        if order is None:
            logger.error("Order %s doesnt exist", order_id)
            return False
        level = self.get_level(order.symbol, order.side, order.price)
        if level is None:
            raise ValueError(
                f"Price Level {order.symbol}:{order.side}:{order.price} doesn't exist!"
            )
        level.orders.pop(order_id)
