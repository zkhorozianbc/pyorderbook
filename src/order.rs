use pyo3::prelude::*;
use pyo3::sync::GILOnceCell;
use pyo3::types::PyType;
use rust_decimal::Decimal;
use std::str::FromStr;
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Cached Python class references — initialized once per process
// ---------------------------------------------------------------------------

static UUID_CLS: GILOnceCell<Py<PyType>> = GILOnceCell::new();
static DECIMAL_CLS: GILOnceCell<Py<PyType>> = GILOnceCell::new();

pub fn uuid_cls(py: Python<'_>) -> PyResult<&Py<PyType>> {
    UUID_CLS.get_or_try_init(py, || {
        let cls = py.import("uuid")?.getattr("UUID")?;
        Ok(cls.downcast::<PyType>()?.clone().unbind())
    })
}

pub fn decimal_cls(py: Python<'_>) -> PyResult<&Py<PyType>> {
    DECIMAL_CLS.get_or_try_init(py, || {
        let cls = py.import("decimal")?.getattr("Decimal")?;
        Ok(cls.downcast::<PyType>()?.clone().unbind())
    })
}

/// Helper: Rust Uuid -> Python uuid.UUID
pub fn uuid_to_py(py: Python<'_>, id: Uuid) -> PyResult<PyObject> {
    let cls = uuid_cls(py)?;
    Ok(cls.call1(py, (id.to_string(),))?.into())
}

/// Helper: Rust Decimal -> Python decimal.Decimal
pub fn decimal_to_py(py: Python<'_>, d: Decimal) -> PyResult<PyObject> {
    let cls = decimal_cls(py)?;
    Ok(cls.call1(py, (d.to_string(),))?.into())
}

// ---------------------------------------------------------------------------
// Side enum — supports string equality to match Python's StrEnum behavior
// ---------------------------------------------------------------------------

/// BID or ASK side of an order.
///
/// Supports equality with strings: `Side.BID == "bid"` is True,
/// matching the Python StrEnum behavior.
#[pyclass]
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Side {
    BID,
    ASK,
}

impl Side {
    pub fn as_str(self) -> &'static str {
        match self {
            Side::BID => "bid",
            Side::ASK => "ask",
        }
    }
}

#[pymethods]
impl Side {
    /// Return the opposite side.
    #[getter]
    fn other(&self) -> Side {
        match self {
            Side::BID => Side::ASK,
            Side::ASK => Side::BID,
        }
    }

    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> &'static str {
        match self {
            Side::BID => "Side.BID",
            Side::ASK => "Side.ASK",
        }
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        // Use Python's hash() on the string value so Side.BID and "bid"
        // have the same hash, matching Python StrEnum behavior.
        let py_str = pyo3::types::PyString::new(py, self.as_str());
        py_str.hash()
    }

    fn __eq__(&self, other: &Bound<'_, pyo3::PyAny>) -> PyResult<bool> {
        // Support comparison with other Side instances
        if let Ok(other_side) = other.extract::<Side>() {
            return Ok(*self == other_side);
        }
        // Support comparison with strings (StrEnum parity)
        if let Ok(s) = other.extract::<String>() {
            return Ok(self.as_str() == s);
        }
        Ok(false)
    }
}

impl Side {
    /// Check if incoming price can match against standing price.
    pub fn price_is_matchable(self, incoming: Decimal, standing: Decimal) -> bool {
        match self {
            Side::BID => incoming >= standing,
            Side::ASK => incoming <= standing,
        }
    }

    /// Determine the fill price for a trade.
    pub fn calc_fill_price(self, incoming: Decimal, standing: Decimal) -> Decimal {
        match self {
            Side::BID => incoming.min(standing),
            Side::ASK => incoming.max(standing),
        }
    }
}

impl std::fmt::Display for Side {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

// ---------------------------------------------------------------------------
// OrderStatus enum
// ---------------------------------------------------------------------------

/// Order status after matching.
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, Debug, PartialEq)]
#[allow(non_camel_case_types)]
pub enum OrderStatus {
    QUEUED,
    PARTIAL_FILL,
    FILLED,
}

#[pymethods]
impl OrderStatus {
    fn __str__(&self) -> &'static str {
        match self {
            OrderStatus::QUEUED => "queued",
            OrderStatus::PARTIAL_FILL => "partial_fill",
            OrderStatus::FILLED => "filled",
        }
    }

    fn __repr__(&self) -> &'static str {
        match self {
            OrderStatus::QUEUED => "OrderStatus.QUEUED",
            OrderStatus::PARTIAL_FILL => "OrderStatus.PARTIAL_FILL",
            OrderStatus::FILLED => "OrderStatus.FILLED",
        }
    }
}

// ---------------------------------------------------------------------------
// Order
// ---------------------------------------------------------------------------

/// A single order in the book.
#[pyclass]
#[derive(Clone, Debug)]
pub struct Order {
    pub id: Uuid,
    pub price: Decimal,
    pub quantity: i64,
    pub symbol: String,
    pub side: Side,
    pub original_quantity: i64,
}

#[pymethods]
impl Order {
    #[new]
    fn new(side: Side, symbol: String, price: f64, quantity: i64) -> PyResult<Self> {
        if quantity <= 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Order quantity must be greater than zero",
            ));
        }
        // Convert via string to match Python's Decimal(str(price)) behavior.
        let price_str = price.to_string();
        let decimal_price = Decimal::from_str(&price_str).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid price value: {}", e))
        })?;
        Ok(Order {
            id: Uuid::new_v4(),
            price: decimal_price,
            quantity,
            symbol,
            side,
            original_quantity: quantity,
        })
    }

    /// Return the order id as a Python uuid.UUID.
    #[getter]
    fn id(&self, py: Python<'_>) -> PyResult<PyObject> {
        uuid_to_py(py, self.id)
    }

    /// Return the price as a Python decimal.Decimal.
    #[getter]
    fn price(&self, py: Python<'_>) -> PyResult<PyObject> {
        decimal_to_py(py, self.price)
    }

    #[getter]
    fn quantity(&self) -> i64 {
        self.quantity
    }

    #[setter]
    fn set_quantity(&mut self, value: i64) {
        self.quantity = value;
    }

    #[getter]
    fn symbol(&self) -> &str {
        &self.symbol
    }

    #[getter]
    fn side(&self) -> Side {
        self.side
    }

    #[getter]
    fn original_quantity(&self) -> i64 {
        self.original_quantity
    }

    /// Computed status based on remaining vs original quantity.
    #[getter]
    fn status(&self) -> OrderStatus {
        if self.quantity == 0 {
            OrderStatus::FILLED
        } else if self.quantity < self.original_quantity {
            OrderStatus::PARTIAL_FILL
        } else {
            OrderStatus::QUEUED
        }
    }
}

// ---------------------------------------------------------------------------
// bid / ask convenience functions
// ---------------------------------------------------------------------------

/// Create a BID order.
#[pyfunction]
pub fn bid(symbol: String, price: f64, quantity: i64) -> PyResult<Order> {
    Order::new(Side::BID, symbol, price, quantity)
}

/// Create an ASK order.
#[pyfunction]
pub fn ask(symbol: String, price: f64, quantity: i64) -> PyResult<Order> {
    Order::new(Side::ASK, symbol, price, quantity)
}
