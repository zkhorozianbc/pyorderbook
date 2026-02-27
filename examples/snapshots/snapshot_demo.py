"""L2 depth snapshots — spread, midpoint, VWAP, depth limiting."""

from pyorderbook import Book, ask, bid

book = Book()

# Build a two-sided order book for AAPL
bids = [
    bid("AAPL", 149.50, 200),
    bid("AAPL", 149.75, 150),
    bid("AAPL", 150.00, 300),
    bid("AAPL", 150.25, 100),
    bid("AAPL", 150.50, 250),
    bid("AAPL", 150.75, 175),
]
asks = [
    ask("AAPL", 151.00, 200),
    ask("AAPL", 151.25, 125),
    ask("AAPL", 151.50, 350),
    ask("AAPL", 151.75, 100),
    ask("AAPL", 152.00, 400),
    ask("AAPL", 152.25, 225),
]
book.match(bids + asks)

# Default snapshot (depth=5)
snap = book.snapshot("AAPL")
print("=== AAPL L2 Snapshot (depth=5) ===\n")
print(f"{'Bid Qty':>10}  {'Bid Price':>10}  |  {'Ask Price':<10}  {'Ask Qty':<10}")
print("-" * 56)
max_rows = max(len(snap.bids), len(snap.asks))
for i in range(max_rows):
    bid_qty = str(snap.bids[i].quantity) if i < len(snap.bids) else ""
    bid_px = str(snap.bids[i].price) if i < len(snap.bids) else ""
    ask_px = str(snap.asks[i].price) if i < len(snap.asks) else ""
    ask_qty = str(snap.asks[i].quantity) if i < len(snap.asks) else ""
    print(f"{bid_qty:>10}  {bid_px:>10}  |  {ask_px:<10}  {ask_qty:<10}")

print(f"\nSpread:    {snap.spread}")
print(f"Midpoint:  {snap.midpoint}")
print(f"Bid VWAP:  {snap.bid_vwap}")
print(f"Ask VWAP:  {snap.ask_vwap}")

# Narrow depth
snap3 = book.snapshot("AAPL", depth=3)
print("\n=== Top 3 levels ===")
print(f"Bids: {[(str(lvl.price), lvl.quantity) for lvl in snap3.bids]}")
print(f"Asks: {[(str(lvl.price), lvl.quantity) for lvl in snap3.asks]}")

# Depth=1 for top-of-book
snap1 = book.snapshot("AAPL", depth=1)
print("\n=== Top of Book ===")
print(f"Best bid: {snap1.bids[0].quantity} @ ${snap1.bids[0].price}")
print(f"Best ask: {snap1.asks[0].quantity} @ ${snap1.asks[0].price}")
print(f"Spread:   ${snap1.spread}")

# Unknown symbol returns None
result = book.snapshot("NOPE")
print(f"\nSnapshot for unknown symbol: {result}")

# One-sided book
book2 = Book()
book2.match(bid("XYZ", 50.0, 100))
snap_one = book2.snapshot("XYZ")
print("\n=== One-sided book (bids only) ===")
print(f"Bids:     {len(snap_one.bids)}")
print(f"Asks:     {len(snap_one.asks)}")
print(f"Spread:   {snap_one.spread}")
print(f"Midpoint: {snap_one.midpoint}")
print(f"Bid VWAP: {snap_one.bid_vwap}")
print(f"Ask VWAP: {snap_one.ask_vwap}")

# Quantity aggregation — multiple orders at same price
book3 = Book()
book3.match([bid("AGG", 25.0, 100), bid("AGG", 25.0, 200), bid("AGG", 25.0, 300)])
snap_agg = book3.snapshot("AGG")
print("\n=== Aggregation (3 orders @ $25) ===")
print(f"Levels: {len(snap_agg.bids)}")
print(f"Total qty: {snap_agg.bids[0].quantity} (100+200+300)")
