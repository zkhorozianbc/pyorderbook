# PyOrderBook
[![Project CI](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml/badge.svg?refresh=1)](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyorderbook)
[![License](https://img.shields.io/github/license/zkhorozianbc/pyorderbook.svg)](https://github.com/zkhorozianbc/pyorderbook/blob/main/LICENSE)

A Python Limit Order Book written in Rust.

## Installation

```sh
pip install pyorderbook
```

Requires Python 3.11+. Pre-built wheels available for Linux, macOS, and Windows.

## Quick Start

```python
from pyorderbook import Book, bid, ask

book = Book()

# Place standing orders
book.match(ask("AAPL", 150.00, 100))
book.match(ask("AAPL", 151.00, 50))

# Incoming bid sweeps through the best asks
blotter = book.match(bid("AAPL", 155.00, 120))

blotter.trades          # list of executed Trade objects
blotter.total_cost      # total fill cost
blotter.average_price   # average fill price
blotter.order.status    # FILLED / PARTIAL_FILL / QUEUED
```

## Matching Engine

Price-time priority with FIFO ordering within each level. Supports partial fills, multi-symbol isolation, and batch processing.

```python
# Batch matching
blotters = book.match([bid("AAPL", 150.00, 10), bid("GOOG", 100.00, 20)])

# Cancel a standing order
order = bid("AAPL", 140.00, 500)
book.match(order)
book.cancel(order)
```

## L2 Snapshots

Get a structured market data view with spread, midpoint, and VWAP.

```python
snap = book.snapshot("AAPL", depth=5)

snap.bids              # list[SnapshotLevel] — best (highest) first
snap.asks              # list[SnapshotLevel] — best (lowest) first
snap.spread            # Decimal | None
snap.midpoint          # Decimal | None
snap.bid_vwap          # Decimal | None
snap.ask_vwap          # Decimal | None

snap.bids[0].price     # Decimal
snap.bids[0].quantity  # int (aggregated across all orders at that level)
```

## Replay from Parquet

Load historical order data and replay it through the matching engine.

```python
import pyarrow.parquet as pq
from pyorderbook import Book, bid, ask

table = pq.read_table("orders.parquet")  # columns: side, symbol, price, quantity
book = Book()

for i in range(len(table)):
    side = table.column("side")[i].as_py()
    order_fn = bid if side == "bid" else ask
    order = order_fn(
        table.column("symbol")[i].as_py(),
        table.column("price")[i].as_py(),
        table.column("quantity")[i].as_py(),
    )
    blotter = book.match(order)

# Inspect final book state
snap = book.snapshot("AAPL", depth=10)
```

See [`examples/replay/`](examples/replay/) for a complete example with sample data.

## API Reference

| Function / Method | Description |
|---|---|
| `bid(symbol, price, qty)` | Create a buy order |
| `ask(symbol, price, qty)` | Create a sell order |
| `Book.match(order_or_list)` | Match against the book. Returns `TradeBlotter` or `list[TradeBlotter]` |
| `Book.cancel(order)` | Cancel a standing order |
| `Book.snapshot(symbol, depth=5)` | L2 depth snapshot with spread, midpoint, VWAP |
| `Book.get_order(order_id)` | Look up an order by UUID |
| `Book.get_level(symbol, side, price)` | Get the price level at a given price |
| `Book.order_map` | All standing orders as `dict[UUID, Order]` |
| `Book.levels` | Price levels by symbol and side |

## Examples

| Example | Description |
|---|---|
| [`examples/basic/`](examples/basic/) | Order matching, partial fills, cancellation, FIFO |
| [`examples/snapshots/`](examples/snapshots/) | L2 depth views, spread, midpoint, VWAP, aggregation |
| [`examples/replay/`](examples/replay/) | Load orders from Parquet, replay through the book, snapshot over time |

## Design

- **Price-time priority** — best price first, FIFO within each level
- **Decimal precision** — prices use `decimal.Decimal`, no floating-point errors
- **Multi-symbol** — single `Book` handles any number of symbols independently
- **Rust core** — matching engine compiled to native code via PyO3
