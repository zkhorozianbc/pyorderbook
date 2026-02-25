use pyo3::prelude::*;
use rust_decimal::Decimal;
use rust_decimal::prelude::ToPrimitive;
use std::collections::VecDeque;
use uuid::Uuid;

use crate::order::{decimal_to_py, uuid_to_py, Order, Side};

// ---------------------------------------------------------------------------
// Trade
// ---------------------------------------------------------------------------

/// A single trade between an incoming and standing order.
#[pyclass]
#[derive(Clone, Debug)]
pub struct Trade {
    pub incoming_order_id: Uuid,
    pub standing_order_id: Uuid,
    pub fill_quantity: i64,
    pub fill_price: Decimal,
}

#[pymethods]
impl Trade {
    #[new]
    fn new(
        incoming_order_id: &Bound<'_, pyo3::PyAny>,
        standing_order_id: &Bound<'_, pyo3::PyAny>,
        fill_quantity: i64,
        fill_price: &Bound<'_, pyo3::PyAny>,
    ) -> PyResult<Self> {
        let inc_str: String = incoming_order_id.str()?.extract()?;
        let std_str: String = standing_order_id.str()?.extract()?;
        let price_str: String = fill_price.str()?.extract()?;

        let inc_id = Uuid::parse_str(&inc_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid incoming_order_id: {}", e))
        })?;
        let std_id = Uuid::parse_str(&std_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid standing_order_id: {}", e))
        })?;
        let price = Decimal::from_str_exact(&price_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid fill_price: {}", e))
        })?;

        Ok(Trade {
            incoming_order_id: inc_id,
            standing_order_id: std_id,
            fill_quantity,
            fill_price: price,
        })
    }

    #[getter]
    fn incoming_order_id(&self, py: Python<'_>) -> PyResult<PyObject> {
        uuid_to_py(py, self.incoming_order_id)
    }

    #[getter]
    fn standing_order_id(&self, py: Python<'_>) -> PyResult<PyObject> {
        uuid_to_py(py, self.standing_order_id)
    }

    #[getter]
    fn fill_quantity(&self) -> i64 {
        self.fill_quantity
    }

    #[getter]
    fn fill_price(&self, py: Python<'_>) -> PyResult<PyObject> {
        decimal_to_py(py, self.fill_price)
    }
}

impl Trade {
    /// Create a Trade from Rust-native types (used internally by matching engine).
    pub fn from_rust(
        incoming_order_id: Uuid,
        standing_order_id: Uuid,
        fill_quantity: i64,
        fill_price: Decimal,
    ) -> Self {
        Trade {
            incoming_order_id,
            standing_order_id,
            fill_quantity,
            fill_price,
        }
    }
}

// ---------------------------------------------------------------------------
// TradeBlotter
// ---------------------------------------------------------------------------

/// Blotter statistics returned by Book.match().
#[pyclass]
#[derive(Clone, Debug)]
pub struct TradeBlotter {
    pub order: Order,
    pub trades: Vec<Trade>,
    pub total_cost: f64,
    pub average_price: f64,
}

#[pymethods]
impl TradeBlotter {
    #[new]
    fn new(order: Order, trades: Vec<Trade>) -> Self {
        let (total_cost, average_price) = compute_blotter_stats(&trades);
        TradeBlotter {
            order,
            trades,
            total_cost,
            average_price,
        }
    }

    #[getter]
    fn order(&self, py: Python<'_>) -> PyResult<Py<Order>> {
        Py::new(py, self.order.clone())
    }

    #[getter]
    fn trades(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = pyo3::types::PyList::empty(py);
        for t in &self.trades {
            list.append(Py::new(py, t.clone())?)?;
        }
        Ok(list.into())
    }

    #[getter]
    fn total_cost(&self) -> f64 {
        self.total_cost
    }

    #[getter]
    fn average_price(&self) -> f64 {
        self.average_price
    }
}

impl TradeBlotter {
    /// Create a TradeBlotter from Rust-native types (used internally).
    pub fn from_rust(order: Order, trades: Vec<Trade>) -> Self {
        let (total_cost, average_price) = compute_blotter_stats(&trades);
        TradeBlotter {
            order,
            trades,
            total_cost,
            average_price,
        }
    }
}

fn compute_blotter_stats(trades: &[Trade]) -> (f64, f64) {
    if trades.is_empty() {
        return (0.0, 0.0);
    }
    let mut sum_cost = Decimal::ZERO;
    let mut sum_price = Decimal::ZERO;
    for t in trades {
        sum_cost += t.fill_price * Decimal::from(t.fill_quantity);
        sum_price += t.fill_price;
    }
    let count = Decimal::from(trades.len() as i64);
    let tc = sum_cost.to_f64().unwrap_or(0.0);
    let ap = (sum_price / count).to_f64().unwrap_or(0.0);
    (
        (tc * 100.0).round() / 100.0,
        (ap * 100.0).round() / 100.0,
    )
}

// ---------------------------------------------------------------------------
// OrderQueue — FIFO queue matching Python dict[UUID, Order] semantics
// ---------------------------------------------------------------------------

/// FIFO order queue.
///
/// Supports dict-like operations for API parity with the Python OrderQueue:
/// iteration, keyed lookup via `__getitem__`, and `pop(uuid)`.
#[pyclass]
#[derive(Clone, Debug)]
pub struct OrderQueue {
    orders: VecDeque<Order>,
}

#[pymethods]
impl OrderQueue {
    #[new]
    pub fn new() -> Self {
        OrderQueue {
            orders: VecDeque::new(),
        }
    }

    pub fn append_order(&mut self, order: Order) {
        self.orders.push_back(order);
    }

    fn peek(&self, py: Python<'_>) -> PyResult<Py<Order>> {
        let order = self.orders.front().ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Order Queue is Empty!")
        })?;
        Py::new(py, order.clone())
    }

    fn popleft(&mut self) -> PyResult<()> {
        self.orders.pop_front().ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Order Queue is Empty!")
        })?;
        Ok(())
    }

    /// Remove and return an order by its UUID key (dict.pop parity).
    fn pop(&mut self, order_id: &Bound<'_, pyo3::PyAny>, py: Python<'_>) -> PyResult<Py<Order>> {
        let id_str: String = order_id.str()?.extract()?;
        let uid = Uuid::parse_str(&id_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid order_id: {}", e))
        })?;
        let pos = self.orders.iter().position(|o| o.id == uid).ok_or_else(|| {
            pyo3::exceptions::PyKeyError::new_err(uid.to_string())
        })?;
        let order = self.orders.remove(pos).unwrap();
        Py::new(py, order)
    }

    /// Keyed lookup by UUID (dict[uuid] parity).
    fn __getitem__(&self, key: &Bound<'_, pyo3::PyAny>, py: Python<'_>) -> PyResult<Py<Order>> {
        let id_str: String = key.str()?.extract()?;
        let uid = Uuid::parse_str(&id_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid key: {}", e))
        })?;
        let order = self.orders.iter().find(|o| o.id == uid).ok_or_else(|| {
            pyo3::exceptions::PyKeyError::new_err(uid.to_string())
        })?;
        Py::new(py, order.clone())
    }

    fn __len__(&self) -> usize {
        self.orders.len()
    }

    fn __bool__(&self) -> bool {
        !self.orders.is_empty()
    }

    /// Iterate over order UUIDs (dict iteration parity).
    fn __iter__(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = pyo3::types::PyList::empty(py);
        for order in &self.orders {
            list.append(uuid_to_py(py, order.id)?)?;
        }
        Ok(list.call_method0("__iter__")?.into())
    }

    /// Check if a UUID key is in the queue (dict `in` parity).
    fn __contains__(&self, key: &Bound<'_, pyo3::PyAny>) -> PyResult<bool> {
        let id_str: String = key.str()?.extract()?;
        let uid = match Uuid::parse_str(&id_str) {
            Ok(u) => u,
            Err(_) => return Ok(false),
        };
        Ok(self.orders.iter().any(|o| o.id == uid))
    }
}

// ---------------------------------------------------------------------------
// PriceLevel — with __lt__ for heapq compatibility
// ---------------------------------------------------------------------------

/// Price level exposed to Python.
///
/// Supports `__lt__` for heapq compatibility, matching the Python
/// `PriceLevel.__lt__` that uses `side.price_comparator(self.price, other.price)`.
#[pyclass]
#[derive(Clone, Debug)]
pub struct PriceLevel {
    #[pyo3(get)]
    pub side: Side,
    price: Decimal,
    #[pyo3(get)]
    pub orders: OrderQueue,
}

#[pymethods]
impl PriceLevel {
    #[new]
    fn new(side: Side, price: &Bound<'_, pyo3::PyAny>) -> PyResult<Self> {
        let price_str: String = price.str()?.extract()?;
        let decimal_price = Decimal::from_str_exact(&price_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid price: {}", e))
        })?;
        Ok(PriceLevel {
            side,
            price: decimal_price,
            orders: OrderQueue::new(),
        })
    }

    #[getter]
    fn price(&self, py: Python<'_>) -> PyResult<PyObject> {
        decimal_to_py(py, self.price)
    }

    /// heapq compatibility: BIDS max-heap, ASKS min-heap.
    /// Matches Python: `self.side.price_comparator(self.price, other.price)`
    fn __lt__(&self, other: &PriceLevel) -> bool {
        match self.side {
            // BID comparator is `ge` — for a min-heap to act as max-heap,
            // __lt__ returns True when self.price >= other.price
            Side::BID => self.price >= other.price,
            // ASK comparator is `le` — __lt__ returns True when self.price <= other.price
            Side::ASK => self.price <= other.price,
        }
    }
}

impl PriceLevel {
    /// Create from Rust-native types for internal use.
    pub fn from_rust(side: Side, price: Decimal) -> Self {
        PriceLevel {
            side,
            price,
            orders: OrderQueue::new(),
        }
    }
}
