import builtins
import heapq
import importlib
import importlib.metadata
import sys
import types
import uuid
from decimal import Decimal
from typing import Any, cast

import pytest

import pyorderbook.book as book_module
from pyorderbook.book import Book, _read_parquet_rows
from pyorderbook.level import PriceLevel
from pyorderbook.order import Order, OrderQueue, OrderStatus, Side, ask, bid
from pyorderbook.snapshot import Snapshot, SnapshotLevel
from pyorderbook.trade_blotter import Trade, TradeBlotter


def test_package_can_import_python_fallback_when_rust_backend_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "pyorderbook" or name.startswith("pyorderbook.")
    }

    def missing_distribution(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    original_import = cast(Any, builtins.__import__)

    def block_rust_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pyorderbook._rust":
            raise ImportError("blocked for fallback test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "version", missing_distribution)
    monkeypatch.setattr(builtins, "__import__", block_rust_import)

    try:
        for name in list(sys.modules):
            if name == "pyorderbook" or name.startswith("pyorderbook."):
                sys.modules.pop(name)

        fallback_package = importlib.import_module("pyorderbook")

        assert fallback_package.__version__ == "v0.5.0"
        assert fallback_package._USING_RUST is False
        assert fallback_package.Book.__module__ == "pyorderbook.book"
        assert fallback_package.bid("AAPL", 100.0, 1).side == fallback_package.Side.BID
    finally:
        for name in list(sys.modules):
            if name == "pyorderbook" or name.startswith("pyorderbook."):
                sys.modules.pop(name)
        sys.modules.update(saved_modules)


def test_python_order_side_and_getter_surface() -> None:
    order = Order(Side.BID, "AAPL", 150.25, 100)

    assert Side.BID.other == Side.ASK
    assert Side.ASK.other == Side.BID
    assert Side.BID.price_comparator(Decimal("10"), Decimal("9"))
    assert Side.ASK.price_comparator(Decimal("9"), Decimal("10"))
    assert Side.BID.calc_fill_price(Decimal("12"), Decimal("10")) == Decimal("10")
    assert Side.ASK.calc_fill_price(Decimal("10"), Decimal("12")) == Decimal("12")

    assert order.get_id() == order.id
    assert order.get_price() == Decimal("150.25")
    assert order.get_quantity() == 100
    assert order.get_symbol() == "AAPL"
    assert order.get_side() == Side.BID
    assert order.get_original_quantity() == 100
    assert order.get_status() == OrderStatus.QUEUED

    order.quantity = 40
    assert order.status == OrderStatus.PARTIAL_FILL

    filled_order = Order(Side.ASK, "AAPL", 150.25, 100)
    filled_order.quantity = 0
    assert filled_order.status == OrderStatus.FILLED


@pytest.mark.parametrize("quantity", [0, -1])
def test_python_order_rejects_non_positive_quantity(quantity: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        bid("AAPL", 150.0, quantity)


def test_python_book_bid_and_ask_methods_create_orders_and_match() -> None:
    book = Book()

    book.match(book.bid("IBM", 3.5, 20))
    book.match(book.ask("IBM", 3.6, 10))
    trade_blotter = book.match(book.ask("IBM", 3.5, 10))

    assert bid("IBM", 3.5, 1).side == book.bid("IBM", 3.5, 1).side
    assert ask("IBM", 3.5, 1).side == book.ask("IBM", 3.5, 1).side
    assert len(trade_blotter.trades) == 1
    assert trade_blotter.average_price == 3.5


def test_python_order_queue_fifo_dict_surface() -> None:
    queue = OrderQueue()
    first = bid("AAPL", 150.0, 10)
    second = bid("AAPL", 151.0, 20)

    assert not queue
    with pytest.raises(ValueError, match="Empty"):
        queue.peek()
    with pytest.raises(ValueError, match="Empty"):
        queue.popleft()

    queue.append_order(first)
    queue.append_order(second)

    assert queue
    assert list(queue) == [first.id, second.id]
    assert queue[first.id] is first
    assert queue.peek() is first
    queue.popleft()
    assert queue.peek() is second
    assert queue.pop(second.id) is second
    assert len(queue) == 0


def test_python_price_level_heap_order_and_getters() -> None:
    bid_heap = [PriceLevel(Side.BID, Decimal("10")), PriceLevel(Side.BID, Decimal("12"))]
    heapq.heapify(bid_heap)
    assert heapq.heappop(bid_heap).get_price() == Decimal("12")

    ask_heap = [PriceLevel(Side.ASK, Decimal("12")), PriceLevel(Side.ASK, Decimal("10"))]
    heapq.heapify(ask_heap)
    best_ask = heapq.heappop(ask_heap)
    assert best_ask.get_side() == Side.ASK
    assert best_ask.get_price() == Decimal("10")
    assert isinstance(best_ask.get_orders(), OrderQueue)


def test_python_trade_blotter_snapshot_and_level_getters() -> None:
    incoming_id = uuid.uuid4()
    standing_id = uuid.uuid4()
    trade = Trade(incoming_id, standing_id, 25, Decimal("10.5"))
    order = bid("MSFT", 10.5, 50)
    blotter = TradeBlotter(order, [trade])
    level = SnapshotLevel(Decimal("10.5"), 25)
    snapshot = Snapshot(bids=[level], spread=Decimal("1"), midpoint=Decimal("10"))

    assert trade.get_incoming_order_id() == incoming_id
    assert trade.get_standing_order_id() == standing_id
    assert trade.get_fill_quantity() == 25
    assert trade.get_fill_price() == Decimal("10.5")
    assert blotter.get_order() is order
    assert blotter.get_trades() == [trade]
    assert blotter.get_total_cost() == 262.5
    assert blotter.get_average_price() == 10.5
    assert snapshot.get_bids() == [level]
    assert snapshot.get_asks() == []
    assert snapshot.get_spread() == Decimal("1")
    assert snapshot.get_midpoint() == Decimal("10")
    assert snapshot.get_bid_vwap() is None
    assert snapshot.get_ask_vwap() is None
    assert level.get_price() == Decimal("10.5")
    assert level.get_quantity() == 25


def test_python_book_matching_fifo_cancel_and_inspection_surface() -> None:
    book = Book()
    first = bid("AAPL", 100.0, 30)
    second = bid("AAPL", 100.0, 30)

    blotters = book.match([first, second])
    assert len(blotters) == 2
    assert book.get_order(first.id) is first
    assert book.get_order(uuid.uuid4()) is None

    level = book.get_level("AAPL", Side.BID, Decimal("100"))
    assert level is not None
    assert len(level.orders) == 2
    assert book.get_order_map() is book.order_map
    assert book.get_levels() is book.levels
    assert book.get_level_map() is book.level_map

    book.cancel(second)
    fill = book.match(ask("AAPL", 100.0, 50))
    assert len(fill.trades) == 1
    assert fill.trades[0].standing_order_id == first.id
    assert fill.trades[0].fill_quantity == 30
    assert fill.order.quantity == 20
    assert fill.order.status == OrderStatus.PARTIAL_FILL

    with pytest.raises(KeyError):
        book.cancel(second)


def test_python_book_rejects_invalid_match_input() -> None:
    with pytest.raises(ValueError, match="Invalid input type"):
        Book().match(cast(Any, ("not", "an", "order")))


def test_python_book_sweeps_levels_stops_at_limit_and_snapshots_remainder() -> None:
    book = Book()
    book.match([ask("AAPL", 10.0, 10), ask("AAPL", 11.0, 10), ask("AAPL", 12.0, 10)])

    blotter = book.match(bid("AAPL", 11.0, 25))

    assert [trade.fill_price for trade in blotter.trades] == [Decimal("10"), Decimal("11")]
    assert sum(trade.fill_quantity for trade in blotter.trades) == 20
    assert blotter.order.quantity == 5
    assert blotter.total_cost == 210.0
    assert blotter.average_price == 10.5

    snapshot = book.snapshot("AAPL")
    assert snapshot is not None
    assert snapshot.bids == [SnapshotLevel(Decimal("11"), 5)]
    assert snapshot.asks == [SnapshotLevel(Decimal("12"), 10)]
    assert snapshot.spread == Decimal("1")
    assert snapshot.midpoint == Decimal("11.5")
    assert snapshot.bid_vwap == Decimal("11")
    assert snapshot.ask_vwap == Decimal("12")

    empty_depth = book.snapshot("AAPL", depth=-5)
    assert empty_depth is not None
    assert empty_depth.bids == []
    assert empty_depth.asks == []
    assert empty_depth.spread is None
    assert empty_depth.midpoint is None
    assert empty_depth.bid_vwap is None
    assert empty_depth.ask_vwap is None
    assert book.snapshot("MSFT") is None


def test_python_book_cancel_reports_missing_price_level() -> None:
    book = Book()
    order = bid("AAPL", 100.0, 10)
    book.enqueue_order(order)
    book.level_map["AAPL"][Side.BID].pop(order.price)

    with pytest.raises(ValueError, match="Price Level"):
        book.cancel(order)


def test_python_book_fill_updates_orders_and_uses_side_price_logic() -> None:
    book = Book()
    incoming_bid = bid("AAPL", 12.0, 10)
    standing_ask = ask("AAPL", 10.0, 4)

    bid_trade = book.fill(incoming_bid, standing_ask)
    assert bid_trade.fill_quantity == 4
    assert bid_trade.fill_price == Decimal("10")
    assert incoming_bid.quantity == 6
    assert standing_ask.quantity == 0

    incoming_ask = ask("AAPL", 10.0, 8)
    standing_bid = bid("AAPL", 12.0, 3)
    ask_trade = book.fill(incoming_ask, standing_bid)
    assert ask_trade.fill_quantity == 3
    assert ask_trade.fill_price == Decimal("12")


def test_python_book_parquet_entry_points_use_reader_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"side": "ask", "symbol": "AAPL", "price": 10.0, "quantity": 5},
        {"side": "bid", "symbol": "AAPL", "price": 10.0, "quantity": 3},
    ]
    monkeypatch.setattr(book_module, "_read_parquet_rows", lambda path: rows)

    replay_book = Book()
    blotters = replay_book.replay_parquet("events.parquet")
    assert len(blotters) == 2
    assert len(blotters[1].trades) == 1
    replay_snapshot = replay_book.snapshot("AAPL")
    assert replay_snapshot is not None
    assert replay_snapshot.asks[0].quantity == 2

    ingest_book = Book()
    assert ingest_book.ingest_parquet("snapshot.parquet") == 2
    assert len(ingest_book.order_map) == 2

    loaded_book = Book.from_parquet("snapshot.parquet")
    assert len(loaded_book.order_map) == 2


def test_python_book_replay_parquet_rejects_non_blotter_match_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [{"side": "bid", "symbol": "AAPL", "price": 10.0, "quantity": 1}]
    monkeypatch.setattr(book_module, "_read_parquet_rows", lambda path: rows)

    with pytest.raises(TypeError, match="Expected TradeBlotter"):
        bad_book = Book()
        monkeypatch.setattr(bad_book, "match", lambda orders: [])
        bad_book.replay_parquet("events.parquet")


class _FakeTable:
    def __init__(self, column_names: list[str], rows: list[dict[str, object]]) -> None:
        self.column_names = column_names
        self._rows = rows

    def to_pylist(self) -> list[dict[str, object]]:
        return self._rows


def test_read_parquet_rows_uses_pyarrow_table(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"side": "bid", "symbol": "AAPL", "price": 100.0, "quantity": 1}]
    fake_parquet = types.ModuleType("pyarrow.parquet")
    cast(Any, fake_parquet).read_table = lambda path: _FakeTable(
        ["side", "symbol", "price", "quantity"], rows
    )
    fake_pyarrow = types.ModuleType("pyarrow")
    cast(Any, fake_pyarrow).__path__ = []
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", fake_parquet)

    assert _read_parquet_rows("orders.parquet") == rows


def test_read_parquet_rows_reports_missing_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_parquet = types.ModuleType("pyarrow.parquet")
    cast(Any, fake_parquet).read_table = lambda path: _FakeTable(["side", "symbol"], [])
    fake_pyarrow = types.ModuleType("pyarrow")
    cast(Any, fake_pyarrow).__path__ = []
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", fake_parquet)

    with pytest.raises(ValueError, match="missing \\[price, quantity\\]"):
        _read_parquet_rows("orders.parquet")


def test_read_parquet_rows_reports_missing_pyarrow(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = cast(Any, builtins.__import__)

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pyarrow.parquet":
            raise ImportError("blocked for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="pyarrow is required"):
        _read_parquet_rows("orders.parquet")


def test_order_from_parquet_row_accepts_string_price_and_integer_float_quantity() -> None:
    order = Book._order_from_parquet_row(
        {"side": "BID", "symbol": "AAPL", "price": "100.25", "quantity": 5.0},
        row_idx=7,
    )

    assert order.side == Side.BID
    assert order.symbol == "AAPL"
    assert order.price == Decimal("100.25")
    assert order.quantity == 5


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({}, "side"),
        ({"side": "buy", "symbol": "AAPL", "price": 1, "quantity": 1}, "Invalid side"),
        ({"side": "bid", "price": 1, "quantity": 1}, "symbol"),
        ({"side": "bid", "symbol": "", "price": 1, "quantity": 1}, "Symbol cannot be empty"),
        ({"side": "bid", "symbol": "AAPL", "quantity": 1}, "price"),
        ({"side": "bid", "symbol": "AAPL", "price": object(), "quantity": 1}, "Invalid price"),
        ({"side": "bid", "symbol": "AAPL", "price": "nan?", "quantity": 1}, "Invalid price"),
        ({"side": "bid", "symbol": "AAPL", "price": 1}, "quantity"),
        ({"side": "bid", "symbol": "AAPL", "price": 1, "quantity": True}, "Invalid quantity"),
        ({"side": "bid", "symbol": "AAPL", "price": 1, "quantity": 1.5}, "Invalid quantity"),
        (
            {"side": "bid", "symbol": "AAPL", "price": 1, "quantity": object()},
            "Invalid quantity",
        ),
        ({"side": "bid", "symbol": "AAPL", "price": 1, "quantity": "many"}, "Invalid quantity"),
        ({"side": "bid", "symbol": "AAPL", "price": 1, "quantity": 0}, "greater than zero"),
    ],
)
def test_order_from_parquet_row_rejects_bad_rows(
    row: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Book._order_from_parquet_row(row, row_idx=3)


def test_python_vwap_returns_none_for_empty_or_zero_quantity_levels() -> None:
    assert Book._compute_vwap([]) is None
    assert Book._compute_vwap([SnapshotLevel(Decimal("10"), 0)]) is None
