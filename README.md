# PyOrderBook

A fast limit order book and matching engine for Python, powered by a Rust backend via PyO3.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Why Use It

- Price-time priority matching with FIFO at each price level.
- Multi-symbol books from one `Book` instance.
- L2 snapshots with depth, spread, midpoint, and side VWAP.
- Decimal-backed prices to avoid binary floating-point surprises.
- Optional Parquet ingestion for replaying event streams or loading snapshots.
- Rust speed with a small, Pythonic API.

## Install

```sh
pip install pyorderbook

# or with uv
uv pip install pyorderbook
```

## 60-Second Example

```python
from pyorderbook import Book, ask, bid

book = Book()

# Resting sell-side liquidity.
book.match([
    ask("AAPL", 150.00, 100),
    ask("AAPL", 151.00, 50),
])

# Incoming buy order crosses the spread and partially consumes the second level.
blotter = book.match(bid("AAPL", 155.00, 120))

for trade in blotter.trades:
    print(f"filled {trade.fill_quantity} @ {trade.fill_price}")

print(f"status: {blotter.order.status}")
print(f"remaining quantity: {blotter.order.quantity}")
print(f"total cost: {blotter.total_cost}")

snapshot = book.snapshot("AAPL", depth=3)
print([(level.price, level.quantity) for level in snapshot.asks])
```

Output:

```text
filled 100 @ 150
filled 20 @ 151
status: filled
remaining quantity: 0
total cost: 18020.0
[(Decimal('151'), 30)]
```

## Mental Model

`Book` is the matching engine. Submit orders with `book.match(order)`.

`bid(...)` and `ask(...)` create buy and sell `Order` objects. If an incoming order crosses
resting liquidity, PyOrderBook fills the best available prices first and preserves FIFO order
within the same price.

`TradeBlotter` is returned from every match call. It contains the incoming order after matching,
the trades that occurred, `total_cost`, and `average_price`.

`Snapshot` is an aggregated L2 view of a symbol. Use `book.snapshot("AAPL", depth=5)` to inspect
the current top levels without mutating the book.

## Examples

Run these from the repository root:

| Example | What it shows | Command |
| --- | --- | --- |
| Basic matching | Crosses, partial fills, FIFO, cancel | `python examples/basic_matching.py` |
| L2 snapshots | Depth, spread, midpoint, VWAP | `python examples/l2_snapshot.py` |
| Parquet replay | Replay order events from Parquet | `python examples/parquet_replay.py` |
| Sample data | Regenerate the replay dataset | `python examples/generate_sample_parquet.py` |

Parquet examples require `pyarrow`.

## Development

```sh
uv sync
uv run maturin develop
uv run pytest
```

The package exposes the Rust backend when the extension is available and falls back to the Python
implementation when it is not.

## License

MIT
