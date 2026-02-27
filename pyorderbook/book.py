import heapq as pq
import logging
from collections import defaultdict
from decimal import Decimal
from typing import TypeAlias, cast, overload
from uuid import UUID

from pyorderbook.level import PriceLevel
from pyorderbook.order import Order, Side
from pyorderbook.snapshot import Snapshot, SnapshotLevel
from pyorderbook.trade_blotter import Trade, TradeBlotter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Symbol: TypeAlias = str
Price: TypeAlias = Decimal
PriceLevelHeap: TypeAlias = list[PriceLevel]
REQUIRED_PARQUET_COLUMNS: tuple[str, str, str, str] = ("side", "symbol", "price", "quantity")


def _read_parquet_rows(path: str) -> list[dict[str, object]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise ImportError(
            "pyarrow is required for parquet ingestion. Install with `pip install pyarrow`."
        ) from exc

    table = parquet.read_table(path)
    missing_columns = [name for name in REQUIRED_PARQUET_COLUMNS if name not in table.column_names]
    if missing_columns:
        required = ", ".join(REQUIRED_PARQUET_COLUMNS)
        missing = ", ".join(missing_columns)
        raise ValueError(f"Parquet file must contain columns [{required}]; missing [{missing}].")
    return cast(list[dict[str, object]], table.to_pylist())


class Book:
    """Main Order Book class. Orchestrates order handling and stores
    orders.
    """

    def __init__(self) -> None:
        """Creates required data structures for order matching"""
        self.levels: defaultdict[str, dict[Side, PriceLevelHeap]] = defaultdict(
            lambda: {Side.BID: [], Side.ASK: []}
        )
        self.level_map: defaultdict[str, dict[Side, dict[Price, PriceLevel]]] = defaultdict(
            lambda: {Side.BID: {}, Side.ASK: {}}
        )
        self.order_map: dict[UUID, Order] = {}

    @overload
    def match(self, orders: Order) -> TradeBlotter: ...

    @overload
    def match(self, orders: list[Order]) -> list[TradeBlotter]: ...

    def match(self, orders: Order | list[Order]) -> TradeBlotter | list[TradeBlotter]:
        """Match incoming order(s) against standing orders in the book.
        :param order: incoming order
        :returns: TradeBlotter object containing trade metadata on the trades
        which occured during the matching process
        """
        if isinstance(orders, list):
            return [self.match(order) for order in orders]
        elif isinstance(orders, Order):
            return self._match(orders)
        raise ValueError("Invalid input type", type(orders))

    def replay_parquet(self, path: str) -> list[TradeBlotter]:
        """Replay an event-stream parquet file through the matching engine."""
        blotters: list[TradeBlotter] = []
        for row_idx, row in enumerate(_read_parquet_rows(path)):
            order = self._order_from_parquet_row(row, row_idx)
            blotter = self.match(order)
            if not isinstance(blotter, TradeBlotter):
                raise TypeError("Expected TradeBlotter from single-order replay")
            blotters.append(blotter)
        return blotters

    def ingest_parquet(self, path: str) -> int:
        """Ingest a snapshot parquet file directly as standing orders."""
        rows = _read_parquet_rows(path)
        for row_idx, row in enumerate(rows):
            self.enqueue_order(self._order_from_parquet_row(row, row_idx))
        return len(rows)

    @classmethod
    def from_parquet(cls, path: str) -> "Book":
        """Construct a Book from a snapshot parquet file."""
        book = cls()
        book.ingest_parquet(path)
        return book

    def _match(self, incoming_order: Order) -> TradeBlotter:
        """Main Order procesing function which executes the price-time priority
        matching logic.
        :param incoming_order: incoming order
        :returns: TradeBlotter object containing trade metadata on the trades
        which occured during the matching process
        """
        logger.debug("~~~ Processing order: %s", incoming_order)
        trades: list[Trade] = []
        price_comparator = incoming_order.side.price_comparator
        levels = self.levels[incoming_order.symbol][incoming_order.side.other]
        while incoming_order.quantity and levels:
            level = levels[0]
            if not price_comparator(incoming_order.price, level.price):
                break
            while incoming_order.quantity and level.orders:
                best_standing_order = level.orders.peek()
                trade: Trade = self.fill(incoming_order, best_standing_order)
                trades.append(trade)
                if not best_standing_order.quantity:
                    logger.debug(
                        "Filled standing Order Id: %s from book: %s",
                        best_standing_order.id,
                    )
                    level.orders.popleft()
                    self.order_map.pop(best_standing_order.id)

            if not level.orders:
                logger.debug(
                    "Flushing Price Level for %s at %s price %s",
                    incoming_order.symbol,
                    str(level.side),
                    level.price,
                )
                self.level_map[incoming_order.symbol][level.side].pop(level.price)
                pq.heappop(self.levels[incoming_order.symbol][level.side])

        if incoming_order.quantity:
            self.enqueue_order(incoming_order)

        trade_blotter = TradeBlotter(incoming_order, trades)
        logger.debug("%s", trade_blotter)
        return trade_blotter

    def cancel(self, order: Order) -> None:
        """Cancel Standing Order. Remove order from its price level and delete
        reference in order id map
        :param order_id: id field of Order object
        :returns: False if order doesn't exist or if it's already cancelled,
        True if cancelled successfully.
        """
        order_id = order.id
        logger.debug("~~~ Processing Cancel Request for Order Id", order_id)
        try:
            self.order_map.pop(order.id)
        except KeyError:
            logger.error("Order %s doesnt exist", order_id)
            raise

        level = self.get_level(order.symbol, order.side, order.price)
        if level is None:
            raise ValueError(
                f"Price Level {order.symbol}:{order.side}:{order.price} doesn't exist!"
            )
        level.orders.pop(order_id)

    def fill(
        self,
        incoming_order: Order,
        standing_order: Order,
    ) -> Trade:
        """Execute order fill. Updates incoming and standing order objects, determines
        trade price based on side, and matched quantity, and
        returns Trade object containing trade metadata.
        :param standing_order: standing order
        :param incoming_order: incoming order
        :returns: Trade object containing metadata on the matched price/quantity and
        order id of the matched orders
        """
        matched_quantity: int = min(standing_order.quantity, incoming_order.quantity)
        standing_order.quantity -= matched_quantity
        incoming_order.quantity -= matched_quantity
        fill_price = incoming_order.side.calc_fill_price(incoming_order.price, standing_order.price)
        trade = Trade(incoming_order.id, standing_order.id, matched_quantity, fill_price)
        logger.debug("Filled Order: %s", trade)
        return trade

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
        logger.debug("Adding Order to book: %s", order)
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

    def get_order(self, order_id: UUID) -> Order | None:
        """Return order object from order id
        :param order_id: id field of Order object
        :returns: Order object
        """
        return self.order_map.get(order_id, None)

    def snapshot(self, symbol: str, depth: int = 5) -> Snapshot | None:
        """Return an L2 depth snapshot for a symbol, or None if never seen."""
        if symbol not in self.levels:
            return None
        depth = max(0, depth)

        # Extract top-N bid levels (best = highest price first)
        bid_heap = list(self.levels[symbol][Side.BID])
        bid_levels: list[SnapshotLevel] = []
        for _ in range(min(depth, len(bid_heap))):
            lvl = pq.heappop(bid_heap)
            qty = sum(order.quantity for order in lvl.orders.values())
            bid_levels.append(SnapshotLevel(price=lvl.price, quantity=qty))

        # Extract top-N ask levels (best = lowest price first)
        ask_heap = list(self.levels[symbol][Side.ASK])
        ask_levels: list[SnapshotLevel] = []
        for _ in range(min(depth, len(ask_heap))):
            lvl = pq.heappop(ask_heap)
            qty = sum(order.quantity for order in lvl.orders.values())
            ask_levels.append(SnapshotLevel(price=lvl.price, quantity=qty))

        best_bid = bid_levels[0].price if bid_levels else None
        best_ask = ask_levels[0].price if ask_levels else None

        spread: Decimal | None = None
        midpoint: Decimal | None = None
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            midpoint = (best_ask + best_bid) / Decimal(2)

        bid_vwap = self._compute_vwap(bid_levels)
        ask_vwap = self._compute_vwap(ask_levels)

        return Snapshot(
            bids=bid_levels,
            asks=ask_levels,
            spread=spread,
            midpoint=midpoint,
            bid_vwap=bid_vwap,
            ask_vwap=ask_vwap,
        )

    def get_order_map(self) -> dict[UUID, Order]:
        return self.order_map

    def get_levels(self) -> defaultdict[str, dict[Side, PriceLevelHeap]]:
        return self.levels

    def get_level_map(self) -> defaultdict[str, dict[Side, dict[Price, PriceLevel]]]:
        return self.level_map

    @staticmethod
    def _compute_vwap(levels: list[SnapshotLevel]) -> Decimal | None:
        total_pq = Decimal(0)
        total_q = 0
        for lvl in levels:
            total_pq += lvl.price * lvl.quantity
            total_q += lvl.quantity
        if total_q == 0:
            return None
        return total_pq / Decimal(total_q)

    @staticmethod
    def _order_from_parquet_row(row: dict[str, object], row_idx: int) -> Order:
        side_raw = row.get("side")
        if side_raw is None:
            raise ValueError(f"Missing required field 'side' at row {row_idx}")
        side_text = str(side_raw).lower()
        try:
            side = Side(side_text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid side at row {row_idx}: '{side_raw}'. Expected 'bid' or 'ask'."
            ) from exc

        symbol_raw = row.get("symbol")
        if symbol_raw is None:
            raise ValueError(f"Missing required field 'symbol' at row {row_idx}")
        symbol = str(symbol_raw)
        if not symbol:
            raise ValueError(f"Symbol cannot be empty at row {row_idx}")

        price_raw = row.get("price")
        if price_raw is None:
            raise ValueError(f"Missing required field 'price' at row {row_idx}")
        if not isinstance(price_raw, int | float | str):
            raise ValueError(f"Invalid price at row {row_idx}: '{price_raw}'")
        try:
            price = float(price_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid price at row {row_idx}: '{price_raw}'") from exc

        quantity_raw = row.get("quantity")
        if quantity_raw is None:
            raise ValueError(f"Missing required field 'quantity' at row {row_idx}")
        if isinstance(quantity_raw, bool):
            raise ValueError(f"Invalid quantity at row {row_idx}: '{quantity_raw}'")
        try:
            if isinstance(quantity_raw, float):
                if not quantity_raw.is_integer():
                    raise ValueError(f"Invalid quantity at row {row_idx}: '{quantity_raw}'")
                quantity = int(quantity_raw)
            elif isinstance(quantity_raw, int | str):
                quantity = int(quantity_raw)
            else:
                raise ValueError(f"Invalid quantity at row {row_idx}: '{quantity_raw}'")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid quantity at row {row_idx}: '{quantity_raw}'") from exc

        return Order(side, symbol, price, quantity)
