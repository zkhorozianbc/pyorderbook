### Limit Order Book written in pure Python 3.12

- Order matching engine enforcing Price-Time priority
- Order cancellation

### Design
- Price Levels are stored in heap, as dataclasses with a price attribute and orders attribute. Orders are stores as a double-ended queue (collections.deque). New price levels are created when an unseen price is received for some symbol/side, and standing price levels are deleted when there are no more orders in the queue at that price level.
- Unfilled orders are enqueued to the tail of the corresponding symbol/side/price queue
- Matching Logic iterates through the price level heap (descending order for buys, ascending for sells) and dequeues from the head of each matching price level until the level or incoming order quantity is exhausted
- Order cancellation is done by locating orders with an order reference map, and marking cancelled orders with a cancelled flag. Cancelled orders are actually deleted (dequeued from price level) if/when they are encountered during the matching process of a subsequent order
- decimal.Decimal objects are used to store prices due to floating point arithmetic problems

### System Requirements
- uv
### Instructions to test
```
# create uv venv
uv init
# runs test_order_book.py
uv run pytest
# runs simulate_order_flow function in order_book.py
un run order_book.py
```