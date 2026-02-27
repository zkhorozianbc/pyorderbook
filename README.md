# PyOrderBook

A high-performance limit order book and matching engine for Python, with a Rust backend via PyO3.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Installation

```sh
pip install pyorderbook
```

## Quick Start

```python
from pyorderbook import Book, ask, bid

book = Book()

# Post two asks (sell orders)
book.match(ask("AAPL", 150.00, 100))
book.match(ask("AAPL", 151.00, 50))

# Incoming bid sweeps both price levels
blotter = book.match(bid("AAPL", 155.00, 120))

for trade in blotter.trades:
    print(f"Filled {trade.fill_quantity} @ {trade.fill_price}")

print(f"Total cost:    ${blotter.total_cost}")
print(f"Average price: ${blotter.average_price}")
print(f"Order status:  {blotter.order.status}")  # partial_fill (30 remaining)
```

## Core API

### Orders

```python
from pyorderbook import bid, ask, Order, Side

order = bid("AAPL", 150.00, 100)   # Buy 100 AAPL @ $150
order = ask("GOOG", 280.50, 50)    # Sell 50 GOOG @ $280.50

# Or construct directly
order = Order(Side.BID, "AAPL", 150.00, 100)

order.id                # UUID
order.price             # Decimal
order.quantity           # int (remaining)
order.original_quantity  # int
order.symbol             # str
order.side               # Side.BID | Side.ASK
order.status             # queued | partial_fill | filled
```

### Matching

```python
book = Book()

# Single order — returns TradeBlotter
blotter = book.match(bid("AAPL", 150.00, 100))

# Batch — returns list[TradeBlotter]
blotters = book.match([
    ask("AAPL", 149.00, 50),
    ask("AAPL", 150.00, 50),
])
```

Price-time priority: orders match at the best available price, with earlier orders at the same price filling first.

### TradeBlotter

Every `match()` call returns a `TradeBlotter` with execution details:

| Field           | Type           | Description                  |
|-----------------|----------------|------------------------------|
| `order`         | `Order`        | The incoming order           |
| `trades`        | `list[Trade]`  | Fills that occurred          |
| `total_cost`    | `float`        | Sum of price * quantity      |
| `average_price` | `float`        | Mean fill price              |

Each `Trade` contains: `incoming_order_id`, `standing_order_id`, `fill_quantity`, `fill_price`.

### Cancel

```python
order = bid("AAPL", 150.00, 100)
book.match(order)
book.cancel(order)  # Raises KeyError if not found
```

### Book Inspection

```python
book.get_order(order.id)                         # Order | None
book.get_level("AAPL", Side.BID, Decimal("150")) # PriceLevel | None
book.order_map                                    # dict[UUID, Order]
```

## L2 Snapshots

```python
snap = book.snapshot("AAPL", depth=5)

snap.bids       # list[SnapshotLevel] — best bid first
snap.asks       # list[SnapshotLevel] — best ask first
snap.spread     # Decimal | None
snap.midpoint   # Decimal | None
snap.bid_vwap   # Decimal | None
snap.ask_vwap   # Decimal | None
```

Each `SnapshotLevel` has `.price` (Decimal) and `.quantity` (int, aggregated across orders at that level).

## Parquet Integration

Requires `pyarrow`. Expected schema: `side` (str), `symbol` (str), `price` (numeric), `quantity` (int).

### Replay Events

Process time-ordered events through the matching engine:

```python
blotters = book.replay_parquet("events.parquet")
```

### Load Snapshot

Load standing orders without matching:

```python
book = Book.from_parquet("snapshot.parquet")
# or
book.ingest_parquet("snapshot.parquet")
```

## Architecture

- **Matching engine**: price-time priority (FIFO at each price level)
- **Rust backend**: core data structures compiled via [PyO3](https://pyo3.rs) + [maturin](https://www.maturin.rs)
- **Multi-symbol**: single `Book` instance handles all symbols independently
- **Decimal prices**: all prices stored as `decimal.Decimal` to avoid floating-point errors

## License

MIT
