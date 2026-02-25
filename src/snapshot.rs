use pyo3::prelude::*;
use rust_decimal::Decimal;

use crate::order::decimal_to_py;

// ---------------------------------------------------------------------------
// SnapshotLevel — a single aggregated price level in a snapshot
// ---------------------------------------------------------------------------

#[pyclass]
#[derive(Clone, Debug)]
pub struct SnapshotLevel {
    pub price: Decimal,
    pub quantity: i64,
}

#[pymethods]
impl SnapshotLevel {
    #[getter]
    fn price(&self, py: Python<'_>) -> PyResult<PyObject> {
        decimal_to_py(py, self.price)
    }

    #[getter]
    fn quantity(&self) -> i64 {
        self.quantity
    }
}

impl SnapshotLevel {
    pub fn from_rust(price: Decimal, quantity: i64) -> Self {
        SnapshotLevel { price, quantity }
    }
}

// ---------------------------------------------------------------------------
// Snapshot — L2 depth view of one symbol
// ---------------------------------------------------------------------------

#[pyclass]
#[derive(Clone, Debug)]
pub struct Snapshot {
    pub bids: Vec<SnapshotLevel>,
    pub asks: Vec<SnapshotLevel>,
    pub spread: Option<Decimal>,
    pub midpoint: Option<Decimal>,
    pub bid_vwap: Option<Decimal>,
    pub ask_vwap: Option<Decimal>,
}

#[pymethods]
impl Snapshot {
    #[getter]
    fn bids(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = pyo3::types::PyList::empty(py);
        for lvl in &self.bids {
            list.append(Py::new(py, lvl.clone())?)?;
        }
        Ok(list.into())
    }

    #[getter]
    fn asks(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = pyo3::types::PyList::empty(py);
        for lvl in &self.asks {
            list.append(Py::new(py, lvl.clone())?)?;
        }
        Ok(list.into())
    }

    #[getter]
    fn spread(&self, py: Python<'_>) -> PyResult<PyObject> {
        optional_decimal_to_py(py, self.spread)
    }

    #[getter]
    fn midpoint(&self, py: Python<'_>) -> PyResult<PyObject> {
        optional_decimal_to_py(py, self.midpoint)
    }

    #[getter]
    fn bid_vwap(&self, py: Python<'_>) -> PyResult<PyObject> {
        optional_decimal_to_py(py, self.bid_vwap)
    }

    #[getter]
    fn ask_vwap(&self, py: Python<'_>) -> PyResult<PyObject> {
        optional_decimal_to_py(py, self.ask_vwap)
    }
}

fn optional_decimal_to_py(py: Python<'_>, value: Option<Decimal>) -> PyResult<PyObject> {
    match value {
        Some(d) => decimal_to_py(py, d),
        None => Ok(py.None().into()),
    }
}
