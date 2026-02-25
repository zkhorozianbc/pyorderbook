from decimal import Decimal

from pyorderbook import Book, ask, bid


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
