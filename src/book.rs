use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use rust_decimal::Decimal;
use std::collections::HashMap;
use std::collections::VecDeque;
use uuid::Uuid;

use crate::order::{decimal_to_py, uuid_to_py, Order, Side};
use crate::snapshot::{Snapshot, SnapshotLevel};
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

const PARQUET_COLUMNS: [&str; 4] = ["side", "symbol", "price", "quantity"];

#[derive(Clone, Debug)]
struct ParquetOrderRow {
    side: Side,
    symbol: String,
    price: f64,
    quantity: i64,
}

impl ParquetOrderRow {
    fn to_order(&self) -> PyResult<Order> {
        Order::try_new(self.side, self.symbol.clone(), self.price, self.quantity)
    }
}

fn parse_parquet_side(side_text: &str, row_idx: usize) -> PyResult<Side> {
    match side_text.to_ascii_lowercase().as_str() {
        "bid" => Ok(Side::BID),
        "ask" => Ok(Side::ASK),
        _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Invalid side at row {}: '{}'. Expected 'bid' or 'ask'.",
            row_idx, side_text
        ))),
    }
}

fn read_required_row_field<'py>(
    row: &Bound<'py, PyDict>,
    field: &str,
    row_idx: usize,
) -> PyResult<Bound<'py, pyo3::PyAny>> {
    row.get_item(field)?.ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!(
            "Missing required field '{}' at row {}",
            field, row_idx
        ))
    })
}

fn extract_row_price(value: &Bound<'_, pyo3::PyAny>, row_idx: usize) -> PyResult<f64> {
    if let Ok(price) = value.extract::<f64>() {
        return Ok(price);
    }
    let as_str: String = value.str()?.extract()?;
    as_str.parse::<f64>().map_err(|_| {
        pyo3::exceptions::PyValueError::new_err(format!(
            "Invalid price at row {}: '{}'",
            row_idx, as_str
        ))
    })
}

fn extract_row_quantity(value: &Bound<'_, pyo3::PyAny>, row_idx: usize) -> PyResult<i64> {
    if let Ok(quantity) = value.extract::<i64>() {
        return Ok(quantity);
    }
    let as_str: String = value.str()?.extract()?;
    as_str.parse::<i64>().map_err(|_| {
        pyo3::exceptions::PyValueError::new_err(format!(
            "Invalid quantity at row {}: '{}'",
            row_idx, as_str
        ))
    })
}

fn read_parquet_rows(path: &str, py: Python<'_>) -> PyResult<Vec<ParquetOrderRow>> {
    let pq = py.import("pyarrow.parquet").map_err(|_| {
        pyo3::exceptions::PyImportError::new_err(
            "pyarrow is required for parquet ingestion. Install with `pip install pyarrow`.",
        )
    })?;

    let table = pq.call_method1("read_table", (path,)).map_err(|err| {
        pyo3::exceptions::PyValueError::new_err(format!(
            "Failed to read parquet file '{}': {}",
            path, err
        ))
    })?;

    let column_names: Vec<String> = table.getattr("column_names")?.extract()?;
    let missing_columns: Vec<&str> = PARQUET_COLUMNS
        .iter()
        .copied()
        .filter(|name| !column_names.iter().any(|existing| existing == name))
        .collect();
    if !missing_columns.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Parquet file must contain columns [{}]; missing [{}].",
            PARQUET_COLUMNS.join(", "),
            missing_columns.join(", ")
        )));
    }

    let rows_obj = table.call_method0("to_pylist")?;
    let rows = rows_obj.downcast::<PyList>()?;
    let mut parsed_rows = Vec::with_capacity(rows.len());

    for (row_idx, row_any) in rows.iter().enumerate() {
        let row = row_any.downcast::<PyDict>().map_err(|_| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Parquet row {} is not a mapping.",
                row_idx
            ))
        })?;

        let side_text: String = read_required_row_field(&row, "side", row_idx)?.extract()?;
        let side = parse_parquet_side(&side_text, row_idx)?;

        let symbol: String = read_required_row_field(&row, "symbol", row_idx)?.extract()?;
        if symbol.is_empty() {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Symbol cannot be empty at row {}",
                row_idx
            )));
        }

        let price = extract_row_price(&read_required_row_field(&row, "price", row_idx)?, row_idx)?;
        let quantity = extract_row_quantity(
            &read_required_row_field(&row, "quantity", row_idx)?,
            row_idx,
        )?;

        parsed_rows.push(ParquetOrderRow {
            side,
            symbol,
            price,
            quantity,
        });
    }

    Ok(parsed_rows)
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
        if let Ok(list) = orders.downcast::<PyList>() {
            let mut blotters: Vec<Py<TradeBlotter>> = Vec::new();
            for item in list.iter() {
                let order: PyRef<Order> = item.extract()?;
                let blotter = self.match_single(&order)?;
                blotters.push(Py::new(py, blotter)?);
            }
            Ok(PyList::new(py, blotters)?.into())
        } else {
            let order: PyRef<Order> = orders.extract()?;
            let blotter = self.match_single(&order)?;
            Ok(Py::new(py, blotter)?.into_any().into())
        }
    }

    /// Replay an event-stream parquet file through the matching engine.
    ///
    /// Expected columns:
    /// - side: "bid" | "ask"
    /// - symbol: string
    /// - price: numeric
    /// - quantity: integer
    ///
    /// Returns a list of TradeBlotter entries, one per input row.
    fn replay_parquet(&mut self, path: &str, py: Python<'_>) -> PyResult<PyObject> {
        let rows = read_parquet_rows(path, py)?;
        let mut blotters: Vec<Py<TradeBlotter>> = Vec::with_capacity(rows.len());
        for row in rows {
            let order = row.to_order()?;
            let blotter = self.match_single(&order)?;
            blotters.push(Py::new(py, blotter)?);
        }
        Ok(PyList::new(py, blotters)?.into())
    }

    /// Ingest a snapshot parquet file directly into the book as standing orders.
    ///
    /// Expected columns:
    /// - side: "bid" | "ask"
    /// - symbol: string
    /// - price: numeric
    /// - quantity: integer
    ///
    /// Returns the number of ingested rows.
    fn ingest_parquet(&mut self, path: &str, py: Python<'_>) -> PyResult<usize> {
        let rows = read_parquet_rows(path, py)?;
        for row in &rows {
            self.enqueue_internal(&row.to_order()?);
        }
        Ok(rows.len())
    }

    /// Build a Book from a snapshot parquet file.
    #[staticmethod]
    fn from_parquet(path: &str, py: Python<'_>) -> PyResult<Self> {
        let mut book = Book::new();
        book.ingest_parquet(path, py)?;
        Ok(book)
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
        let fill_price = incoming_order
            .side
            .calc_fill_price(incoming_order.price, standing_order.price);
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
        self.enqueue_internal(&order);
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

    fn __getattr__(slf: PyRef<'_, Self>, name: &str, py: Python<'_>) -> PyResult<PyObject> {
        let self_obj = crate::getter::pyref_to_object(py, &slf);
        crate::getter::handle_getter_attr(py, self_obj, name)
    }

    /// Return an L2 depth snapshot for a symbol, or None if never seen.
    #[pyo3(signature = (symbol, depth = 5))]
    fn snapshot(&self, symbol: &str, depth: isize) -> Option<Snapshot> {
        let sym_book = self.symbols.get(symbol)?;
        let depth = depth.max(0) as usize;

        // Bids: sorted ascending, best (highest) at back → iterate reversed
        let bid_levels: Vec<SnapshotLevel> = sym_book
            .bids
            .levels
            .iter()
            .rev()
            .take(depth)
            .map(|lvl| {
                let qty: i64 = lvl.orders.iter().map(|o| o.quantity).sum();
                SnapshotLevel::from_rust(lvl.price, qty)
            })
            .collect();

        // Asks: sorted descending, best (lowest) at back → iterate reversed
        let ask_levels: Vec<SnapshotLevel> = sym_book
            .asks
            .levels
            .iter()
            .rev()
            .take(depth)
            .map(|lvl| {
                let qty: i64 = lvl.orders.iter().map(|o| o.quantity).sum();
                SnapshotLevel::from_rust(lvl.price, qty)
            })
            .collect();

        let best_bid = bid_levels.first().map(|l| l.price);
        let best_ask = ask_levels.first().map(|l| l.price);

        let spread = match (best_bid, best_ask) {
            (Some(b), Some(a)) => Some(a - b),
            _ => None,
        };

        let midpoint = match (best_bid, best_ask) {
            (Some(b), Some(a)) => Some((a + b) / Decimal::from(2)),
            _ => None,
        };

        let bid_vwap = compute_vwap(&bid_levels);
        let ask_vwap = compute_vwap(&ask_levels);

        Some(Snapshot {
            bids: bid_levels,
            asks: ask_levels,
            spread,
            midpoint,
            bid_vwap,
            ask_vwap,
        })
    }
}

fn compute_vwap(levels: &[SnapshotLevel]) -> Option<Decimal> {
    let mut sum_pq = Decimal::ZERO;
    let mut sum_q: i64 = 0;
    for lvl in levels {
        sum_pq += lvl.price * Decimal::from(lvl.quantity);
        sum_q += lvl.quantity;
    }
    if sum_q == 0 {
        None
    } else {
        Some(sum_pq / Decimal::from(sum_q))
    }
}

impl Book {
    fn enqueue_internal(&mut self, order: &Order) {
        let entry = OrderEntry::from_order(order);
        let ascending = matches!(order.side, Side::BID);
        let sym_book = self.symbols.entry(order.symbol.clone()).or_default();
        let one_side = if ascending {
            &mut sym_book.bids
        } else {
            &mut sym_book.asks
        };
        one_side.insert(entry, ascending);
        self.order_map
            .insert(order.id, (order.symbol.clone(), order.side, order.price));
    }

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

                let fill_price = incoming_side.calc_fill_price(incoming_price, standing.price);

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

            if opposite
                .levels
                .last()
                .map_or(false, |l| l.orders.is_empty())
            {
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
            let mut remainder = incoming.clone();
            remainder.quantity = result.remaining_qty;
            self.enqueue_internal(&remainder);
        }

        let mut result_order = incoming.clone();
        result_order.quantity = result.remaining_qty;

        Ok(TradeBlotter::from_rust(result_order, result.trades))
    }
}
