use pyo3::prelude::*;

mod asian_mc;
mod paths;

/// Native Monte Carlo / path-simulation kernels for quantvolt.
/// Exposed to Python as `quantvolt._core`. See Task 59 / .kiro/steering/tech.md.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(asian_mc::asian_monte_carlo, m)?)?;
    m.add_function(wrap_pyfunction!(paths::simulate_ou, m)?)?;
    m.add_function(wrap_pyfunction!(paths::simulate_correlated_forwards, m)?)?;
    m.add_function(wrap_pyfunction!(
        paths::simulate_correlated_forwards_term,
        m
    )?)?;
    Ok(())
}
