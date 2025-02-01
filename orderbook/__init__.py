from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

try:
    __version__ = version("orderbook")
except PackageNotFoundError:
    __version__ = "unknown"

from orderbook.book import Book
from orderbook.level import PriceLevel
from orderbook.order import Order
from orderbook.order import OrderQueue
from orderbook.order import OrderStatus
from orderbook.order import Side
from orderbook.transaction import Transaction
from orderbook.transaction import TransactionSummary

__all__ = [
    "Book",
    "Order",
    "OrderQueue",
    "OrderStatus",
    "Side",
    "PriceLevel",
    "Transaction",
    "TransactionSummary",
]
