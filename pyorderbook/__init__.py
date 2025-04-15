from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyorderbook")
except PackageNotFoundError:
    __version__ = "v0.5.0"

from pyorderbook.book import Book
from pyorderbook.level import PriceLevel
from pyorderbook.order import Order, OrderQueue, OrderStatus, Side, ask, bid
from pyorderbook.trade_blotter import Trade, TradeBlotter

easter_egg = "artificial lake"
__all__ = [
    "Book",
    "bid",
    "ask",
    "Order",
    "OrderQueue",
    "OrderStatus",
    "Side",
    "PriceLevel",
    "Trade",
    "TradeBlotter",
    "easter_egg",
]
