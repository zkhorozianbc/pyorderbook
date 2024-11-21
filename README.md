### Limit Order Book written in pure Python 3.12

Handles buy and sell orders and order cancellation

### Design
- Orders are matched according to Price-Time priority
- Price Levels are stored in a double-ended queue (collections.deque), 1 queue for each symbol/side/price. The symbol/side/price grouping is represented as a nested default dict of default dicts, where the leaf dict has price (Decimal Type) keys and collections.deque values. New price levels are created when an unseen price is received for some symbol/side
- Unfilled orders are enqueued to the tail of the corresponding symbol/side/price queue
- Min/Max standing order prices for each symbol/side are stored and used to create smart iterator over prices (tick size = 1 cent) to find matching orders
- Matching Logic dequeues from the head of each matching price level, maintaining a FIFO ordering and encforcing the time priority
- Order Cancellation is done by locating orders with an order reference map, and marking cancelled orders with a cancelled flag. Cancelled orders are actually deleted (dequeued from price level) if/when they are encountered during the matching process of a subsequent order
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