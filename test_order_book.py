from order_book import Book, Order, Side
from decimal import Decimal


def test_simple_order_flow():
    book = Book()
    book.process_order(Order(3.5, 70, "IBM", Side.SELL))
    book.process_order(Order(3.6, 70, "IBM", Side.SELL))
    transaction_summary = book.process_order(Order(54.3, 140, "IBM", Side.BUY))
    assert len(transaction_summary.transactions) == 2
    assert transaction_summary.average_price == Decimal("3.55")
    book.process_order(Order(341.24, 70, "IBM", Side.BUY))
    assert book.levels["IBM"][Side.BUY][Decimal("341.24")]


# print(book.process_sell(Order(37.54, 30)))
# print(book.process_sell(Order(37.54, 30)))
# print(book.process_sell(Order(48.50, 30)))
# print(book.process_sell(Order(35.50, 30)))


# print(book.process_buy(buy_order=Order(34, 70)))
# while book.buys:
#     print(heappop(book.buys))
# print('sells')
# while book.sells:
#     print(heappop(book.sells))
