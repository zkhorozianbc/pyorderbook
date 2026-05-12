"""Core matching behavior: crossing orders, partial fills, FIFO, and cancel."""

from typing import Any

from pyorderbook import Book, ask, bid


def short_id(order_id: object) -> str:
    return str(order_id)[:8]


def print_trades(label: str, blotter: Any) -> None:
    print(label)
    for trade in blotter.trades:
        print(f"  fill {trade.fill_quantity:>3} @ {trade.fill_price}")
    print(f"  status={blotter.order.status} remaining={blotter.order.quantity}")


def main() -> None:
    book = Book()

    first_ask = ask("AAPL", 150.00, 100)
    second_ask = ask("AAPL", 151.00, 50)
    book.match([first_ask, second_ask])

    sweep = book.match(bid("AAPL", 151.00, 130))
    print_trades("AAPL bid 130 @ 151.00", sweep)

    remaining_ask = book.get_order(second_ask.id)
    if remaining_ask is not None:
        print(f"  resting ask left at 151.00: {remaining_ask.quantity}")

    print()

    partial_book = Book()
    resting_bid = bid("MSFT", 200.00, 75)
    partial_book.match(resting_bid)

    partial = partial_book.match(ask("MSFT", 199.00, 100))
    print_trades("MSFT ask 100 @ 199.00", partial)
    print("  unfilled remainder rests as a new ask")

    print()

    fifo_book = Book()
    first_bid = bid("TSLA", 250.00, 50)
    second_bid = bid("TSLA", 250.00, 50)
    fifo_book.match([first_bid, second_bid])

    fifo = fifo_book.match(ask("TSLA", 250.00, 70))
    print("TSLA FIFO at 250.00")
    for trade in fifo.trades:
        standing = "first" if trade.standing_order_id == first_bid.id else "second"
        print(
            f"  {standing:<6} resting bid {short_id(trade.standing_order_id)} "
            f"filled {trade.fill_quantity}"
        )

    print()

    cancel_order = bid("AAPL", 140.00, 10)
    book.match(cancel_order)
    print(f"cancel queued bid {short_id(cancel_order.id)}")
    book.cancel(cancel_order)
    print(f"  get_order after cancel: {book.get_order(cancel_order.id)}")


if __name__ == "__main__":
    main()
