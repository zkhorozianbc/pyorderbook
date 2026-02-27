"""Replay historical orders from Parquet and take L2 snapshots.

Reads sample_orders.parquet and replays it directly through Book.replay_parquet().

Usage:
    python examples/replay/replay_and_snapshot.py
"""

from pathlib import Path

from pyorderbook import Book

# Load order data from parquet
parquet_path = Path(__file__).parent / "sample_orders.parquet"
book = Book()
blotters = book.replay_parquet(str(parquet_path))
total_trades = sum(len(blotter.trades) for blotter in blotters)

# Final summary
print("=== Replay Complete ===")
print(f"Orders processed: {len(blotters)}")
print(f"Total trades:     {total_trades}")
print(f"Standing orders:  {len(book.order_map)}\n")

# Final detailed snapshot for each symbol
for symbol in ["AAPL", "GOOG", "TSLA"]:
    snap = book.snapshot(symbol, depth=5)
    if snap is None:
        continue

    print(f"=== {symbol} Final L2 (depth=5) ===")
    print(f"{'Bid Qty':>10}  {'Bid':>10}  |  {'Ask':<10}  {'Ask Qty':<10}")
    print("-" * 50)
    max_rows = max(len(snap.bids), len(snap.asks))
    for j in range(max_rows):
        bq = str(snap.bids[j].quantity) if j < len(snap.bids) else ""
        bp = str(snap.bids[j].price) if j < len(snap.bids) else ""
        ap = str(snap.asks[j].price) if j < len(snap.asks) else ""
        aq = str(snap.asks[j].quantity) if j < len(snap.asks) else ""
        print(f"{bq:>10}  {bp:>10}  |  {ap:<10}  {aq:<10}")
    print()
