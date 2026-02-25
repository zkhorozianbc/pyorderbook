use pyo3::prelude::*;

mod book;
mod order;
mod trade;

#[pymodule]
fn _rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<order::Side>()?;
    m.add_class::<order::OrderStatus>()?;
    m.add_class::<order::Order>()?;
    m.add_class::<trade::OrderQueue>()?;
    m.add_class::<trade::PriceLevel>()?;
    m.add_class::<book::Book>()?;
    m.add_class::<trade::Trade>()?;
    m.add_class::<trade::TradeBlotter>()?;
    m.add_function(wrap_pyfunction!(order::bid, m)?)?;
    m.add_function(wrap_pyfunction!(order::ask, m)?)?;
    Ok(())
}
