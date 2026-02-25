"""Replay historical orders from Parquet and take L2 snapshots.

Reads sample_orders.parquet, feeds each order through the matching engine,
and prints snapshots at intervals to show the book evolving over time.

Usage:
    python examples/replay/replay_and_snapshot.py
"""

from pathlib import Path

import pyarrow.parquet as pq

from pyorderbook import Book, Side, ask, bid

# Load order data from parquet
parquet_path = Path(__file__).parent / "sample_orders.parquet"
table = pq.read_table(parquet_path)
print(f"Loaded {len(table)} orders from {parquet_path.name}")
print(f"Columns: {table.column_names}\n")

book = Book()
total_trades = 0

# Replay orders through the matching engine
for i in range(len(table)):
    row_side = table.column("side")[i].as_py()
    row_symbol = table.column("symbol")[i].as_py()
    row_price = table.column("price")[i].as_py()
    row_qty = table.column("quantity")[i].as_py()

    if row_side == "bid":
        order = bid(row_symbol, row_price, row_qty)
    else:
        order = ask(row_symbol, row_price, row_qty)

    blotter = book.match(order)
    total_trades += len(blotter.trades)

    # Print snapshot every 50 orders
    if (i + 1) % 50 == 0:
        print(f"--- After {i + 1} orders ({total_trades} trades so far) ---\n")

        for symbol in ["AAPL", "GOOG", "TSLA"]:
            snap = book.snapshot(symbol, depth=3)
            if snap is None:
                continue

            print(f"  {symbol}:")
            if snap.bids:
                best_bid = f"${snap.bids[0].price}"
                bid_depth = sum(l.quantity for l in snap.bids)
            else:
                best_bid = "---"
                bid_depth = 0

            if snap.asks:
                best_ask = f"${snap.asks[0].price}"
                ask_depth = sum(l.quantity for l in snap.asks)
            else:
                best_ask = "---"
                ask_depth = 0

            spread_str = f"${snap.spread}" if snap.spread is not None else "N/A"
            mid_str = f"${snap.midpoint}" if snap.midpoint is not None else "N/A"

            print(f"    Best bid: {best_bid}  |  Best ask: {best_ask}")
            print(f"    Spread: {spread_str}  |  Midpoint: {mid_str}")
            print(f"    Bid depth: {bid_depth}  |  Ask depth: {ask_depth}")

            if snap.bid_vwap is not None:
                print(f"    Bid VWAP: ${snap.bid_vwap:.4f}", end="")
            if snap.ask_vwap is not None:
                print(f"  |  Ask VWAP: ${snap.ask_vwap:.4f}", end="")
            print("\n")

# Final summary
print(f"=== Replay Complete ===")
print(f"Orders processed: {len(table)}")
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
