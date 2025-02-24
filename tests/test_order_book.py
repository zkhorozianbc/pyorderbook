from decimal import Decimal

from orderbook import Book, bid, ask


def test_bid() -> None:
    book = Book()
    summaries = book.match([ask("IBM", 3.5, 70), ask("IBM", 3.6, 70), bid("IBM", 54.3, 140)])
    assert len(summaries[2].transactions) == 2
    assert summaries[2].average_price == 3.55


def test_ask() -> None:
    book = Book()
    summaries = book.match([bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70), ask("GOOG", 54.3, 140)])
    assert len(summaries[2].transactions) == 0
    assert summaries[2].average_price is None
    (summary,) = book.match(ask("GOOG", 3.1, 140))
    assert len(summary.transactions) == 2
    assert summary.average_price == 3.55


def test_cancel() -> None:
    book = Book()
    bid1, bid2 = bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70)
    book.match([bid1, bid2])
    book.cancel(bid1)
    (summary,) = book.match(ask("GOOG", 3.1, 140))
    assert len(summary.transactions) == 1
    assert summary.average_price == 3.6
