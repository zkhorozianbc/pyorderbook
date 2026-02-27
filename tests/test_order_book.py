from decimal import Decimal
from pathlib import Path

import pytest

from pyorderbook import Book, ask, bid


def _write_orders_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    pa = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    table = pa.table({
        "side": [str(row["side"]) for row in rows],
        "symbol": [str(row["symbol"]) for row in rows],
        "price": [float(row["price"]) for row in rows],
        "quantity": [int(row["quantity"]) for row in rows],
    })
    parquet.write_table(table, path)


def test_bid() -> None:
    book = Book()
    blotter = book.match([ask("IBM", 3.5, 70), ask("IBM", 3.6, 70), bid("IBM", 54.3, 140)])
    assert len(blotter[2].trades) == 2
    assert blotter[2].average_price == 3.55


def test_ask() -> None:
    book = Book()
    blotters = book.match([bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70), ask("GOOG", 54.3, 140)])
    assert len(blotters[2].trades) == 0
    assert blotters[2].average_price == 0
    blotter = book.match(ask("GOOG", 3.1, 140))
    assert len(blotter.trades) == 2
    assert blotter.average_price == 3.55


def test_cancel() -> None:
    book = Book()
    bid1, bid2 = bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70)
    book.match([bid1, bid2])
    book.cancel(bid1)
    blotter = book.match(ask("GOOG", 3.1, 140))
    assert len(blotter.trades) == 1
    assert blotter.average_price == 3.6


def test_snapshot() -> None:
    """Exercises snapshot on whichever backend is active."""
    book = Book()
    # Unknown symbol
    assert book.snapshot("NOPE") is None

    # Build a two-sided book
    book.match([bid("AAPL", 99.0, 10), bid("AAPL", 100.0, 20)])
    book.match([ask("AAPL", 101.0, 30), ask("AAPL", 102.0, 40)])

    snap = book.snapshot("AAPL")
    assert snap is not None

    # Bids: best (highest) first
    assert len(snap.bids) == 2
    assert snap.bids[0].price == Decimal("100")
    assert snap.bids[0].quantity == 20
    assert snap.bids[1].price == Decimal("99")
    assert snap.bids[1].quantity == 10

    # Asks: best (lowest) first
    assert len(snap.asks) == 2
    assert snap.asks[0].price == Decimal("101")
    assert snap.asks[0].quantity == 30
    assert snap.asks[1].price == Decimal("102")
    assert snap.asks[1].quantity == 40

    # Spread and midpoint
    assert snap.spread == Decimal("1")
    assert snap.midpoint == Decimal("100.5")

    # Depth limiting
    snap3 = book.snapshot("AAPL", depth=1)
    assert snap3 is not None
    assert len(snap3.bids) == 1
    assert len(snap3.asks) == 1

    # Quantity aggregation
    book2 = Book()
    book2.match([bid("X", 10.0, 30), bid("X", 10.0, 70)])
    snap2 = book2.snapshot("X")
    assert snap2 is not None
    assert len(snap2.bids) == 1
    assert snap2.bids[0].quantity == 100


def test_replay_parquet(tmp_path: Path) -> None:
    parquet_path = tmp_path / "orders.parquet"
    _write_orders_parquet(
        parquet_path,
        [
            {"side": "ask", "symbol": "X", "price": 10.0, "quantity": 40},
            {"side": "bid", "symbol": "X", "price": 10.0, "quantity": 30},
            {"side": "bid", "symbol": "X", "price": 10.0, "quantity": 20},
        ],
    )

    book = Book()
    blotters = book.replay_parquet(str(parquet_path))

    assert len(blotters) == 3
    assert sum(len(blotter.trades) for blotter in blotters) == 2
    snap = book.snapshot("X")
    assert snap is not None
    assert len(snap.bids) == 1
    assert snap.bids[0].quantity == 10
    assert len(snap.asks) == 0


def test_from_parquet_ingests_standing_orders(tmp_path: Path) -> None:
    parquet_path = tmp_path / "snapshot.parquet"
    _write_orders_parquet(
        parquet_path,
        [
            {"side": "bid", "symbol": "AAPL", "price": 99.0, "quantity": 10},
            {"side": "ask", "symbol": "AAPL", "price": 101.0, "quantity": 20},
        ],
    )

    book = Book.from_parquet(str(parquet_path))
    snap = book.snapshot("AAPL")

    assert len(book.order_map) == 2
    assert snap is not None
    assert snap.bids[0].price == Decimal("99")
    assert snap.bids[0].quantity == 10
    assert snap.asks[0].price == Decimal("101")
    assert snap.asks[0].quantity == 20


def test_replay_parquet_missing_columns_raises(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    parquet_path = tmp_path / "invalid.parquet"
    parquet.write_table(pa.table({"side": ["bid"], "symbol": ["X"]}), parquet_path)

    book = Book()
    with pytest.raises(ValueError, match="missing"):
        book.replay_parquet(str(parquet_path))
