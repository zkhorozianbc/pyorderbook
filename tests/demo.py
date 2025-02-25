from orderbook import Book, ask, bid


def simulate_order_flow() -> None:
    """Toy order flow simulation. Feel free to experiment and set
    your desired log level at the top of the file!"""
    book = Book()
    book.match(ask("GOOG", 3.6, 70))
    book.match(ask("GOOG", 3.5, 70))
    blotter = book.match(bid("GOOG", 3.7, 70))
    print(blotter)


if __name__ == "__main__":
    simulate_order_flow()
