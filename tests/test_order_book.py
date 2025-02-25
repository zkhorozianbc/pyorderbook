from orderbook import Book, ask, bid


def test_bid() -> None:
    book = Book()
    blotter = book.match([ask("IBM", 3.5, 70), ask("IBM", 3.6, 70), bid("IBM", 54.3, 140)])
    assert len(blotter[2].trades) == 2
    assert blotter[2].average_price == 3.55


def test_ask() -> None:
    book = Book()
    blotters = book.match([bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70), ask("GOOG", 54.3, 140)])
    assert len(blotters[2].trades) == 0
    assert blotters[2].average_price is None
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
