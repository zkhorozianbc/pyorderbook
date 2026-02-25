"""Basic order matching — price-time priority, partial fills, cancellation."""

from pyorderbook import Book, Side, ask, bid

book = Book()

# Place some standing ask orders
a1 = ask("AAPL", 150.0, 100)
a2 = ask("AAPL", 151.0, 50)
a3 = ask("AAPL", 152.0, 200)
book.match([a1, a2, a3])
print("Standing asks placed at $150, $151, $152")

# Incoming bid sweeps through the best asks
blotter = book.match(bid("AAPL", 155.0, 120))
print(f"\nBid for 120 @ $155:")
print(f"  Trades: {len(blotter.trades)}")
for t in blotter.trades:
    print(f"    Filled {t.fill_quantity} @ ${t.fill_price}")
print(f"  Total cost: ${blotter.total_cost}")
print(f"  Avg price:  ${blotter.average_price}")
print(f"  Remaining:  {blotter.order.quantity} (status: {blotter.order.status})")

# Partial fill — bid doesn't fully consume the book
blotter2 = book.match(bid("AAPL", 151.5, 25))
print(f"\nBid for 25 @ $151.50:")
print(f"  Trades: {len(blotter2.trades)}")
for t in blotter2.trades:
    print(f"    Filled {t.fill_quantity} @ ${t.fill_price}")
print(f"  Remaining: {blotter2.order.quantity}")

# Cancel a standing order
b1 = bid("AAPL", 140.0, 500)
book.match(b1)
print(f"\nPlaced bid {b1.id} for 500 @ $140")
book.cancel(b1)
print(f"Cancelled bid {b1.id}")

# Verify it's gone
result = book.get_order(b1.id)
print(f"get_order after cancel: {result}")

# FIFO at same price level
b2 = bid("TSLA", 200.0, 50)
b3 = bid("TSLA", 200.0, 50)
book.match([b2, b3])
blotter3 = book.match(ask("TSLA", 200.0, 60))
print(f"\nFIFO test — two bids at $200, ask for 60:")
for t in blotter3.trades:
    standing = "b2" if t.standing_order_id == b2.id else "b3"
    print(f"  Matched {standing}: {t.fill_quantity} @ ${t.fill_price}")

# Multi-symbol isolation
book.match(ask("GOOG", 100.0, 50))
blotter4 = book.match(bid("MSFT", 200.0, 50))
print(f"\nGOOG ask vs MSFT bid: {len(blotter4.trades)} trades (symbols don't cross)")

# Show the order map
print(f"\nStanding orders in book: {len(book.order_map)}")
for uid, order in book.order_map.items():
    print(f"  {order.side} {order.symbol} {order.quantity}@{order.price}")
