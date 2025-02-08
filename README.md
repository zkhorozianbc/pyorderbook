# Order Book

Order Book is a pure Python implementation of an order matching engine that enforces Price-Time priority. It provides order matching, order cancellation and detailed transaction summaries.

## Features

- **Order Matching Engine**
- **Order Cancellation**
- **Detailed Transaction Summaries**

## Usage

```python
from decimal import Decimal
from orderbook import Book, Order, Side

# Create a new order book
book = Book()

# Process some orders
book.process_order(Order(Decimal("3.5"), 70, "IBM", Side.SELL))
book.process_order(Order(Decimal("3.6"), 70, "IBM", Side.SELL))
transaction_summary = book.process_order(Order(Decimal("54.3"), 140, "IBM", Side.BUY))

# Print transaction summary
print(transaction_summary)
```

## Installation

To install the package, use:

```sh
# pip
pip install orderbook
# uv
uv pip install orderbook
# or 
uv add orderbook
```

## System Requirements
- Python 3.12+


## Design

- **Price Levels**: Stored in a heap of dataclasses, each with a price attribute and orders attribute. Orders are stored in a dictionary within each price level. New price levels are created when an unseen price is received for a symbol/side, and standing price levels are deleted when there are no more orders in the queue at that price level.
- **Order Queueing**: Unfilled orders are enqueued to the tail of the corresponding symbol/side/price queue, maintaining insertion order.
- **Matching Logic**: Iterates through the price level heap (descending order for buys, ascending for sells) and dequeues from the head of each matching price level until the level or incoming order quantity is exhausted.
- **Order Cancellation**: Uses a reference map from order ID to its encompassing price level. The order is popped from the price level and the reference map.
- **Precision**: Uses `decimal.Decimal` objects to store prices to avoid floating point arithmetic problems.
