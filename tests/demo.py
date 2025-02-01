from decimal import Decimal

from orderbook import Book, Order, Side


def simulate_order_flow() -> None:
    """Toy order flow simulation. Feel free to experiment and set
    your desired log level at the top of the file!"""
    book = Book()
    book.process_order(Order(Decimal("3.6"), 70, "GOOG", Side.SELL))
    book.process_order(Order(Decimal("3.5"), 70, "GOOG", Side.SELL))
    book.process_order(Order(Decimal("3.7"), 150, "GOOG", Side.BUY))
    book.process_order(Order(Decimal("3.1"), 140, "GOOG", Side.SELL))
    book.process_order(Order(Decimal("3.6"), 70, "IBM", Side.BUY))
    book.process_order(Order(Decimal("54.3"), 10, "TSLA", Side.SELL))
    book.process_order(Order(Decimal("3.1"), 1430, "GOOG", Side.BUY))
    book.process_order(Order(Decimal("5.3"), 130, "TSLA", Side.BUY))


if __name__ == "__main__":
    simulate_order_flow()
