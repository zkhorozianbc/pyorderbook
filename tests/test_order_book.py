from decimal import Decimal

from orderbook import Book, Order, Side


def test_buy() -> None:
    book = Book()
    book.process_order(Order(Decimal("3.5"), 70, "IBM", Side.SELL))
    book.process_order(Order(Decimal("3.6"), 70, "IBM", Side.SELL))
    transaction_summary = book.process_order(Order(Decimal("54.3"), 140, "IBM", Side.BUY))
    assert len(transaction_summary.transactions) == 2
    assert transaction_summary.average_price == Decimal("3.55")


def test_sell() -> None:
    book = Book()
    book.process_order(Order(Decimal("3.5"), 70, "GOOG", Side.BUY))
    book.process_order(Order(Decimal("3.6"), 70, "GOOG", Side.BUY))
    transaction_summary = book.process_order(Order(Decimal("54.3"), 140, "GOOG", Side.SELL))
    assert len(transaction_summary.transactions) == 0
    assert transaction_summary.average_price is None
    transaction_summary = book.process_order(Order(Decimal("3.1"), 140, "GOOG", Side.SELL))
    assert len(transaction_summary.transactions) == 2
    assert transaction_summary.average_price == Decimal("3.55")


def test_cancel() -> None:
    book = Book()
    buy1 = Order(Decimal("3.5"), 70, "GOOG", Side.BUY)
    buy2 = Order(Decimal("3.6"), 70, "GOOG", Side.BUY)
    book.process_order(buy1)
    book.process_order(buy2)
    book.cancel_order(buy1.id)
    transaction_summary = book.process_order(Order(Decimal(3.1), 140, "GOOG", Side.SELL))
    assert len(transaction_summary.transactions) == 1
    assert transaction_summary.average_price == Decimal("3.6")
