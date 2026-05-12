"""L2 snapshots: aggregated depth, spread, midpoint, and side VWAP."""

from pyorderbook import Book, ask, bid


def fmt(value: object) -> str:
    return "" if value is None else str(value)


def main() -> None:
    book = Book()

    book.match(
        [
            bid("AAPL", 100.00, 20),
            bid("AAPL", 100.00, 30),
            bid("AAPL", 99.50, 40),
            bid("AAPL", 99.00, 60),
            ask("AAPL", 101.00, 25),
            ask("AAPL", 101.00, 15),
            ask("AAPL", 101.50, 35),
            ask("AAPL", 102.00, 45),
        ]
    )

    snapshot = book.snapshot("AAPL", depth=3)
    if snapshot is None:
        raise RuntimeError("AAPL should have a snapshot")

    print("AAPL L2 snapshot, depth=3")
    print(f"{'bid qty':>8} {'bid':>8} | {'ask':<8} {'ask qty':<8}")
    print("-" * 39)

    rows = max(len(snapshot.bids), len(snapshot.asks))
    for index in range(rows):
        bid_level = snapshot.bids[index] if index < len(snapshot.bids) else None
        ask_level = snapshot.asks[index] if index < len(snapshot.asks) else None

        bid_qty = fmt(bid_level.quantity if bid_level else None)
        bid_price = fmt(bid_level.price if bid_level else None)
        ask_price = fmt(ask_level.price if ask_level else None)
        ask_qty = fmt(ask_level.quantity if ask_level else None)

        print(f"{bid_qty:>8} {bid_price:>8} | {ask_price:<8} {ask_qty:<8}")

    print()
    print(f"spread:   {snapshot.spread}")
    print(f"midpoint: {snapshot.midpoint}")
    print(f"bid vwap: {snapshot.bid_vwap}")
    print(f"ask vwap: {snapshot.ask_vwap}")

    top = book.snapshot("AAPL", depth=1)
    if top is None:
        raise RuntimeError("AAPL should have top-of-book data")

    print()
    print("top of book")
    print(f"  best bid: {top.bids[0].quantity} @ {top.bids[0].price}")
    print(f"  best ask: {top.asks[0].quantity} @ {top.asks[0].price}")


if __name__ == "__main__":
    main()
