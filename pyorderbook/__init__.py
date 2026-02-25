from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyorderbook")
except PackageNotFoundError:
    __version__ = "v0.5.0"

_USING_RUST = False

try:
    from pyorderbook._rust import (
        Book,
        Order,
        OrderQueue,
        OrderStatus,
        PriceLevel,
        Side,
        Snapshot,
        SnapshotLevel,
        Trade,
        TradeBlotter,
        ask,
        bid,
    )

    _USING_RUST = True
except ImportError:
    from pyorderbook.book import Book
    from pyorderbook.level import PriceLevel
    from pyorderbook.order import Order, OrderQueue, OrderStatus, Side, ask, bid
    from pyorderbook.snapshot import Snapshot, SnapshotLevel
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
    "Snapshot",
    "SnapshotLevel",
    "Trade",
    "TradeBlotter",
    "easter_egg",
    "_USING_RUST",
]
