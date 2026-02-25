# PyOrderBook
[![Project CI](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml/badge.svg?refresh=1)](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyorderbook)
[![License](https://img.shields.io/github/license/zkhorozianbc/pyorderbook.svg)](https://github.com/zkhorozianbc/pyorderbook/blob/main/LICENSE)

A limit order book and matching engine with a Rust backend. Falls back to a pure-Python implementation when the compiled extension is unavailable.

## Installation

```sh
pip install pyorderbook
```

## Usage

```python
from pyorderbook import Book, bid, ask

book = Book()

# Submit orders
book.match(bid("AAPL", 150.00, 100))
book.match(ask("AAPL", 150.50, 50))

# Incoming order matches against standing orders
blotter = book.match(ask("AAPL", 150.00, 30))

print(blotter.trades)        # list of Trade objects
print(blotter.total_cost)    # total fill cost
print(blotter.average_price) # average fill price
print(blotter.order.status)  # OrderStatus.FILLED / PARTIAL_FILL / QUEUED

# Cancel a standing order
order = book.get_order(order_id)
book.cancel(order)

# Batch matching
blotters = book.match([bid("AAPL", 150.00, 10), bid("AAPL", 149.50, 20)])
```

## Backend

Pre-built wheels include a compiled Rust extension (via [PyO3](https://pyo3.rs)) for Linux, macOS, and Windows. You can check which backend is active:

```python
import pyorderbook
print(pyorderbook._USING_RUST)  # True if Rust backend is loaded
```

If the Rust extension is not available (e.g. installing from sdist without a Rust toolchain), the pure-Python implementation is used automatically. The API is identical.

## Requirements

- Python 3.11+

## Design

- **Matching**: Price-time priority. Incoming orders match against the best available price, FIFO within each level.
- **Price levels**: Sorted arrays with best price at the back for O(1) access during matching. New levels inserted via binary search.
- **Order queues**: FIFO queues (VecDeque in Rust, dict in Python) at each price level.
- **Cancellation**: O(log n) lookup via order ID reference map + binary search.
- **Precision**: Prices stored as `decimal.Decimal` (Python) / `rust_decimal::Decimal` (Rust) to avoid floating-point errors.
