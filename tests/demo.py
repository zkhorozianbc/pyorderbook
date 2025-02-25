import pprint

from pyorderbook import Book, ask, bid


def simulate_order_flow() -> None:
    """Toy order flow simulation"""
    book = Book()
    pprint.pprint(book.match([ask("GOOG", 3.5, 25), ask("GOOG", 3.6, 75), bid("GOOG", 3.7, 100)]))


if __name__ == "__main__":
    simulate_order_flow()
