# PyOrderBook
[![Project CI](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml/badge.svg?refresh=1)](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyorderbook)
[![License](https://img.shields.io/github/license/zkhorozianbc/pyorderbook.svg)](https://github.com/zkhorozianbc/pyorderbook/blob/main/LICENSE)

A fast limit order book and matching engine. Compiled Rust core with Python bindings.

## Installation

```sh
pip install pyorderbook
```

Requires Python 3.11+. Pre-built wheels available for Linux, macOS, and Windows.

## Usage

```python
from pyorderbook import Book, bid, ask

book = Book()

# Submit orders — returns a TradeBlotter with fill results
book.match(bid("AAPL", 150.00, 100))
book.match(ask("AAPL", 150.50, 50))

# Incoming order matches against standing orders
blotter = book.match(ask("AAPL", 150.00, 30))

blotter.trades          # list of Trade objects
blotter.total_cost      # total fill cost
blotter.average_price   # average fill price
blotter.order.status    # OrderStatus.FILLED / PARTIAL_FILL / QUEUED

# Cancel a standing order
order = book.get_order(order_id)
book.cancel(order)

# Batch matching
blotters = book.match([bid("AAPL", 150.00, 10), bid("AAPL", 149.50, 20)])
```

## API

| Function / Method | Description |
|---|---|
| `bid(symbol, price, quantity)` | Create a buy order |
| `ask(symbol, price, quantity)` | Create a sell order |
| `Book.match(order_or_list)` | Match order(s) against the book. Returns `TradeBlotter` or `list[TradeBlotter]` |
| `Book.cancel(order)` | Cancel a standing order |
| `Book.get_order(order_id)` | Look up an order by UUID |
| `Book.get_level(symbol, side, price)` | Get the price level at a given price |
| `Book.order_map` | All standing orders as `dict[UUID, Order]` |
| `Book.levels` | Price levels by symbol and side |

## Design

- **Price-time priority**: best price first, FIFO within each level
- **Decimal precision**: prices use `decimal.Decimal` — no floating-point errors
- **Multi-symbol**: single `Book` instance handles any number of symbols independently
