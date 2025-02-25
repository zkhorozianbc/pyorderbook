# Order Book

Order Book is a pure Python implementation of an order matching engine that enforces Price-Time priority. It provides order matching, order cancellation and detailed trade blotter.

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
pip install pyorderbook
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
