use pyo3::prelude::*;
use pyo3::types::PyDict;
use rust_decimal::Decimal;
use std::collections::HashMap;
use std::collections::VecDeque;
use uuid::Uuid;

use crate::order::{decimal_to_py, uuid_to_py, Order, Side};
use crate::trade::{PriceLevel, Trade, TradeBlotter};

// ---------------------------------------------------------------------------
// Internal data structures (not exposed to Python)
// ---------------------------------------------------------------------------

/// A single order entry stored inside the matching engine.
#[derive(Clone, Debug)]
struct OrderEntry {
    id: Uuid,
    price: Decimal,
    quantity: i64,
    original_quantity: i64,
    symbol: String,
    side: Side,
}

impl OrderEntry {
    fn from_order(order: &Order) -> Self {
        OrderEntry {
            id: order.id,
            price: order.price,
            quantity: order.quantity,
            original_quantity: order.original_quantity,
            symbol: order.symbol.clone(),
            side: order.side,
        }
    }

    fn to_order(&self) -> Order {
        Order {
            id: self.id,
            price: self.price,
            quantity: self.quantity,
            original_quantity: self.original_quantity,
            symbol: self.symbol.clone(),
            side: self.side,
        }
    }
}

/// A price level with a FIFO queue of orders.
#[derive(Clone, Debug)]
struct PriceLevelInner {
    price: Decimal,
    orders: VecDeque<OrderEntry>,
}

/// One side of the book (bids or asks) for a single symbol.
/// - Bids: sorted ascending by price -> best bid (highest) at the **back**
/// - Asks: sorted descending by price -> best ask (lowest) at the **back**
#[derive(Clone, Debug, Default)]
struct OneSide {
    levels: Vec<PriceLevelInner>,
}

impl OneSide {
    /// Find the index of a price level via binary search.
    /// `ascending` = true for bids, false for asks.
    fn find_level(&self, price: Decimal, ascending: bool) -> Result<usize, usize> {
        self.levels.binary_search_by(|lvl| {
            if ascending {
                lvl.price.cmp(&price)
            } else {
                price.cmp(&lvl.price)
            }
        })
    }

    /// Insert an order into the correct price level, creating it if needed.
    fn insert(&mut self, entry: OrderEntry, ascending: bool) {
        match self.find_level(entry.price, ascending) {
            Ok(idx) => {
                self.levels[idx].orders.push_back(entry);
            }
            Err(idx) => {
                let mut orders = VecDeque::new();
                let price = entry.price;
                orders.push_back(entry);
                self.levels.insert(idx, PriceLevelInner { price, orders });
            }
        }
    }

    /// Remove a specific order by id from the level at the given price.
    fn remove_order(&mut self, price: Decimal, order_id: Uuid, ascending: bool) -> bool {
        if let Ok(idx) = self.find_level(price, ascending) {
            let level = &mut self.levels[idx];
            if let Some(pos) = level.orders.iter().position(|o| o.id == order_id) {
                level.orders.remove(pos);
                if level.orders.is_empty() {
                    self.levels.remove(idx);
                }
                return true;
            }
        }
        false
    }
}

/// Per-symbol book state.
#[derive(Clone, Debug, Default)]
struct SymbolBook {
    bids: OneSide,
    asks: OneSide,
}

// ---------------------------------------------------------------------------
// Internal matching result — no Python types needed
// ---------------------------------------------------------------------------

struct MatchResult {
    trades: Vec<Trade>,
    remaining_qty: i64,
}

// ---------------------------------------------------------------------------
// Python-visible Book class
// ---------------------------------------------------------------------------

/// Main order book and matching engine.
#[pyclass]
pub struct Book {
    symbols: HashMap<String, SymbolBook>,
    /// Maps order_id -> (symbol, side, price) for fast lookup/cancel.
    order_map: HashMap<Uuid, (String, Side, Decimal)>,
}

#[pymethods]
impl Book {
    #[new]
    fn new() -> Self {
        Book {
            symbols: HashMap::new(),
            order_map: HashMap::new(),
        }
    }

    /// Match incoming order(s). Accepts a single Order or a list of Orders.
    /// Returns a TradeBlotter or list of TradeBlotters respectively.
    #[pyo3(name = "match")]
    fn match_orders(
        &mut self,
        orders: &Bound<'_, pyo3::PyAny>,
        py: Python<'_>,
    ) -> PyResult<PyObject> {
        if let Ok(list) = orders.downcast::<pyo3::types::PyList>() {
            let mut blotters: Vec<Py<TradeBlotter>> = Vec::new();
            for item in list.iter() {
                let order: PyRef<Order> = item.extract()?;
                let blotter = self.match_single(&order)?;
                blotters.push(Py::new(py, blotter)?);
            }
            Ok(pyo3::types::PyList::new(py, blotters)?.into())
        } else {
            let order: PyRef<Order> = orders.extract()?;
            let blotter = self.match_single(&order)?;
            Ok(Py::new(py, blotter)?.into_any().into())
        }
    }

    /// Cancel a standing order.
    ///
    /// Raises KeyError (with the UUID) if the order is not in the book,
    /// matching the Python backend behavior.
    fn cancel(&mut self, order: PyRef<Order>, py: Python<'_>) -> PyResult<()> {
        let order_id = order.id;
        let (symbol, side, price) = match self.order_map.remove(&order_id) {
            Some(v) => v,
            None => {
                // Match Python: raises KeyError with the UUID object as argument
                let py_uuid = uuid_to_py(py, order_id)?;
                return Err(pyo3::exceptions::PyKeyError::new_err(py_uuid));
            }
        };

        let sym_book = self.symbols.get_mut(&symbol).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Price Level {}:{}:{} doesn't exist!",
                symbol, side, price
            ))
        })?;

        let ascending = matches!(side, Side::BID);
        let one_side = if ascending {
            &mut sym_book.bids
        } else {
            &mut sym_book.asks
        };

        if !one_side.remove_order(price, order_id, ascending) {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Price Level {}:{}:{} doesn't exist!",
                symbol, side, price
            )));
        }
        Ok(())
    }

    /// Execute order fill between incoming and standing orders.
    /// Updates both orders' quantities and returns a Trade.
    fn fill(
        &self,
        incoming_order: &mut Order,
        standing_order: &mut Order,
        py: Python<'_>,
    ) -> PyResult<Py<Trade>> {
        let matched_quantity = incoming_order.quantity.min(standing_order.quantity);
        standing_order.quantity -= matched_quantity;
        incoming_order.quantity -= matched_quantity;
        let fill_price =
            incoming_order.side.calc_fill_price(incoming_order.price, standing_order.price);
        let trade = Trade::from_rust(
            incoming_order.id,
            standing_order.id,
            matched_quantity,
            fill_price,
        );
        Py::new(py, trade)
    }

    /// Add order to book directly (enqueue without matching).
    fn enqueue_order(&mut self, order: PyRef<Order>) {
        let entry = OrderEntry::from_order(&order);
        let ascending = matches!(order.side, Side::BID);
        let sym_book = self.symbols.entry(order.symbol.clone()).or_default();
        let one_side = if ascending {
            &mut sym_book.bids
        } else {
            &mut sym_book.asks
        };
        one_side.insert(entry, ascending);
        self.order_map.insert(
            order.id,
            (order.symbol.clone(), order.side, order.price),
        );
    }

    /// Return an Order by its id, or None.
    fn get_order(
        &self,
        order_id: &Bound<'_, pyo3::PyAny>,
        py: Python<'_>,
    ) -> PyResult<Option<Py<Order>>> {
        let id_str: String = order_id.str()?.extract()?;
        let uid = Uuid::parse_str(&id_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid order_id: {}", e))
        })?;

        let Some((symbol, side, price)) = self.order_map.get(&uid) else {
            return Ok(None);
        };
        let sym_book = match self.symbols.get(symbol) {
            Some(b) => b,
            None => return Ok(None),
        };
        let ascending = matches!(side, Side::BID);
        let one_side = if ascending {
            &sym_book.bids
        } else {
            &sym_book.asks
        };
        if let Ok(idx) = one_side.find_level(*price, ascending) {
            for entry in &one_side.levels[idx].orders {
                if entry.id == uid {
                    return Ok(Some(Py::new(py, entry.to_order())?));
                }
            }
        }
        Ok(None)
    }

    /// Return a PriceLevel snapshot for a given symbol/side/price, or None.
    ///
    /// Note: returns a snapshot (copy) of the current state. Modifications to
    /// the returned PriceLevel do not affect the book. This matches the Rust
    /// backend's value semantics. The Python backend returns a live reference.
    fn get_level(
        &self,
        symbol: &str,
        side: Side,
        price: &Bound<'_, pyo3::PyAny>,
        py: Python<'_>,
    ) -> PyResult<Option<Py<PriceLevel>>> {
        let price_str: String = price.str()?.extract()?;
        let decimal_price = Decimal::from_str_exact(&price_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid price: {}", e))
        })?;

        let sym_book = match self.symbols.get(symbol) {
            Some(b) => b,
            None => return Ok(None),
        };
        let ascending = matches!(side, Side::BID);
        let one_side = if ascending {
            &sym_book.bids
        } else {
            &sym_book.asks
        };

        if let Ok(idx) = one_side.find_level(decimal_price, ascending) {
            let level = &one_side.levels[idx];
            let mut pl = PriceLevel::from_rust(side, level.price);
            for entry in &level.orders {
                pl.orders.append_order(entry.to_order());
            }
            return Ok(Some(Py::new(py, pl)?));
        }
        Ok(None)
    }

    /// Expose order_map as dict[UUID, Order] for API parity.
    #[getter]
    fn order_map(&self, py: Python<'_>) -> PyResult<PyObject> {
        let dict = PyDict::new(py);
        for (uid, (symbol, side, price)) in &self.order_map {
            // Look up the actual order entry to get current quantity
            let sym_book = match self.symbols.get(symbol) {
                Some(b) => b,
                None => continue,
            };
            let ascending = matches!(side, Side::BID);
            let one_side = if ascending {
                &sym_book.bids
            } else {
                &sym_book.asks
            };
            if let Ok(idx) = one_side.find_level(*price, ascending) {
                for entry in &one_side.levels[idx].orders {
                    if entry.id == *uid {
                        let py_uuid = uuid_to_py(py, *uid)?;
                        let py_order = Py::new(py, entry.to_order())?;
                        dict.set_item(py_uuid, py_order)?;
                        break;
                    }
                }
            }
        }
        Ok(dict.into())
    }

    /// Expose levels as defaultdict-like structure for API parity.
    /// Returns dict[symbol, dict[Side, list[PriceLevel]]].
    #[getter]
    fn levels(&self, py: Python<'_>) -> PyResult<PyObject> {
        let outer = PyDict::new(py);
        for (symbol, sym_book) in &self.symbols {
            let inner = PyDict::new(py);
            // Build bid levels list (in heap order for parity)
            let bid_list = pyo3::types::PyList::empty(py);
            for lvl in &sym_book.bids.levels {
                let mut pl = PriceLevel::from_rust(Side::BID, lvl.price);
                for entry in &lvl.orders {
                    pl.orders.append_order(entry.to_order());
                }
                bid_list.append(Py::new(py, pl)?)?;
            }
            let ask_list = pyo3::types::PyList::empty(py);
            for lvl in &sym_book.asks.levels {
                let mut pl = PriceLevel::from_rust(Side::ASK, lvl.price);
                for entry in &lvl.orders {
                    pl.orders.append_order(entry.to_order());
                }
                ask_list.append(Py::new(py, pl)?)?;
            }
            inner.set_item(Side::BID, bid_list)?;
            inner.set_item(Side::ASK, ask_list)?;
            outer.set_item(symbol, inner)?;
        }
        Ok(outer.into())
    }

    /// Expose level_map as dict[symbol, dict[Side, dict[Price, PriceLevel]]] for API parity.
    #[getter]
    fn level_map(&self, py: Python<'_>) -> PyResult<PyObject> {
        let outer = PyDict::new(py);
        for (symbol, sym_book) in &self.symbols {
            let inner = PyDict::new(py);
            let bid_map = PyDict::new(py);
            for lvl in &sym_book.bids.levels {
                let mut pl = PriceLevel::from_rust(Side::BID, lvl.price);
                for entry in &lvl.orders {
                    pl.orders.append_order(entry.to_order());
                }
                let py_price = decimal_to_py(py, lvl.price)?;
                bid_map.set_item(py_price, Py::new(py, pl)?)?;
            }
            let ask_map = PyDict::new(py);
            for lvl in &sym_book.asks.levels {
                let mut pl = PriceLevel::from_rust(Side::ASK, lvl.price);
                for entry in &lvl.orders {
                    pl.orders.append_order(entry.to_order());
                }
                let py_price = decimal_to_py(py, lvl.price)?;
                ask_map.set_item(py_price, Py::new(py, pl)?)?;
            }
            inner.set_item(Side::BID, bid_map)?;
            inner.set_item(Side::ASK, ask_map)?;
            outer.set_item(symbol, inner)?;
        }
        Ok(outer.into())
    }
}

impl Book {
    /// Core matching logic — pure Rust, no Python objects involved.
    fn match_inner(
        &mut self,
        incoming_id: Uuid,
        incoming_price: Decimal,
        incoming_side: Side,
        incoming_qty: i64,
        symbol: &str,
    ) -> MatchResult {
        let mut trades: Vec<Trade> = Vec::new();
        let mut remaining_qty = incoming_qty;

        let sym_book = self.symbols.entry(symbol.to_string()).or_default();

        let opposite = match incoming_side {
            Side::BID => &mut sym_book.asks,
            Side::ASK => &mut sym_book.bids,
        };

        while remaining_qty > 0 && !opposite.levels.is_empty() {
            let standing_price = opposite.levels.last().unwrap().price;

            if !incoming_side.price_is_matchable(incoming_price, standing_price) {
                break;
            }

            let last_idx = opposite.levels.len() - 1;
            let level = &mut opposite.levels[last_idx];

            while remaining_qty > 0 && !level.orders.is_empty() {
                let standing = level.orders.front_mut().unwrap();
                let matched_qty = remaining_qty.min(standing.quantity);

                standing.quantity -= matched_qty;
                remaining_qty -= matched_qty;

                let fill_price =
                    incoming_side.calc_fill_price(incoming_price, standing.price);

                trades.push(Trade::from_rust(
                    incoming_id,
                    standing.id,
                    matched_qty,
                    fill_price,
                ));

                if standing.quantity == 0 {
                    let filled = level.orders.pop_front().unwrap();
                    self.order_map.remove(&filled.id);
                }
            }

            if opposite.levels.last().map_or(false, |l| l.orders.is_empty()) {
                opposite.levels.pop();
            }
        }

        MatchResult {
            trades,
            remaining_qty,
        }
    }

    /// Match a single incoming order, enqueue remainder, return TradeBlotter.
    fn match_single(&mut self, incoming: &Order) -> PyResult<TradeBlotter> {
        let symbol = incoming.symbol.clone();
        let incoming_side = incoming.side;
        let incoming_price = incoming.price;

        let result = self.match_inner(
            incoming.id,
            incoming_price,
            incoming_side,
            incoming.quantity,
            &symbol,
        );

        // Enqueue remainder
        if result.remaining_qty > 0 {
            let mut entry = OrderEntry::from_order(incoming);
            entry.quantity = result.remaining_qty;

            let ascending = matches!(incoming_side, Side::BID);
            let same_side = match incoming_side {
                Side::BID => &mut self.symbols.get_mut(&symbol).unwrap().bids,
                Side::ASK => &mut self.symbols.get_mut(&symbol).unwrap().asks,
            };
            same_side.insert(entry, ascending);
            self.order_map
                .insert(incoming.id, (symbol, incoming_side, incoming_price));
        }

        let mut result_order = incoming.clone();
        result_order.quantity = result.remaining_qty;

        Ok(TradeBlotter::from_rust(result_order, result.trades))
    }
}
