### Limit Order Book written in pure Python 3.12

- Order matching engine enforcing Price-Time priority
- Order cancellation

### Design
- Price Levels are stored in a heap of dataclasses each with a price attribute and orders attribute. Orders are stored in a doubly linked list in each price level. New price levels are created when an unseen price is received for some symbol/side, and standing price levels are deleted when there are no more orders in the queue at that price level.
- Unfilled orders are enqueued to the tail of the corresponding symbol/side/price queue
- Matching Logic iterates through the price level heap (descending order for buys, ascending for sells) and dequeues from the head of each matching price level until the level or incoming order quantity is exhausted
- Order cancellation is done by storing a reference map from order id to it's encompassing price level. The order is popped from the price level and the reference map. Orders of a price level are stored as a doubly linked list which supports node deletion in constant time (implemented in linked_list.py)
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

### Further Improvements
- Implement order queues as doubly linked lists to support O(1) cancellation. Currently, the cancel_order functionality leaves cancelled orders in the book until they're encountered during order matching, at which point they're removed.