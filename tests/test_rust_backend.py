"""Comprehensive test suite for the pyorderbook Rust backend.

Tests cover: Order/Side/OrderStatus types, bid/ask constructors, Book matching
engine (price-time priority, partial fills, multi-symbol, FIFO ordering),
cancel logic, get_order/get_level, TradeBlotter statistics, OrderQueue,
PriceLevel, edge cases, and error handling.

All tests are written to pass against both the Rust and Python backends.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

import pyorderbook
from pyorderbook import (
    Book,
    Order,
    OrderQueue,
    OrderStatus,
    PriceLevel,
    Side,
    Snapshot,
    SnapshotLevel,
    Trade,
    TradeBlotter,
    ask,
    bid,
)

# ── Backend detection ──────────────────────────────────────────────────────


class TestBackendDetection:
    def test_using_rust_flag_exists(self) -> None:
        assert hasattr(pyorderbook, "_USING_RUST")
        assert isinstance(pyorderbook._USING_RUST, bool)

    def test_rust_backend_is_active(self) -> None:
        assert pyorderbook._USING_RUST is True, "Rust backend should be active"

    def test_easter_egg(self) -> None:
        assert pyorderbook.easter_egg == "artificial lake"

    def test_all_exports(self) -> None:
        expected = {
            "Book",
            "bid",
            "ask",
            "Order",
            "OrderQueue",
            "OrderStatus",
            "Side",
            "PriceLevel",
            "Snapshot",
            "SnapshotLevel",
            "Trade",
            "TradeBlotter",
            "easter_egg",
            "_USING_RUST",
        }
        assert expected.issubset(set(pyorderbook.__all__))


# ── Side enum ──────────────────────────────────────────────────────────────


class TestSide:
    def test_bid_exists(self) -> None:
        assert Side.BID is not None

    def test_ask_exists(self) -> None:
        assert Side.ASK is not None

    def test_bid_other_is_ask(self) -> None:
        assert Side.BID.other == Side.ASK

    def test_ask_other_is_bid(self) -> None:
        assert Side.ASK.other == Side.BID

    def test_bid_equality(self) -> None:
        assert Side.BID == Side.BID
        assert Side.BID != Side.ASK

    def test_ask_equality(self) -> None:
        assert Side.ASK == Side.ASK
        assert Side.ASK != Side.BID


# ── OrderStatus enum ──────────────────────────────────────────────────────


class TestOrderStatus:
    def test_queued(self) -> None:
        assert OrderStatus.QUEUED is not None

    def test_partial_fill(self) -> None:
        assert OrderStatus.PARTIAL_FILL is not None

    def test_filled(self) -> None:
        assert OrderStatus.FILLED is not None

    def test_equality(self) -> None:
        assert OrderStatus.QUEUED == OrderStatus.QUEUED
        assert OrderStatus.QUEUED != OrderStatus.FILLED
        assert OrderStatus.PARTIAL_FILL != OrderStatus.FILLED


# ── Order construction ─────────────────────────────────────────────────────


class TestOrder:
    def test_bid_order_creation(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.side == Side.BID
        assert o.symbol == "AAPL"
        assert o.price == Decimal("150")
        assert o.quantity == 100
        assert o.original_quantity == 100
        assert isinstance(o.id, uuid.UUID)

    def test_ask_order_creation(self) -> None:
        o = ask("GOOG", 2800.50, 10)
        assert o.side == Side.ASK
        assert o.symbol == "GOOG"
        assert o.quantity == 10
        assert o.original_quantity == 10

    def test_order_via_constructor(self) -> None:
        o = Order(Side.BID, "TSLA", 200.0, 50)
        assert o.side == Side.BID
        assert o.symbol == "TSLA"
        assert o.quantity == 50

    def test_order_id_is_uuid(self) -> None:
        o = bid("X", 1.0, 1)
        assert isinstance(o.id, uuid.UUID)

    def test_order_price_is_decimal(self) -> None:
        o = bid("X", 1.5, 1)
        assert isinstance(o.price, Decimal)

    def test_order_unique_ids(self) -> None:
        o1 = bid("X", 1.0, 1)
        o2 = bid("X", 1.0, 1)
        assert o1.id != o2.id

    def test_order_status_queued(self) -> None:
        o = bid("X", 1.0, 10)
        assert o.status == OrderStatus.QUEUED

    def test_zero_quantity_raises(self) -> None:
        with pytest.raises((ValueError, Exception)):
            bid("X", 1.0, 0)

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises((ValueError, Exception)):
            ask("X", 1.0, -5)


# ── Basic matching ─────────────────────────────────────────────────────────


class TestBasicMatching:
    """Tests from the original test suite, plus extensions."""

    def test_bid_matches_standing_asks(self) -> None:
        book = Book()
        blotters = book.match([ask("IBM", 3.5, 70), ask("IBM", 3.6, 70), bid("IBM", 54.3, 140)])
        assert len(blotters[2].trades) == 2
        assert blotters[2].average_price == 3.55

    def test_ask_no_match_then_match(self) -> None:
        book = Book()
        blotters = book.match([bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70), ask("GOOG", 54.3, 140)])
        assert len(blotters[2].trades) == 0
        assert blotters[2].average_price == 0
        blotter = book.match(ask("GOOG", 3.1, 140))
        assert len(blotter.trades) == 2
        assert blotter.average_price == 3.55

    def test_cancel(self) -> None:
        book = Book()
        bid1, bid2 = bid("GOOG", 3.5, 70), bid("GOOG", 3.6, 70)
        book.match([bid1, bid2])
        book.cancel(bid1)
        blotter = book.match(ask("GOOG", 3.1, 140))
        assert len(blotter.trades) == 1
        assert blotter.average_price == 3.6

    def test_single_order_match_returns_blotter(self) -> None:
        book = Book()
        blotter = book.match(bid("AAPL", 100.0, 50))
        assert isinstance(blotter, TradeBlotter)
        assert len(blotter.trades) == 0

    def test_list_match_returns_list(self) -> None:
        book = Book()
        result = book.match([bid("AAPL", 100.0, 50)])
        assert isinstance(result, list)
        assert len(result) == 1


# ── Price-time priority (FIFO) ────────────────────────────────────────────


class TestPriceTimePriority:
    def test_fifo_at_same_price(self) -> None:
        """Orders at the same price should be filled in FIFO order."""
        book = Book()
        b1 = bid("X", 10.0, 50)
        b2 = bid("X", 10.0, 50)
        book.match([b1, b2])
        # Incoming ask should match b1 first (FIFO)
        blotter = book.match(ask("X", 10.0, 50))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].standing_order_id == b1.id

    def test_fifo_second_order_after_first_filled(self) -> None:
        """After first is filled, second should be next."""
        book = Book()
        b1 = bid("X", 10.0, 30)
        b2 = bid("X", 10.0, 30)
        book.match([b1, b2])
        blotter = book.match(ask("X", 10.0, 50))
        assert len(blotter.trades) == 2
        assert blotter.trades[0].standing_order_id == b1.id
        assert blotter.trades[0].fill_quantity == 30
        assert blotter.trades[1].standing_order_id == b2.id
        assert blotter.trades[1].fill_quantity == 20

    def test_price_priority_bid_side(self) -> None:
        """Higher-priced bids should be matched first for incoming asks."""
        book = Book()
        b_low = bid("X", 9.0, 100)
        b_high = bid("X", 11.0, 100)
        book.match([b_low, b_high])
        blotter = book.match(ask("X", 9.0, 50))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].standing_order_id == b_high.id

    def test_price_priority_ask_side(self) -> None:
        """Lower-priced asks should be matched first for incoming bids."""
        book = Book()
        a_high = ask("X", 11.0, 100)
        a_low = ask("X", 9.0, 100)
        book.match([a_high, a_low])
        blotter = book.match(bid("X", 11.0, 50))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].standing_order_id == a_low.id


# ── Partial fills ──────────────────────────────────────────────────────────


class TestPartialFills:
    def test_incoming_partial_fill(self) -> None:
        """Incoming order partially filled, remainder enqueued."""
        book = Book()
        book.match(ask("X", 10.0, 30))
        blotter = book.match(bid("X", 10.0, 100))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].fill_quantity == 30
        assert blotter.order.quantity == 70
        assert blotter.order.status == OrderStatus.PARTIAL_FILL

    def test_standing_partial_fill(self) -> None:
        """Standing order partially filled, remains in book."""
        book = Book()
        a1 = ask("X", 10.0, 100)
        book.match(a1)
        blotter = book.match(bid("X", 10.0, 30))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].fill_quantity == 30
        assert blotter.order.status == OrderStatus.FILLED
        # The remaining 70 should still be in the book
        blotter2 = book.match(bid("X", 10.0, 70))
        assert len(blotter2.trades) == 1
        assert blotter2.trades[0].fill_quantity == 70

    def test_full_fill_status(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.order.status == OrderStatus.FILLED
        assert blotter.order.quantity == 0

    def test_no_fill_status(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.order.status == OrderStatus.QUEUED
        assert blotter.order.quantity == 50


# ── Fill price logic ───────────────────────────────────────────────────────


class TestFillPrice:
    def test_bid_fill_price_is_min(self) -> None:
        """BID fill price = min(incoming, standing)."""
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 15.0, 50))
        assert blotter.trades[0].fill_price == Decimal("10")

    def test_ask_fill_price_is_max(self) -> None:
        """ASK fill price = max(incoming, standing)."""
        book = Book()
        book.match(bid("X", 15.0, 50))
        blotter = book.match(ask("X", 10.0, 50))
        assert blotter.trades[0].fill_price == Decimal("15")

    def test_same_price_fill(self) -> None:
        """When prices are equal, fill price equals that price."""
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.trades[0].fill_price == Decimal("10")


# ── TradeBlotter statistics ────────────────────────────────────────────────


class TestTradeBlotterStats:
    def test_total_cost_single_trade(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.total_cost == 500.0

    def test_total_cost_multiple_trades(self) -> None:
        book = Book()
        book.match([ask("X", 10.0, 30), ask("X", 12.0, 20)])
        blotter = book.match(bid("X", 15.0, 50))
        # 30 * 10 + 20 * 12 = 300 + 240 = 540
        assert blotter.total_cost == 540.0

    def test_average_price_multiple_trades(self) -> None:
        book = Book()
        book.match([ask("X", 10.0, 50), ask("X", 20.0, 50)])
        blotter = book.match(bid("X", 25.0, 100))
        # avg = (10 + 20) / 2 = 15
        assert blotter.average_price == 15.0

    def test_no_trades_stats(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.total_cost == 0.0
        assert blotter.average_price == 0.0

    def test_blotter_has_order(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.order is not None
        assert blotter.order.symbol == "X"


# ── Multi-symbol isolation ─────────────────────────────────────────────────


class TestMultiSymbol:
    def test_different_symbols_dont_match(self) -> None:
        book = Book()
        book.match(ask("AAPL", 150.0, 100))
        blotter = book.match(bid("GOOG", 200.0, 100))
        assert len(blotter.trades) == 0

    def test_same_symbol_matches(self) -> None:
        book = Book()
        book.match(ask("AAPL", 150.0, 100))
        blotter = book.match(bid("AAPL", 160.0, 100))
        assert len(blotter.trades) == 1

    def test_multiple_symbols_independent(self) -> None:
        book = Book()
        book.match([ask("AAPL", 150.0, 50), ask("GOOG", 100.0, 50)])
        b1 = book.match(bid("AAPL", 160.0, 50))
        b2 = book.match(bid("GOOG", 110.0, 50))
        assert len(b1.trades) == 1
        assert len(b2.trades) == 1


# ── Cancel ─────────────────────────────────────────────────────────────────


class TestCancel:
    def test_cancel_removes_from_book(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.match(b1)
        book.cancel(b1)
        blotter = book.match(ask("X", 10.0, 50))
        assert len(blotter.trades) == 0

    def test_cancel_nonexistent_order_raises(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        # Don't add to book — cancel should fail
        with pytest.raises(KeyError):
            book.cancel(b1)

    def test_cancel_already_cancelled_raises(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.match(b1)
        book.cancel(b1)
        with pytest.raises(KeyError):
            book.cancel(b1)

    def test_cancel_one_of_many_at_same_level(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        b2 = bid("X", 10.0, 50)
        b3 = bid("X", 10.0, 50)
        book.match([b1, b2, b3])
        book.cancel(b2)
        blotter = book.match(ask("X", 10.0, 100))
        assert len(blotter.trades) == 2
        trade_standing_ids = {t.standing_order_id for t in blotter.trades}
        assert b1.id in trade_standing_ids
        assert b3.id in trade_standing_ids
        assert b2.id not in trade_standing_ids

    def test_cancel_preserves_fifo(self) -> None:
        """Cancelling middle order should preserve FIFO of remaining."""
        book = Book()
        b1 = bid("X", 10.0, 30)
        b2 = bid("X", 10.0, 30)
        b3 = bid("X", 10.0, 30)
        book.match([b1, b2, b3])
        book.cancel(b2)
        blotter = book.match(ask("X", 10.0, 50))
        assert blotter.trades[0].standing_order_id == b1.id
        assert blotter.trades[1].standing_order_id == b3.id


# ── get_order ──────────────────────────────────────────────────────────────


class TestGetOrder:
    def test_get_standing_order(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.match(b1)
        found = book.get_order(b1.id)
        assert found is not None
        assert found.id == b1.id
        assert found.quantity == 50

    def test_get_nonexistent_order(self) -> None:
        book = Book()
        result = book.get_order(uuid.uuid4())
        assert result is None

    def test_get_filled_order_returns_none(self) -> None:
        """Fully filled orders are removed from the book."""
        book = Book()
        a1 = ask("X", 10.0, 50)
        book.match(a1)
        book.match(bid("X", 10.0, 50))
        result = book.get_order(a1.id)
        assert result is None


# ── get_level ──────────────────────────────────────────────────────────────


class TestGetLevel:
    def test_get_existing_level(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        level = book.get_level("X", Side.BID, Decimal("10"))
        assert level is not None
        assert level.side == Side.BID
        assert level.price == Decimal("10")

    def test_get_nonexistent_level(self) -> None:
        book = Book()
        level = book.get_level("X", Side.BID, Decimal("10"))
        assert level is None

    def test_level_has_correct_order_count(self) -> None:
        book = Book()
        book.match([bid("X", 10.0, 50), bid("X", 10.0, 30)])
        level = book.get_level("X", Side.BID, Decimal("10"))
        assert level is not None
        assert len(level.orders) == 2


# ── No-cross scenarios ─────────────────────────────────────────────────────


class TestNoCross:
    def test_bid_below_ask_no_match(self) -> None:
        book = Book()
        book.match(ask("X", 15.0, 100))
        blotter = book.match(bid("X", 10.0, 100))
        assert len(blotter.trades) == 0
        assert blotter.order.quantity == 100

    def test_ask_above_bid_no_match(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 100))
        blotter = book.match(ask("X", 15.0, 100))
        assert len(blotter.trades) == 0
        assert blotter.order.quantity == 100


# ── Edge cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_quantity_one(self) -> None:
        book = Book()
        book.match(ask("X", 5.0, 1))
        blotter = book.match(bid("X", 5.0, 1))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].fill_quantity == 1

    def test_many_orders_at_different_prices(self) -> None:
        book = Book()
        asks = [ask("X", float(i), 10) for i in range(1, 21)]
        book.match(asks)
        blotter = book.match(bid("X", 20.0, 200))
        assert len(blotter.trades) == 20
        assert blotter.order.quantity == 0

    def test_large_quantity(self) -> None:
        book = Book()
        book.match(ask("X", 1.0, 1_000_000))
        blotter = book.match(bid("X", 1.0, 1_000_000))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].fill_quantity == 1_000_000
        assert blotter.total_cost == 1_000_000.0

    def test_small_price(self) -> None:
        book = Book()
        book.match(ask("X", 0.01, 100))
        blotter = book.match(bid("X", 0.01, 100))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].fill_price == Decimal("0.01")
        assert blotter.total_cost == 1.0

    def test_sequential_matches_deplete_book(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 100))
        book.match(bid("X", 10.0, 60))
        blotter = book.match(bid("X", 10.0, 60))
        assert blotter.trades[0].fill_quantity == 40
        assert blotter.order.quantity == 20

    def test_empty_book_no_match(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 100.0, 50))
        assert len(blotter.trades) == 0

    def test_match_sweeps_multiple_levels(self) -> None:
        """A large bid should sweep through multiple ask price levels."""
        book = Book()
        book.match([ask("X", 10.0, 50), ask("X", 11.0, 50), ask("X", 12.0, 50)])
        blotter = book.match(bid("X", 12.0, 120))
        assert len(blotter.trades) == 3
        assert blotter.trades[0].fill_price == Decimal("10")
        assert blotter.trades[1].fill_price == Decimal("11")
        assert blotter.trades[2].fill_price == Decimal("12")
        assert blotter.order.quantity == 0

    def test_partial_sweep_stops_at_price(self) -> None:
        """Sweep should stop when standing price exceeds incoming limit."""
        book = Book()
        book.match([ask("X", 10.0, 50), ask("X", 11.0, 50), ask("X", 12.0, 50)])
        blotter = book.match(bid("X", 11.0, 200))
        assert len(blotter.trades) == 2
        total_filled = sum(t.fill_quantity for t in blotter.trades)
        assert total_filled == 100
        assert blotter.order.quantity == 100


# ── Trade object ───────────────────────────────────────────────────────────


class TestTrade:
    def test_trade_fields(self) -> None:
        book = Book()
        a1 = ask("X", 10.0, 50)
        book.match(a1)
        b1 = bid("X", 10.0, 50)
        blotter = book.match(b1)
        trade = blotter.trades[0]
        assert trade.incoming_order_id == b1.id
        assert trade.standing_order_id == a1.id
        assert trade.fill_quantity == 50
        assert trade.fill_price == Decimal("10")

    def test_trade_ids_are_uuids(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        trade = blotter.trades[0]
        assert isinstance(trade.incoming_order_id, uuid.UUID)
        assert isinstance(trade.standing_order_id, uuid.UUID)

    def test_trade_fill_price_is_decimal(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        assert isinstance(blotter.trades[0].fill_price, Decimal)


# ── OrderQueue ─────────────────────────────────────────────────────────────


class TestOrderQueue:
    def test_empty_queue(self) -> None:
        q = OrderQueue()
        assert len(q) == 0

    def test_append_and_peek(self) -> None:
        q = OrderQueue()
        o = bid("X", 1.0, 1)
        q.append_order(o)
        assert len(q) == 1
        p = q.peek()
        assert p.id == o.id

    def test_popleft(self) -> None:
        q = OrderQueue()
        q.append_order(bid("X", 1.0, 1))
        q.append_order(bid("X", 2.0, 1))
        assert len(q) == 2
        q.popleft()
        assert len(q) == 1

    def test_peek_empty_raises(self) -> None:
        q = OrderQueue()
        with pytest.raises(ValueError):
            q.peek()

    def test_popleft_empty_raises(self) -> None:
        q = OrderQueue()
        with pytest.raises(ValueError):
            q.popleft()

    def test_bool_empty(self) -> None:
        q = OrderQueue()
        assert not q

    def test_bool_nonempty(self) -> None:
        q = OrderQueue()
        q.append_order(bid("X", 1.0, 1))
        assert q


# ── Stress / batch ─────────────────────────────────────────────────────────


class TestStress:
    def test_batch_of_100_orders(self) -> None:
        book = Book()
        asks = [ask("X", float(10 + i * 0.01), 10) for i in range(50)]
        bids = [bid("X", float(10 + i * 0.01), 10) for i in range(50)]
        book.match(asks)
        blotters = book.match(bids)
        # Each bid should match the lowest available ask
        total_trades = sum(len(b.trades) for b in blotters)
        assert total_trades == 50

    def test_repeated_match_and_cancel(self) -> None:
        book = Book()
        for _ in range(50):
            b = bid("X", 10.0, 10)
            book.match(b)
            book.cancel(b)
        # Book should be empty
        blotter = book.match(ask("X", 10.0, 100))
        assert len(blotter.trades) == 0


# ── Side string equality (StrEnum parity) ─────────────────────────────────


class TestSideStringEquality:
    """Side.BID == 'bid' must be True, matching Python StrEnum behavior."""

    def test_bid_equals_string(self) -> None:
        assert Side.BID == "bid"

    def test_ask_equals_string(self) -> None:
        assert Side.ASK == "ask"

    def test_bid_not_equals_wrong_string(self) -> None:
        assert Side.BID != "ask"
        assert Side.BID != "BID"
        assert Side.BID != "something"

    def test_ask_not_equals_wrong_string(self) -> None:
        assert Side.ASK != "bid"
        assert Side.ASK != "ASK"

    def test_side_str_value(self) -> None:
        assert str(Side.BID) == "bid"
        assert str(Side.ASK) == "ask"

    def test_side_not_equals_int(self) -> None:
        assert Side.BID != 0
        assert Side.BID != 1

    def test_side_hash_matches_string_hash(self) -> None:
        """Side.BID and 'bid' should have same hash for dict key parity."""
        assert hash(Side.BID) == hash("bid")
        assert hash(Side.ASK) == hash("ask")

    def test_side_as_dict_key(self) -> None:
        d = {Side.BID: "bids", Side.ASK: "asks"}
        assert d[Side.BID] == "bids"
        assert d["bid"] == "bids"
        assert d["ask"] == "asks"


# ── Cancel error parity ───────────────────────────────────────────────────


class TestCancelErrorParity:
    def test_cancel_nonexistent_raises_key_error(self) -> None:
        """cancel should raise KeyError specifically."""
        book = Book()
        b1 = bid("X", 10.0, 50)
        with pytest.raises(KeyError):
            book.cancel(b1)

    def test_cancel_key_error_contains_uuid(self) -> None:
        """The KeyError argument should be the UUID object."""
        book = Book()
        b1 = bid("X", 10.0, 50)
        with pytest.raises(KeyError) as exc_info:
            book.cancel(b1)
        # The error arg should be a UUID, matching Python backend
        assert isinstance(exc_info.value.args[0], uuid.UUID)
        assert exc_info.value.args[0] == b1.id


# ── Book.fill() ───────────────────────────────────────────────────────────


class TestBookFill:
    def test_fill_exists(self) -> None:
        book = Book()
        assert hasattr(book, "fill")

    def test_fill_basic(self) -> None:
        book = Book()
        incoming = bid("X", 10.0, 50)
        standing = ask("X", 10.0, 30)
        trade = book.fill(incoming, standing)
        assert isinstance(trade, Trade)
        assert trade.fill_quantity == 30
        assert incoming.quantity == 20
        assert standing.quantity == 0

    def test_fill_price_logic(self) -> None:
        book = Book()
        incoming = bid("X", 15.0, 50)
        standing = ask("X", 10.0, 50)
        trade = book.fill(incoming, standing)
        # BID fill price = min(incoming, standing)
        assert trade.fill_price == Decimal("10")


# ── Book.enqueue_order() ──────────────────────────────────────────────────


class TestBookEnqueueOrder:
    def test_enqueue_order_exists(self) -> None:
        book = Book()
        assert hasattr(book, "enqueue_order")

    def test_enqueue_then_match(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.enqueue_order(b1)
        blotter = book.match(ask("X", 10.0, 50))
        assert len(blotter.trades) == 1
        assert blotter.trades[0].standing_order_id == b1.id

    def test_enqueue_then_get_order(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.enqueue_order(b1)
        found = book.get_order(b1.id)
        assert found is not None
        assert found.id == b1.id

    def test_enqueue_then_cancel(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.enqueue_order(b1)
        book.cancel(b1)
        blotter = book.match(ask("X", 10.0, 50))
        assert len(blotter.trades) == 0


# ── Book attribute access ─────────────────────────────────────────────────


class TestBookAttributes:
    def test_order_map_exists(self) -> None:
        book = Book()
        assert hasattr(book, "order_map")

    def test_order_map_empty(self) -> None:
        book = Book()
        assert len(book.order_map) == 0

    def test_order_map_has_standing_orders(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.match(b1)
        om = book.order_map
        assert len(om) == 1
        assert b1.id in om
        assert om[b1.id].quantity == 50

    def test_order_map_excludes_filled(self) -> None:
        book = Book()
        a1 = ask("X", 10.0, 50)
        book.match(a1)
        book.match(bid("X", 10.0, 50))
        assert len(book.order_map) == 0

    def test_levels_exists(self) -> None:
        book = Book()
        assert hasattr(book, "levels")

    def test_levels_structure(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        lvls = book.levels
        assert "X" in lvls
        assert Side.BID in lvls["X"]
        bid_levels = lvls["X"][Side.BID]
        assert len(bid_levels) == 1

    def test_level_map_exists(self) -> None:
        book = Book()
        assert hasattr(book, "level_map")

    def test_level_map_structure(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        lm = book.level_map
        assert "X" in lm
        assert Side.BID in lm["X"]
        assert Decimal("10") in lm["X"][Side.BID]
        level = lm["X"][Side.BID][Decimal("10")]
        assert isinstance(level, PriceLevel)
        assert len(level.orders) == 1


# ── OrderQueue dict-like operations ───────────────────────────────────────


class TestOrderQueueDictOps:
    def test_iteration(self) -> None:
        q = OrderQueue()
        o1 = bid("X", 1.0, 1)
        o2 = bid("X", 2.0, 1)
        q.append_order(o1)
        q.append_order(o2)
        ids = list(q)
        assert len(ids) == 2
        assert ids[0] == o1.id
        assert ids[1] == o2.id

    def test_contains(self) -> None:
        q = OrderQueue()
        o1 = bid("X", 1.0, 1)
        q.append_order(o1)
        assert o1.id in q
        assert uuid.uuid4() not in q

    def test_getitem(self) -> None:
        q = OrderQueue()
        o1 = bid("X", 1.0, 1)
        q.append_order(o1)
        fetched = q[o1.id]
        assert fetched.id == o1.id

    def test_getitem_missing_raises_key_error(self) -> None:
        q = OrderQueue()
        with pytest.raises(KeyError):
            q[uuid.uuid4()]

    def test_pop_by_uuid(self) -> None:
        q = OrderQueue()
        o1 = bid("X", 1.0, 1)
        o2 = bid("X", 2.0, 1)
        q.append_order(o1)
        q.append_order(o2)
        removed = q.pop(o1.id)
        assert removed.id == o1.id
        assert len(q) == 1
        # Remaining order is o2
        assert q.peek().id == o2.id

    def test_pop_missing_raises_key_error(self) -> None:
        q = OrderQueue()
        with pytest.raises(KeyError):
            q.pop(uuid.uuid4())


# ── PriceLevel.__lt__ (heapq compatibility) ───────────────────────────────


class TestPriceLevelComparison:
    def test_bid_lt_higher_price_is_first(self) -> None:
        """For BID heap, higher price should sort first (max-heap via __lt__)."""
        import heapq

        p1 = PriceLevel(Side.BID, Decimal("10"))
        p2 = PriceLevel(Side.BID, Decimal("20"))
        heap: list[PriceLevel] = []
        heapq.heappush(heap, p1)
        heapq.heappush(heap, p2)
        # Best bid (highest price) should be at top
        best = heapq.heappop(heap)
        assert best.price == Decimal("20")

    def test_ask_lt_lower_price_is_first(self) -> None:
        """For ASK heap, lower price should sort first (min-heap via __lt__)."""
        import heapq

        p1 = PriceLevel(Side.ASK, Decimal("20"))
        p2 = PriceLevel(Side.ASK, Decimal("10"))
        heap: list[PriceLevel] = []
        heapq.heappush(heap, p1)
        heapq.heappush(heap, p2)
        # Best ask (lowest price) should be at top
        best = heapq.heappop(heap)
        assert best.price == Decimal("10")

    def test_lt_exists(self) -> None:
        p1 = PriceLevel(Side.BID, Decimal("10"))
        p2 = PriceLevel(Side.BID, Decimal("20"))
        # Should not raise TypeError
        _ = p1 < p2


# ── Trade and TradeBlotter direct construction ────────────────────────────


class TestDirectConstruction:
    def test_trade_direct_construction(self) -> None:
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        t = Trade(id1, id2, 100, Decimal("10.5"))
        assert t.incoming_order_id == id1
        assert t.standing_order_id == id2
        assert t.fill_quantity == 100
        assert t.fill_price == Decimal("10.5")

    def test_trade_blotter_direct_construction(self) -> None:
        order = bid("X", 10.0, 100)
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        t = Trade(id1, id2, 50, Decimal("10"))
        blotter = TradeBlotter(order, [t])
        assert blotter.total_cost == 500.0
        assert blotter.average_price == 10.0
        assert len(blotter.trades) == 1


# ── Snapshot ──────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_unknown_symbol_returns_none(self) -> None:
        book = Book()
        assert book.snapshot("NOPE") is None

    def test_basic_bids_and_asks(self) -> None:
        book = Book()
        book.match([bid("AAPL", 99.0, 10), bid("AAPL", 100.0, 20)])
        book.match([ask("AAPL", 101.0, 30), ask("AAPL", 102.0, 40)])
        snap = book.snapshot("AAPL")
        assert snap is not None
        # Bids: best (highest) first
        assert len(snap.bids) == 2
        assert snap.bids[0].price == Decimal("100")
        assert snap.bids[0].quantity == 20
        assert snap.bids[1].price == Decimal("99")
        assert snap.bids[1].quantity == 10
        # Asks: best (lowest) first
        assert len(snap.asks) == 2
        assert snap.asks[0].price == Decimal("101")
        assert snap.asks[0].quantity == 30
        assert snap.asks[1].price == Decimal("102")
        assert snap.asks[1].quantity == 40

    def test_spread_and_midpoint(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        book.match(ask("X", 12.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.spread == Decimal("2")
        assert snap.midpoint == Decimal("11")

    def test_bid_vwap(self) -> None:
        book = Book()
        # 2 bid levels: 50@10 + 50@20 → vwap = (50*10 + 50*20) / (50+50) = 1500/100 = 15
        book.match([bid("X", 10.0, 50), bid("X", 20.0, 50)])
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.bid_vwap == Decimal("15")

    def test_ask_vwap(self) -> None:
        book = Book()
        # 2 ask levels: 50@100 + 150@200 → vwap = (50*100 + 150*200) / (50+150) = 35000/200
        book.match([ask("X", 100.0, 50), ask("X", 200.0, 150)])
        snap = book.snapshot("X")
        assert snap is not None
        expected = Decimal("35000") / Decimal("200")
        assert snap.ask_vwap == expected

    def test_depth_limiting(self) -> None:
        book = Book()
        for i in range(10):
            book.match(bid("X", float(90 + i), 10))
            book.match(ask("X", float(110 + i), 10))
        snap = book.snapshot("X", depth=3)
        assert snap is not None
        assert len(snap.bids) == 3
        assert len(snap.asks) == 3
        # Best bid is highest price
        assert snap.bids[0].price == Decimal("99")
        # Best ask is lowest price
        assert snap.asks[0].price == Decimal("110")

    def test_one_sided_book_bids_only(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert len(snap.bids) == 1
        assert len(snap.asks) == 0
        assert snap.spread is None
        assert snap.midpoint is None
        assert snap.bid_vwap == Decimal("10")
        assert snap.ask_vwap is None

    def test_one_sided_book_asks_only(self) -> None:
        book = Book()
        book.match(ask("X", 20.0, 100))
        snap = book.snapshot("X")
        assert snap is not None
        assert len(snap.bids) == 0
        assert len(snap.asks) == 1
        assert snap.spread is None
        assert snap.midpoint is None
        assert snap.bid_vwap is None
        assert snap.ask_vwap == Decimal("20")

    def test_quantity_aggregation_at_same_price(self) -> None:
        book = Book()
        book.match([bid("X", 10.0, 30), bid("X", 10.0, 70)])
        snap = book.snapshot("X")
        assert snap is not None
        assert len(snap.bids) == 1
        assert snap.bids[0].price == Decimal("10")
        assert snap.bids[0].quantity == 100

    def test_default_depth_is_5(self) -> None:
        book = Book()
        for i in range(10):
            book.match(bid("X", float(i + 1), 10))
        snap = book.snapshot("X")
        assert snap is not None
        assert len(snap.bids) == 5

    def test_depth_zero_returns_empty_snapshot(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        snap = book.snapshot("X", depth=0)
        assert snap is not None
        assert len(snap.bids) == 0
        assert len(snap.asks) == 0
        assert snap.spread is None
        assert snap.midpoint is None
        assert snap.bid_vwap is None
        assert snap.ask_vwap is None

    def test_depth_negative_clamped_to_zero(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        snap = book.snapshot("X", depth=-5)
        assert snap is not None
        assert len(snap.bids) == 0
        assert len(snap.asks) == 0

    def test_depth_exceeds_available_levels(self) -> None:
        book = Book()
        book.match([bid("X", 10.0, 50), bid("X", 11.0, 50)])
        snap = book.snapshot("X", depth=100)
        assert snap is not None
        assert len(snap.bids) == 2

    def test_empty_symbol_book(self) -> None:
        """A symbol that had orders but is now fully crossed returns empty snapshot."""
        book = Book()
        book.match(ask("X", 10.0, 50))
        book.match(bid("X", 10.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert len(snap.bids) == 0
        assert len(snap.asks) == 0
        assert snap.spread is None
        assert snap.midpoint is None

    def test_price_is_decimal(self) -> None:
        book = Book()
        book.match(bid("X", 10.5, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert isinstance(snap.bids[0].price, Decimal)

    def test_quantity_is_int(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert isinstance(snap.bids[0].quantity, int)

    def test_snapshot_types(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        book.match(ask("X", 12.0, 50))
        snap = book.snapshot("X")
        assert isinstance(snap, Snapshot)
        assert isinstance(snap.bids[0], SnapshotLevel)
        assert isinstance(snap.spread, Decimal)
        assert isinstance(snap.midpoint, Decimal)


# ── Getter methods ───────────────────────────────────────────────────────


class TestOrderGetters:
    def test_get_id(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_id() == o.id
        assert isinstance(o.get_id(), uuid.UUID)

    def test_get_price(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_price() == o.price
        assert isinstance(o.get_price(), Decimal)

    def test_get_quantity(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_quantity() == 100

    def test_get_symbol(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_symbol() == "AAPL"

    def test_get_side(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_side() == Side.BID
        o2 = ask("AAPL", 150.0, 100)
        assert o2.get_side() == Side.ASK

    def test_get_original_quantity(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_original_quantity() == 100

    def test_get_status_queued(self) -> None:
        o = bid("AAPL", 150.0, 100)
        assert o.get_status() == OrderStatus.QUEUED

    def test_get_status_after_partial_fill(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 30))
        blotter = book.match(bid("X", 10.0, 100))
        assert blotter.order.get_status() == OrderStatus.PARTIAL_FILL

    def test_get_status_after_full_fill(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.order.get_status() == OrderStatus.FILLED

    def test_getter_returns_callable(self) -> None:
        """get_* should be callable (method), not a bare value."""
        o = bid("X", 10.0, 50)
        assert callable(o.get_id)
        assert callable(o.get_price)
        assert callable(o.get_quantity)

    def test_invalid_getter_raises(self) -> None:
        o = bid("X", 10.0, 50)
        with pytest.raises(AttributeError):
            o.get_nonexistent()


class TestTradeGetters:
    def test_get_incoming_order_id(self) -> None:
        book = Book()
        a1 = ask("X", 10.0, 50)
        book.match(a1)
        b1 = bid("X", 10.0, 50)
        blotter = book.match(b1)
        trade = blotter.trades[0]
        assert trade.get_incoming_order_id() == trade.incoming_order_id
        assert isinstance(trade.get_incoming_order_id(), uuid.UUID)

    def test_get_standing_order_id(self) -> None:
        book = Book()
        a1 = ask("X", 10.0, 50)
        book.match(a1)
        b1 = bid("X", 10.0, 50)
        blotter = book.match(b1)
        trade = blotter.trades[0]
        assert trade.get_standing_order_id() == trade.standing_order_id
        assert trade.get_standing_order_id() == a1.id

    def test_get_fill_quantity(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 30))
        trade = blotter.trades[0]
        assert trade.get_fill_quantity() == 30

    def test_get_fill_price(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        trade = blotter.trades[0]
        assert trade.get_fill_price() == Decimal("10")
        assert isinstance(trade.get_fill_price(), Decimal)


class TestTradeBlotterGetters:
    def test_get_order(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        order = blotter.get_order()
        assert order is not None
        assert order.symbol == "X"
        assert order.quantity == 50

    def test_get_trades_empty(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.get_trades() == []

    def test_get_trades_with_fills(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        trades = blotter.get_trades()
        assert len(trades) == 1
        assert isinstance(trades[0], Trade)

    def test_get_total_cost(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.get_total_cost() == 500.0

    def test_get_average_price(self) -> None:
        book = Book()
        book.match([ask("X", 10.0, 50), ask("X", 20.0, 50)])
        blotter = book.match(bid("X", 25.0, 100))
        assert blotter.get_average_price() == 15.0

    def test_get_total_cost_no_trades(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.get_total_cost() == 0.0

    def test_get_average_price_no_trades(self) -> None:
        book = Book()
        blotter = book.match(bid("X", 10.0, 50))
        assert blotter.get_average_price() == 0.0


class TestSnapshotGetters:
    def test_get_bids(self) -> None:
        book = Book()
        book.match([bid("X", 10.0, 50), bid("X", 11.0, 30)])
        snap = book.snapshot("X")
        assert snap is not None
        bids = snap.get_bids()
        assert len(bids) == 2
        assert isinstance(bids[0], SnapshotLevel)
        assert bids[0].price == Decimal("11")

    def test_get_asks(self) -> None:
        book = Book()
        book.match([ask("X", 10.0, 50), ask("X", 11.0, 30)])
        snap = book.snapshot("X")
        assert snap is not None
        asks = snap.get_asks()
        assert len(asks) == 2
        assert asks[0].price == Decimal("10")

    def test_get_spread(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        book.match(ask("X", 12.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.get_spread() == Decimal("2")

    def test_get_spread_none(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.get_spread() is None

    def test_get_midpoint(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        book.match(ask("X", 12.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.get_midpoint() == Decimal("11")

    def test_get_bid_vwap(self) -> None:
        book = Book()
        book.match([bid("X", 10.0, 50), bid("X", 20.0, 50)])
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.get_bid_vwap() == Decimal("15")

    def test_get_ask_vwap(self) -> None:
        book = Book()
        book.match([ask("X", 10.0, 50), ask("X", 20.0, 50)])
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.get_ask_vwap() == Decimal("15")

    def test_get_bid_vwap_none(self) -> None:
        book = Book()
        book.match(ask("X", 10.0, 50))
        snap = book.snapshot("X")
        assert snap is not None
        assert snap.get_bid_vwap() is None


class TestSnapshotLevelGetters:
    def test_get_price(self) -> None:
        book = Book()
        book.match(bid("X", 10.5, 50))
        snap = book.snapshot("X")
        assert snap is not None
        lvl = snap.bids[0]
        assert lvl.get_price() == Decimal("10.5")
        assert isinstance(lvl.get_price(), Decimal)

    def test_get_quantity(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 75))
        snap = book.snapshot("X")
        assert snap is not None
        lvl = snap.bids[0]
        assert lvl.get_quantity() == 75
        assert isinstance(lvl.get_quantity(), int)


class TestPriceLevelGetters:
    def test_get_side(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        level = book.get_level("X", Side.BID, Decimal("10"))
        assert level is not None
        assert level.get_side() == Side.BID

    def test_get_price(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        level = book.get_level("X", Side.BID, Decimal("10"))
        assert level is not None
        assert level.get_price() == Decimal("10")
        assert isinstance(level.get_price(), Decimal)

    def test_get_orders(self) -> None:
        book = Book()
        book.match([bid("X", 10.0, 50), bid("X", 10.0, 30)])
        level = book.get_level("X", Side.BID, Decimal("10"))
        assert level is not None
        orders = level.get_orders()
        assert isinstance(orders, OrderQueue)
        assert len(orders) == 2


class TestBookGetters:
    def test_get_order_map_empty(self) -> None:
        book = Book()
        om = book.get_order_map()
        assert len(om) == 0

    def test_get_order_map_with_orders(self) -> None:
        book = Book()
        b1 = bid("X", 10.0, 50)
        book.match(b1)
        om = book.get_order_map()
        assert len(om) == 1
        assert b1.id in om

    def test_get_levels(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        levels = book.get_levels()
        assert isinstance(levels, dict)
        assert "X" in levels

    def test_get_level_map(self) -> None:
        book = Book()
        book.match(bid("X", 10.0, 50))
        lm = book.get_level_map()
        assert isinstance(lm, dict)
        assert "X" in lm
        assert Side.BID in lm["X"]
        assert Decimal("10") in lm["X"][Side.BID]
