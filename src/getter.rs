use pyo3::prelude::*;
use pyo3::PyClass;

/// Internal callable returned by `__getattr__` for `get_*` attribute lookups.
/// Lazily evaluates the attribute on the underlying object when called.
#[pyclass]
pub struct _GetterMethod {
    obj: PyObject,
    attr: String,
}

#[pymethods]
impl _GetterMethod {
    fn __call__(&self, py: Python<'_>) -> PyResult<PyObject> {
        self.obj.getattr(py, self.attr.as_str())
    }

    fn __repr__(&self) -> String {
        format!("<getter for '{}'>", self.attr)
    }
}

/// Handle `get_*` attribute lookups. Returns a `_GetterMethod` callable
/// if the underlying attribute (without the `get_` prefix) exists.
pub fn handle_getter_attr(py: Python<'_>, self_obj: PyObject, name: &str) -> PyResult<PyObject> {
    if let Some(attr_name) = name.strip_prefix("get_") {
        if self_obj.getattr(py, attr_name).is_ok() {
            let getter = _GetterMethod {
                obj: self_obj,
                attr: attr_name.to_string(),
            };
            let py_getter = Py::new(py, getter)?.into_bound(py).into_any().unbind();
            return Ok(py_getter);
        }
    }
    Err(pyo3::exceptions::PyAttributeError::new_err(format!(
        "object has no attribute '{}'",
        name
    )))
}

/// Convert a PyRef to a PyObject for use in __getattr__ methods.
pub fn pyref_to_object<T: PyClass>(py: Python<'_>, slf: &PyRef<'_, T>) -> PyObject {
    // SAFETY: PyRef holds a valid borrowed reference to a Python object.
    // from_borrowed_ptr increments the refcount, giving us an owned reference.
    unsafe { PyObject::from_borrowed_ptr(py, slf.as_ptr()) }
}
