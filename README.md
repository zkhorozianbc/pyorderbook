# PyOrderBook
[![Project CI](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml/badge.svg?refresh=1)](https://github.com/zkhorozianbc/pyorderbook/actions/workflows/project-ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pyorderbook.svg)](https://pypi.org/project/pyorderbook/)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyorderbook)
[![License](https://img.shields.io/github/license/zkhorozianbc/pyorderbook.svg)](https://github.com/zkhorozianbc/pyorderbook/blob/main/LICENSE)

PyOrderBook is a pure Python implementation of a limit order book and matching engine.

## Features

- **Order Matching Engine**
- **Order Cancellation**
- **Detailed Trade Blotter**

## Usage

```python
from pyorderbook import Book, bid, ask

# Create a new order book
book = Book()

# Process some orders
book.match(bid("IBM", 3.5, 20))
book.match(ask("IBM", 3.6, 10))
trade_blotter = book.match(ask("IBM", 3.5, 10))

# Print trade blotter
print(trade_blotter)
```

## Installation

To install the package, use:

```sh
# pip
pip3 install pyorderbook
# uv
uv pip install pyorderbook
# or 
uv add pyorderbook
```

## System Requirements
- Python 3.11+


## Design

- **Price Levels**: Stored in a heap of dataclasses, each with a price attribute and orders attribute. Orders are stored in a dictionary within each price level. New price levels are created when an unseen price is received for a symbol/side, and standing price levels are deleted when there are no more orders in the queue at that price level.
- **Order Queueing**: Unfilled orders are enqueued to the tail of the corresponding symbol/side/price queue, maintaining insertion order.
- **Matching Logic**: Iterates through the price level heap (descending order for bids, ascending for asks) and dequeues from the head of each matching price level until the level or incoming order quantity is exhausted.
- **Order Cancellation**: Uses a reference map from order ID to its encompassing price level. The order is popped from the price level and the reference map.
- **Precision**: Uses `decimal.Decimal` objects to store prices to avoid floating point arithmetic problems.
