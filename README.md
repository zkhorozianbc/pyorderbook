### Limit Order Book in Python 3.12

Handles buy and sell orders and order cancellation

### Design
- Price Levels are stored in a default dictionary for each side (buy or sell), as a collections.deque
- Min/Max standing order prices for each side are stored and used to create smart iterator over ticks (tick size = 1 cent) to find matching order
- Order Cancellation is done by storing a map of order ids to order references, and marking cancelled orders as cancelled. During price matching for subsequent orders, if a cancelled order is encountered, it is dequeued from the price level
