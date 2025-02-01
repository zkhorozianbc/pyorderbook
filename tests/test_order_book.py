from decimal import Decimal

from orderbook.book import Book
from orderbook.book import Order
from orderbook.book import Side


def test_buy():
    book = Book()
    book.process_order(Order(3.5, 70, "IBM", Side.SELL))
    book.process_order(Order(3.6, 70, "IBM", Side.SELL))
    transaction_summary = book.process_order(Order(54.3, 140, "IBM", Side.BUY))
    assert len(transaction_summary.transactions) == 2
    assert transaction_summary.average_price == Decimal("3.55")


def test_sell():
    book = Book()
    book.process_order(Order(3.5, 70, "GOOG", Side.BUY))
    book.process_order(Order(3.6, 70, "GOOG", Side.BUY))
    transaction_summary = book.process_order(Order(54.3, 140, "GOOG", Side.SELL))
    assert len(transaction_summary.transactions) == 0
    assert transaction_summary.average_price is None
    transaction_summary = book.process_order(Order(3.1, 140, "GOOG", Side.SELL))
    assert len(transaction_summary.transactions) == 2
    assert transaction_summary.average_price == Decimal("3.55")


def test_cancel():
    book = Book()
    buy1 = Order(3.5, 70, "GOOG", Side.BUY)
    buy2 = Order(3.6, 70, "GOOG", Side.BUY)
    book.process_order(buy1)
    book.process_order(buy2)
    book.cancel_order(buy1.id)
    transaction_summary = book.process_order(Order(3.1, 140, "GOOG", Side.SELL))
    assert len(transaction_summary.transactions) == 1
    assert transaction_summary.average_price == Decimal("3.6")
