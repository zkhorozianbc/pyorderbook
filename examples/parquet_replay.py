"""Replay order events from Parquet and inspect the final book state."""

from pathlib import Path
from typing import Any

from pyorderbook import Book

PYARROW_HELP = "This example requires pyarrow. Install it with: pip install pyarrow"
SAMPLE_PATH = Path(__file__).with_name("sample_orders.parquet")
SYMBOLS = ("AAPL", "MSFT", "TSLA")


def top_level(levels: list[Any]) -> str:
    if not levels:
        return "-"
    level = levels[0]
    return f"{level.quantity}@{level.price}"


def main() -> None:
    if not SAMPLE_PATH.exists():
        raise SystemExit(
            "Missing examples/sample_orders.parquet. "
            "Run: python examples/generate_sample_parquet.py"
        )

    book = Book()
    try:
        blotters = book.replay_parquet(str(SAMPLE_PATH))
    except ImportError as exc:
        raise SystemExit(PYARROW_HELP) from exc

    total_trades = sum(len(blotter.trades) for blotter in blotters)
    total_quantity = sum(trade.fill_quantity for blotter in blotters for trade in blotter.trades)

    print(f"replayed orders: {len(blotters)}")
    print(f"trades:          {total_trades}")
    print(f"filled quantity: {total_quantity}")
    print(f"standing orders: {len(book.order_map)}")

    print()
    print("trade events")
    for blotter in blotters:
        if not blotter.trades:
            continue
        fills = ", ".join(f"{trade.fill_quantity}@{trade.fill_price}" for trade in blotter.trades)
        order = blotter.order
        print(f"  {order.symbol} {order.side} {order.original_quantity}@{order.price} -> {fills}")

    print()
    print("top of book")
    for symbol in SYMBOLS:
        snapshot = book.snapshot(symbol, depth=1)
        if snapshot is None:
            continue
        print(f"  {symbol}: bid {top_level(snapshot.bids)} | ask {top_level(snapshot.asks)}")


if __name__ == "__main__":
    main()
