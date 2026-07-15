//! Monte Carlo path-simulation engine (GBM / OU / correlated forwards), antithetic
//! variates, seeded RNG.
//!
//! The **math kernels** ([`simulate_gbm_terminal_and_averages`], [`simulate_ou_core`],
//! [`cholesky_lower`], [`simulate_correlated_forwards_core`]) are pure Rust — no PyO3
//! types — so `cargo test` covers them without Python. The thin PyO3 wrappers here
//! ([`simulate_ou`], [`simulate_correlated_forwards`], [`simulate_correlated_forwards_term`])
//! are registered in `quantvolt._core` and marshal NumPy arrays in/out; each delegates all
//! arithmetic to its pure core.
//!
//! **Determinism (Req 11.2)**: every simulator takes an explicit `seed` and drives a
//! [`StdRng`] via `SeedableRng::seed_from_u64`, so the same seed yields bit-identical
//! results run-to-run for a given build. The stream is *not* NumPy-compatible: quantvolt
//! guarantees per-seed reproducibility, not cross-language stream equivalence.
//!
//! **Antithetic convention**: paths are generated in `(+W, -W)` pairs and each pair
//! counts as **2** toward `path_count`; an odd `path_count` is rounded *up* to the next
//! even number (the returned vector's length is the effective path count).

use numpy::prelude::*;
use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rand::rngs::StdRng;
use rand::{RngExt, SeedableRng};
use rand_distr::StandardNormal;

/// Per-path summary of a driftless GBM with `m` equally spaced fixings.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PathAverages {
    /// Forward at the final fixing `t_m = T`.
    pub terminal: f64,
    /// Arithmetic average of the `m` fixings.
    pub arithmetic: f64,
    /// Geometric average of the `m` fixings.
    pub geometric: f64,
}

/// Simulate driftless GBM under the forward measure and return per-path averages.
///
/// `F_t = F0 * exp(-sigma^2 t / 2 + sigma * W_t)`, sampled at the equally spaced
/// fixings `t_k = k * T / m` for `k = 1..=m` (`m = averaging_points`).
///
/// With `antithetic = true`, Brownian increments are reused with flipped sign so the
/// second path of each pair sees exactly `-W`; see the module docs for the
/// `path_count` rounding convention. With `antithetic = false`, exactly `path_count`
/// independent paths are returned.
pub fn simulate_gbm_terminal_and_averages(
    forward: f64,
    sigma: f64,
    time_to_expiry: f64,
    averaging_points: usize,
    seed: u64,
    path_count: usize,
    antithetic: bool,
) -> Vec<PathAverages> {
    let m = averaging_points;
    let dt = time_to_expiry / m as f64;
    let sqrt_dt = dt.sqrt();
    let mut rng = StdRng::seed_from_u64(seed);

    // Per-fixing constants, hoisted out of the path loop (hot-path rule, tech.md):
    // drift_k = -sigma^2 t_k / 2 at t_k = k*T/m.
    let drift: Vec<f64> = (1..=m)
        .map(|k| -0.5 * sigma * sigma * (k as f64) * dt)
        .collect();

    let effective = if antithetic {
        path_count.div_ceil(2) * 2
    } else {
        path_count
    };
    let mut out = Vec::with_capacity(effective);
    let mut increments = vec![0.0_f64; m];

    if antithetic {
        // Mirror constant per fixing: F+_k * F-_k = F^2 exp(2 drift_k), so the -W leg
        // costs one division per fixing instead of a second exp.
        let mirror: Vec<f64> = drift
            .iter()
            .map(|d| forward * forward * (2.0 * d).exp())
            .collect();
        for _ in 0..effective / 2 {
            for dw in increments.iter_mut() {
                *dw = sqrt_dt * rng.sample::<f64, _>(StandardNormal);
            }
            let (plus, minus) = antithetic_pair(forward, sigma, &drift, &mirror, &increments);
            out.push(plus);
            out.push(minus);
        }
    } else {
        for _ in 0..effective {
            for dw in increments.iter_mut() {
                *dw = sqrt_dt * rng.sample::<f64, _>(StandardNormal);
            }
            out.push(single_path(forward, sigma, &drift, &increments));
        }
    }
    out
}

/// Walk one GBM path from pre-drawn Brownian increments.
fn single_path(forward: f64, sigma: f64, drift: &[f64], increments: &[f64]) -> PathAverages {
    let m = increments.len() as f64;
    let mut w = 0.0_f64; // Brownian motion at t_k
    let mut arith_sum = 0.0_f64;
    let mut log_sum = 0.0_f64;
    let mut fixing = forward;
    for (d, dw) in drift.iter().zip(increments) {
        w += dw;
        let log_f = d + sigma * w;
        fixing = forward * log_f.exp();
        arith_sum += fixing;
        log_sum += log_f;
    }
    PathAverages {
        terminal: fixing,
        arithmetic: arith_sum / m,
        geometric: forward * (log_sum / m).exp(),
    }
}

/// Walk a `(+W, -W)` antithetic pair in one pass over the shared increments.
fn antithetic_pair(
    forward: f64,
    sigma: f64,
    drift: &[f64],
    mirror: &[f64],
    increments: &[f64],
) -> (PathAverages, PathAverages) {
    let m = increments.len() as f64;
    let mut w = 0.0_f64;
    let (mut arith_plus, mut log_plus_sum, mut fix_plus) = (0.0_f64, 0.0_f64, forward);
    let (mut arith_minus, mut log_minus_sum, mut fix_minus) = (0.0_f64, 0.0_f64, forward);
    for ((d, c), dw) in drift.iter().zip(mirror).zip(increments) {
        w += dw;
        let sw = sigma * w; // the -W leg sees exactly -sw
        let log_plus = d + sw;
        fix_plus = forward * log_plus.exp();
        fix_minus = c / fix_plus; // = forward * exp(d - sw), one division instead of an exp
        arith_plus += fix_plus;
        arith_minus += fix_minus;
        log_plus_sum += log_plus;
        log_minus_sum += d - sw;
    }
    (
        PathAverages {
            terminal: fix_plus,
            arithmetic: arith_plus / m,
            geometric: forward * (log_plus_sum / m).exp(),
        },
        PathAverages {
            terminal: fix_minus,
            arithmetic: arith_minus / m,
            geometric: forward * (log_minus_sum / m).exp(),
        },
    )
}

/// Simulate Ornstein-Uhlenbeck paths by Euler stepping (seeded, no antithetics).
///
/// `x_{t+dt} = x_t + kappa * (mu - x_t) * dt + sigma * sqrt(dt) * z`.
///
/// Returns `path_count` paths, each of length `steps + 1` with `x0` first.
///
/// Pure kernel (no PyO3); the [`simulate_ou`] wrapper marshals it to NumPy for
/// `quantvolt._core`. Determinism per `seed` (Req 11.2); GBM / OU per Task 59.
#[allow(clippy::too_many_arguments)]
pub fn simulate_ou_core(
    x0: f64,
    kappa: f64,
    mu: f64,
    sigma: f64,
    dt: f64,
    steps: usize,
    seed: u64,
    path_count: usize,
) -> Vec<Vec<f64>> {
    let sqrt_dt = dt.sqrt();
    let mut rng = StdRng::seed_from_u64(seed);
    let mut out = Vec::with_capacity(path_count);
    for _ in 0..path_count {
        let mut path = Vec::with_capacity(steps + 1);
        let mut x = x0;
        path.push(x);
        for _ in 0..steps {
            let z: f64 = rng.sample(StandardNormal);
            x += kappa * (mu - x) * dt + sigma * sqrt_dt * z;
            path.push(x);
        }
        out.push(path);
    }
    out
}

/// Python binding for [`simulate_ou_core`]: simulate Ornstein-Uhlenbeck (mean-reverting)
/// paths by seeded Euler stepping. Returns a NumPy `float64` array of shape
/// `(path_count, steps + 1)` with `x0` in column 0. The Python wrapper validates inputs
/// (finite params, positive `dt`, `steps`/`path_count` >= 1) before calling. Determinism
/// per `seed` (Req 11.2); GBM / OU engine per Task 59 (`.kiro/steering/tech.md`).
#[pyfunction]
#[pyo3(signature = (x0, kappa, mu, sigma, dt, steps, seed, path_count))]
#[allow(clippy::too_many_arguments)]
pub fn simulate_ou<'py>(
    py: Python<'py>,
    x0: f64,
    kappa: f64,
    mu: f64,
    sigma: f64,
    dt: f64,
    steps: usize,
    seed: u64,
    path_count: usize,
) -> PyResult<Bound<'py, numpy::PyArray2<f64>>> {
    let paths = simulate_ou_core(x0, kappa, mu, sigma, dt, steps, seed, path_count);
    let cols = steps + 1;
    let mut flat = Vec::with_capacity(paths.len() * cols);
    for p in &paths {
        flat.extend_from_slice(p);
    }
    let arr = PyArray1::from_vec(py, flat);
    arr.reshape([paths.len(), cols])
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

// ---------------------------------------------------------------------------
// Correlated multi-commodity forward simulation (Task 62, Appendix A, GBM).
// ---------------------------------------------------------------------------

/// Simulated correlated log-forward trajectories, flat row-major with logical shape
/// `(n_paths, steps + 1, dim)` — record 0 of every path is the initial state `z0`.
#[derive(Debug, Clone, PartialEq)]
pub struct CorrelatedPaths {
    pub data: Vec<f64>,
    pub n_paths: usize,
    pub steps: usize,
    pub dim: usize,
}

/// Lower-triangular Cholesky factor `L` of a symmetric PSD matrix `cov` (flat
/// row-major, dimension `n`) such that `cov = L·Lᵀ` (eq A.9).
///
/// **Zero-pivot tolerant.** A zero diagonal pivot — an expired/zero-variance tenor
/// (eq A.5) or a rank-deficient PSD block from perfectly correlated tenors (|ρ| = 1) —
/// yields a zero row/column instead of a division by zero, which is the correct factor
/// for a rank-deficient PSD matrix. A pivot below `-tol`, with
/// `tol = 1e-10·max(1, max diagonal)`, means the matrix is **not** PSD and returns
/// `Err`. This is a defensive backstop only: the Python boundary already rejects
/// non-PSD input (Property 61), so a complex factor is never produced here.
pub fn cholesky_lower(cov: &[f64], n: usize) -> Result<Vec<f64>, String> {
    let mut max_diag = 0.0_f64;
    for d in 0..n {
        max_diag = max_diag.max(cov[d * n + d].abs());
    }
    let tol = 1e-10 * max_diag.max(1.0);

    let mut l = vec![0.0_f64; n * n];
    for i in 0..n {
        for j in 0..=i {
            let mut sum = cov[i * n + j];
            for k in 0..j {
                sum -= l[i * n + k] * l[j * n + k];
            }
            if i == j {
                if sum < -tol {
                    return Err(format!(
                        "covariance is not positive semidefinite: negative Cholesky pivot \
                         {sum:e} at index {i}"
                    ));
                }
                l[i * n + j] = if sum > 0.0 { sum.sqrt() } else { 0.0 };
            } else {
                let ljj = l[j * n + j];
                // A true PSD matrix with L[j][j] == 0 also has this numerator == 0, so a
                // zero row/column propagates correctly; guard the division defensively.
                l[i * n + j] = if ljj > 0.0 { sum / ljj } else { 0.0 };
            }
        }
    }
    Ok(l)
}

/// `out = L·x` for a lower-triangular `L` (flat row-major, dimension `n`).
fn matvec_lower(l: &[f64], x: &[f64], n: usize, out: &mut [f64]) {
    for i in 0..n {
        let row = &l[i * n..i * n + i + 1];
        let mut acc = 0.0_f64;
        for (j, &lij) in row.iter().enumerate() {
            acc += lij * x[j];
        }
        out[i] = acc;
    }
}

/// Simulate correlated GBM log-forward curves (Appendix A). **Pure Rust.**
///
/// State `Z = {Z_{t,k}^i} = {log F}` is a flat vector of dimension `dim` over the
/// commodity/tenor pairs the caller has flattened. Given the initial curve `z0`, a
/// per-step drift `mu` (both length `dim`) and the assembled covariance `cov` (flat
/// row-major `dim*dim`, symmetric PSD — validated in Python), each step draws
/// `ε ~ N(0, I)` and forms the correlated increment (eqs A.9–A.13)
///
/// ```text
///     L = chol(cov),   ΔZ = μ + L·ε,   Z ← Z + ΔZ
/// ```
///
/// The same covariance and drift apply at every one of `steps` steps.
///
/// **Expired-tenor masking (eq A.5).** A state index `d` with zero variance
/// (`cov[d][d] == 0`) is treated as an expired tenor (`k < k_t`): its increment is
/// forced to exactly `0` — drift ignored, no noise — so `Z[d]` stays at `z0[d]` on
/// every path and step. (For a PSD `cov`, a zero diagonal forces the whole row/column
/// to zero, so `(L·ε)[d]` is already `0`; the mask additionally suppresses the drift.)
///
/// **Antithetic variates.** With `antithetic = true`, paths are generated in `(+ε, -ε)`
/// pairs sharing each step's drawn normals; the `-ε` leg uses `ΔZ = μ − L·ε`. Each pair
/// counts as 2 toward `path_count` and an odd `path_count` rounds up (see module docs).
///
/// The engine is **measure-agnostic**: the caller supplies `μ` consistent with their
/// measure — physical `P` (VaR/scenarios) or risk-neutral `Q` (pricing, where
/// `μ = −½·diag(cov)` makes the forward a martingale). GBM today; the same increment
/// machinery admits OU by swapping the drift/vol term structure (Req 20.5).
#[allow(clippy::too_many_arguments)]
pub fn simulate_correlated_forwards_core(
    z0: &[f64],
    mu: &[f64],
    cov: &[f64],
    dim: usize,
    steps: usize,
    seed: u64,
    path_count: usize,
    antithetic: bool,
) -> Result<CorrelatedPaths, String> {
    if dim < 1 {
        return Err(format!("dim must be >= 1, got {dim}"));
    }
    if z0.len() != dim {
        return Err(format!("z0 length {} must equal dim {dim}", z0.len()));
    }
    if mu.len() != dim {
        return Err(format!("drift length {} must equal dim {dim}", mu.len()));
    }
    if cov.len() != dim * dim {
        return Err(format!(
            "cov length {} must equal dim*dim {}",
            cov.len(),
            dim * dim
        ));
    }
    if steps < 1 {
        return Err(format!("steps must be >= 1, got {steps}"));
    }
    if path_count < 1 {
        return Err(format!("path_count must be >= 1, got {path_count}"));
    }
    for (name, slice) in [("z0", z0), ("drift", mu), ("cov", cov)] {
        if let Some(bad) = slice.iter().find(|v| !v.is_finite()) {
            return Err(format!("{name} must be finite, got {bad}"));
        }
    }

    let l = cholesky_lower(cov, dim)?;
    let active: Vec<bool> = (0..dim).map(|d| cov[d * dim + d] > 0.0).collect();

    let effective = if antithetic {
        path_count.div_ceil(2) * 2
    } else {
        path_count
    };
    let rec = steps + 1;
    let mut data = vec![0.0_f64; effective * rec * dim];
    let mut rng = StdRng::seed_from_u64(seed);
    let mut eps = vec![0.0_f64; dim];
    let mut incr = vec![0.0_f64; dim];

    if antithetic {
        let mut zp = vec![0.0_f64; dim];
        let mut zm = vec![0.0_f64; dim];
        for pair in 0..effective / 2 {
            let (p_plus, p_minus) = (2 * pair, 2 * pair + 1);
            zp.copy_from_slice(z0);
            zm.copy_from_slice(z0);
            write_record(&mut data, p_plus, 0, rec, dim, &zp);
            write_record(&mut data, p_minus, 0, rec, dim, &zm);
            for s in 1..=steps {
                for e in eps.iter_mut() {
                    *e = rng.sample::<f64, _>(StandardNormal);
                }
                matvec_lower(&l, &eps, dim, &mut incr);
                for d in 0..dim {
                    if active[d] {
                        zp[d] += mu[d] + incr[d];
                        zm[d] += mu[d] - incr[d];
                    }
                }
                write_record(&mut data, p_plus, s, rec, dim, &zp);
                write_record(&mut data, p_minus, s, rec, dim, &zm);
            }
        }
    } else {
        let mut z = vec![0.0_f64; dim];
        for p in 0..effective {
            z.copy_from_slice(z0);
            write_record(&mut data, p, 0, rec, dim, &z);
            for s in 1..=steps {
                for e in eps.iter_mut() {
                    *e = rng.sample::<f64, _>(StandardNormal);
                }
                matvec_lower(&l, &eps, dim, &mut incr);
                for d in 0..dim {
                    if active[d] {
                        z[d] += mu[d] + incr[d];
                    }
                }
                write_record(&mut data, p, s, rec, dim, &z);
            }
        }
    }

    Ok(CorrelatedPaths {
        data,
        n_paths: effective,
        steps,
        dim,
    })
}

/// Simulate a time-inhomogeneous correlated state process.
///
/// ``mu_steps`` and ``cov_steps`` contain one drift vector and covariance matrix per
/// simulation step. ``active_steps`` is a row-major boolean mask over ``(steps, dim)``;
/// inactive coordinates are held exactly fixed for that step. This directly represents
/// Appendix A's time-varying ``mu_t``, ``C_t`` and advancing first-live-tenor ``k_t``.
#[allow(clippy::too_many_arguments)]
pub fn simulate_correlated_forwards_term_core(
    z0: &[f64],
    mu_steps: &[f64],
    cov_steps: &[f64],
    active_steps: &[bool],
    dim: usize,
    steps: usize,
    seed: u64,
    path_count: usize,
    antithetic: bool,
) -> Result<CorrelatedPaths, String> {
    if dim < 1 || steps < 1 || path_count < 1 {
        return Err("dim, steps and path_count must all be >= 1".to_string());
    }
    if z0.len() != dim
        || mu_steps.len() != steps * dim
        || cov_steps.len() != steps * dim * dim
        || active_steps.len() != steps * dim
    {
        return Err("term-structure input shapes do not match steps and dim".to_string());
    }
    for (name, slice) in [
        ("z0", z0),
        ("drift_steps", mu_steps),
        ("covariance_steps", cov_steps),
    ] {
        if let Some(bad) = slice.iter().find(|v| !v.is_finite()) {
            return Err(format!("{name} must be finite, got {bad}"));
        }
    }

    let mut factors = Vec::with_capacity(steps);
    for step in 0..steps {
        let start = step * dim * dim;
        factors.push(cholesky_lower(&cov_steps[start..start + dim * dim], dim)?);
    }

    let effective = if antithetic {
        path_count.div_ceil(2) * 2
    } else {
        path_count
    };
    let rec = steps + 1;
    let mut data = vec![0.0_f64; effective * rec * dim];
    let mut rng = StdRng::seed_from_u64(seed);
    let mut eps = vec![0.0_f64; dim];
    let mut incr = vec![0.0_f64; dim];

    let pair_count = if antithetic { effective / 2 } else { effective };
    for pair in 0..pair_count {
        let p_plus = if antithetic { 2 * pair } else { pair };
        let p_minus = 2 * pair + 1;
        let mut plus = z0.to_vec();
        let mut minus = z0.to_vec();
        write_record(&mut data, p_plus, 0, rec, dim, &plus);
        if antithetic {
            write_record(&mut data, p_minus, 0, rec, dim, &minus);
        }
        for step in 0..steps {
            for e in &mut eps {
                *e = rng.sample::<f64, _>(StandardNormal);
            }
            matvec_lower(&factors[step], &eps, dim, &mut incr);
            let offset = step * dim;
            for d in 0..dim {
                if active_steps[offset + d] {
                    plus[d] += mu_steps[offset + d] + incr[d];
                    if antithetic {
                        minus[d] += mu_steps[offset + d] - incr[d];
                    }
                }
            }
            write_record(&mut data, p_plus, step + 1, rec, dim, &plus);
            if antithetic {
                write_record(&mut data, p_minus, step + 1, rec, dim, &minus);
            }
        }
    }
    Ok(CorrelatedPaths {
        data,
        n_paths: effective,
        steps,
        dim,
    })
}

/// Copy state `z` into the `(path, step)` record of the flat `(n_paths, rec, dim)` buffer.
#[inline]
fn write_record(data: &mut [f64], path: usize, step: usize, rec: usize, dim: usize, z: &[f64]) {
    let base = (path * rec + step) * dim;
    data[base..base + dim].copy_from_slice(z);
}

/// Simulate correlated multi-commodity log-forward curves (Appendix A, GBM).
///
/// Returns a NumPy `float64` array of shape `(n_paths, steps + 1, dim)`; record 0 of
/// each path is `z0`. `cov` must be symmetric PSD — the Python wrapper validates this
/// and rejects non-PSD input before calling (Property 61). See
/// [`simulate_correlated_forwards_core`] for the increment law, expired-tenor masking,
/// antithetic convention, and per-seed determinism (Req 11.2, 20.1–20.5).
#[pyfunction]
#[pyo3(signature = (z0, drift, cov, steps, path_count, seed, antithetic))]
#[allow(clippy::too_many_arguments)]
pub fn simulate_correlated_forwards<'py>(
    py: Python<'py>,
    z0: PyReadonlyArray1<'py, f64>,
    drift: PyReadonlyArray1<'py, f64>,
    cov: PyReadonlyArray2<'py, f64>,
    steps: usize,
    path_count: usize,
    seed: u64,
    antithetic: bool,
) -> PyResult<Bound<'py, numpy::PyArray3<f64>>> {
    let z0 = z0
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let drift = drift
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let cov = cov
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let dim = z0.len();

    let sim =
        simulate_correlated_forwards_core(z0, drift, cov, dim, steps, seed, path_count, antithetic)
            .map_err(PyValueError::new_err)?;

    // Build the flat NumPy vector and reshape via numpy's own API — numpy 0.29 links
    // ndarray 0.16 internally, so we avoid constructing an ndarray::Array of our 0.17.
    let flat = PyArray1::from_vec(py, sim.data);
    flat.reshape([sim.n_paths, sim.steps + 1, sim.dim])
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Python binding for the time-varying Appendix-A path kernel.
#[pyfunction]
#[pyo3(signature = (z0, drift_steps, covariance_steps, active_steps, path_count, seed, antithetic))]
#[allow(clippy::too_many_arguments)]
pub fn simulate_correlated_forwards_term<'py>(
    py: Python<'py>,
    z0: PyReadonlyArray1<'py, f64>,
    drift_steps: PyReadonlyArray2<'py, f64>,
    covariance_steps: PyReadonlyArray3<'py, f64>,
    active_steps: PyReadonlyArray2<'py, bool>,
    path_count: usize,
    seed: u64,
    antithetic: bool,
) -> PyResult<Bound<'py, numpy::PyArray3<f64>>> {
    let z0 = z0
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let drift = drift_steps
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let covariance = covariance_steps
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let active = active_steps
        .as_slice()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    let dim = z0.len();
    let steps = drift_steps.shape()[0];
    let sim = simulate_correlated_forwards_term_core(
        z0, drift, covariance, active, dim, steps, seed, path_count, antithetic,
    )
    .map_err(PyValueError::new_err)?;
    let flat = PyArray1::from_vec(py, sim.data);
    flat.reshape([sim.n_paths, sim.steps + 1, sim.dim])
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    const F: f64 = 100.0;
    const SIGMA: f64 = 0.25;
    const T: f64 = 0.5;

    #[test]
    fn gbm_same_seed_is_bit_identical() {
        let a = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 42, 1000, true);
        let b = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 42, 1000, true);
        assert_eq!(a, b);
    }

    #[test]
    fn gbm_different_seeds_differ() {
        let a = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 42, 100, true);
        let b = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 43, 100, true);
        assert_ne!(a, b);
    }

    #[test]
    fn antithetic_pairs_mirror_the_brownian_exactly() {
        // For each (+W, -W) pair the W contributions cancel exactly, so
        // ln(F+_T) + ln(F-_T) = 2 ln F - sigma^2 T to floating-point exactness.
        let paths = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 7, 100, true);
        let expected = 2.0 * F.ln() - SIGMA * SIGMA * T;
        for pair in paths.chunks_exact(2) {
            let got = pair[0].terminal.ln() + pair[1].terminal.ln();
            assert!(
                (got - expected).abs() < 1e-12,
                "got {got}, expected {expected}"
            );
        }
    }

    #[test]
    fn antithetic_odd_path_count_rounds_up_to_even() {
        let paths = simulate_gbm_terminal_and_averages(F, SIGMA, T, 4, 1, 999, true);
        assert_eq!(paths.len(), 1000);
        let plain = simulate_gbm_terminal_and_averages(F, SIGMA, T, 4, 1, 999, false);
        assert_eq!(plain.len(), 999);
    }

    #[test]
    fn gbm_terminal_is_a_martingale_within_tolerance() {
        // E[F_T] = F0 under the forward measure. SE of the mean is roughly
        // F*sigma*sqrt(T)/sqrt(n) ~ 0.04 at n = 200_000 (antithetics shrink it further).
        let paths = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 2024, 200_000, true);
        let mean: f64 = paths.iter().map(|p| p.terminal).sum::<f64>() / paths.len() as f64;
        assert!(
            (mean - F).abs() < 0.2,
            "terminal mean {mean} too far from {F}"
        );
    }

    #[test]
    fn geometric_average_never_exceeds_arithmetic() {
        // AM-GM inequality holds pathwise.
        let paths = simulate_gbm_terminal_and_averages(F, SIGMA, T, 12, 5, 500, true);
        for p in &paths {
            assert!(p.geometric <= p.arithmetic + 1e-12);
        }
    }

    #[test]
    fn ou_same_seed_is_bit_identical() {
        let a = simulate_ou_core(10.0, 2.0, 20.0, 1.0, 1.0 / 252.0, 50, 42, 100);
        let b = simulate_ou_core(10.0, 2.0, 20.0, 1.0, 1.0 / 252.0, 50, 42, 100);
        assert_eq!(a, b);
    }

    #[test]
    fn ou_paths_have_expected_shape() {
        let paths = simulate_ou_core(10.0, 2.0, 20.0, 1.0, 0.01, 50, 42, 7);
        assert_eq!(paths.len(), 7);
        for p in &paths {
            assert_eq!(p.len(), 51);
            assert_eq!(p[0], 10.0);
        }
    }

    #[test]
    fn ou_mean_reverts_toward_mu() {
        // Euler mean recursion: E[x_n] = mu + (x0 - mu) * (1 - kappa*dt)^n.
        let (x0, kappa, mu, sigma, dt, steps) = (10.0, 2.0, 20.0, 0.5, 0.01, 200);
        let paths = simulate_ou_core(x0, kappa, mu, sigma, dt, steps, 9, 50_000);
        let mean: f64 = paths.iter().map(|p| *p.last().unwrap()).sum::<f64>() / paths.len() as f64;
        let expected = mu + (x0 - mu) * (1.0 - kappa * dt).powi(steps as i32);
        // SE of the terminal mean ~ sigma/sqrt(2*kappa)/sqrt(n) ~ 0.001; be generous.
        assert!(
            (mean - expected).abs() < 0.02,
            "mean {mean}, expected {expected}"
        );
        // And it has moved decisively from x0 toward mu.
        assert!((mean - mu).abs() < 1.0);
    }

    // --- Correlated multi-commodity engine (Task 62, Appendix A) ---------------

    /// Assemble the 2x2 covariance C = diag(σ)·R·diag(σ)·Δt for a two-asset test.
    fn cov_2x2(s0: f64, s1: f64, rho: f64, dt: f64) -> [f64; 4] {
        let c00 = s0 * s0 * dt;
        let c11 = s1 * s1 * dt;
        let c01 = rho * s0 * s1 * dt;
        [c00, c01, c01, c11]
    }

    #[test]
    fn cholesky_recovers_the_matrix() {
        let c = cov_2x2(0.2, 0.3, 0.5, 1.0 / 12.0);
        let l = cholesky_lower(&c, 2).unwrap();
        assert_eq!(l[1], 0.0, "L must be lower triangular");
        // Reconstruct L·Lᵀ and compare entrywise.
        let recon = [
            l[0] * l[0],
            l[0] * l[2],
            l[2] * l[0],
            l[2] * l[2] + l[3] * l[3],
        ];
        for (r, c) in recon.iter().zip(c.iter()) {
            assert!((r - c).abs() < 1e-15, "recon {r} vs {c}");
        }
    }

    #[test]
    fn cholesky_rejects_non_psd_matrix() {
        // Eigenvalues 3 and -1 → indefinite; must Err rather than emit a complex factor.
        let indefinite = [1.0, 2.0, 2.0, 1.0];
        let err = cholesky_lower(&indefinite, 2).unwrap_err();
        assert!(err.contains("positive semidefinite"), "got {err}");
    }

    #[test]
    fn cholesky_tolerates_zero_variance_row() {
        // Asset 0 expired (σ=0): row/col zero. L must have a zero row, no NaN.
        let c = [0.0, 0.0, 0.0, 0.0075];
        let l = cholesky_lower(&c, 2).unwrap();
        assert_eq!(l[0], 0.0);
        assert_eq!(l[1], 0.0);
        assert_eq!(l[2], 0.0);
        assert!((l[3] - 0.0075_f64.sqrt()).abs() < 1e-15);
    }

    #[test]
    fn correlated_same_seed_is_bit_identical() {
        let c = cov_2x2(0.2, 0.3, 0.5, 1.0 / 12.0);
        let z0 = [4.0, 3.0];
        let mu = [-0.5 * c[0], -0.5 * c[3]];
        let run =
            || simulate_correlated_forwards_core(&z0, &mu, &c, 2, 6, 2024, 5_000, true).unwrap();
        assert_eq!(run(), run());
    }

    #[test]
    fn correlated_different_seeds_differ() {
        let c = cov_2x2(0.2, 0.3, 0.5, 1.0 / 12.0);
        let z0 = [4.0, 3.0];
        let mu = [0.0, 0.0];
        let a = simulate_correlated_forwards_core(&z0, &mu, &c, 2, 6, 1, 1_000, true).unwrap();
        let b = simulate_correlated_forwards_core(&z0, &mu, &c, 2, 6, 2, 1_000, true).unwrap();
        assert_ne!(a, b);
    }

    #[test]
    fn correlated_shape_and_initial_record() {
        let c = cov_2x2(0.2, 0.3, 0.5, 1.0 / 12.0);
        let z0 = [4.0, 3.0];
        let mu = [0.0, 0.0];
        // Odd path_count rounds up to the next even number under antithetic pairing.
        let sim = simulate_correlated_forwards_core(&z0, &mu, &c, 2, 4, 7, 999, true).unwrap();
        assert_eq!(sim.n_paths, 1000);
        assert_eq!(sim.steps, 4);
        assert_eq!(sim.dim, 2);
        assert_eq!(sim.data.len(), 1000 * 5 * 2);
        // Record 0 of every path is z0.
        let rec = sim.steps + 1;
        for p in 0..sim.n_paths {
            let base = p * rec * sim.dim;
            assert_eq!(sim.data[base], 4.0);
            assert_eq!(sim.data[base + 1], 3.0);
        }
    }

    #[test]
    fn correlated_antithetic_pair_sums_to_twice_drift() {
        // For a (+ε, -ε) pair the L·ε contributions cancel exactly, so per step the
        // two increments sum to 2μ to floating-point exactness (drift is measure input).
        let c = cov_2x2(0.25, 0.35, -0.3, 1.0 / 52.0);
        let z0 = [2.0, 1.5];
        let mu = [0.013, -0.021];
        let steps = 3;
        let sim = simulate_correlated_forwards_core(&z0, &mu, &c, 2, steps, 11, 200, true).unwrap();
        let rec = steps + 1;
        let at = |p: usize, s: usize, d: usize| sim.data[(p * rec + s) * sim.dim + d];
        for pair in 0..sim.n_paths / 2 {
            let (pp, pm) = (2 * pair, 2 * pair + 1);
            for s in 1..=steps {
                for d in 0..2 {
                    let dz_plus = at(pp, s, d) - at(pp, s - 1, d);
                    let dz_minus = at(pm, s, d) - at(pm, s - 1, d);
                    assert!(
                        (dz_plus + dz_minus - 2.0 * mu[d]).abs() < 1e-12,
                        "pair {pair} step {s} dim {d}: {dz_plus}+{dz_minus} != 2*{}",
                        mu[d]
                    );
                }
            }
        }
    }

    #[test]
    fn correlated_expired_tenor_stays_frozen() {
        // Asset 0 expired (σ=0) but carries a nonzero drift; it must stay at z0 on every
        // path/step (eq A.5 masking suppresses both noise and drift). Asset 1 must move.
        let c = [0.0, 0.0, 0.0, 0.0075];
        let z0 = [7.0, 3.0];
        let mu = [0.5, 0.1]; // nonzero drift on the expired tenor: must be ignored
        let steps = 5;
        let sim = simulate_correlated_forwards_core(&z0, &mu, &c, 2, steps, 3, 400, true).unwrap();
        let rec = steps + 1;
        let at = |p: usize, s: usize, d: usize| sim.data[(p * rec + s) * sim.dim + d];
        let mut asset1_moved = false;
        for p in 0..sim.n_paths {
            for s in 0..=steps {
                assert_eq!(
                    at(p, s, 0),
                    7.0,
                    "expired tenor drifted at path {p} step {s}"
                );
                if (at(p, s, 1) - 3.0).abs() > 1e-9 {
                    asset1_moved = true;
                }
            }
        }
        assert!(asset1_moved, "active tenor never moved");
    }

    #[test]
    fn correlated_empirical_covariance_converges_to_c() {
        // Property 60: sample covariance of ΔZ over a large plain sample → C.
        let (s0, s1, rho, dt) = (0.2, 0.3, 0.5, 1.0 / 12.0);
        let c = cov_2x2(s0, s1, rho, dt);
        let z0 = [0.0, 0.0];
        let mu = [0.0, 0.0];
        let n = 400_000;
        let sim = simulate_correlated_forwards_core(&z0, &mu, &c, 2, 1, 2024, n, false).unwrap();
        let rec = 2;
        // First-step increment = Z[path][1][d] - z0[d] = data[(path*2 + 1)*2 + d].
        let dz = |p: usize, d: usize| sim.data[(p * rec + 1) * 2 + d];
        let np = sim.n_paths as f64;
        let (mut m0, mut m1) = (0.0, 0.0);
        for p in 0..sim.n_paths {
            m0 += dz(p, 0);
            m1 += dz(p, 1);
        }
        m0 /= np;
        m1 /= np;
        let (mut s00, mut s11, mut s01) = (0.0, 0.0, 0.0);
        for p in 0..sim.n_paths {
            let (a, b) = (dz(p, 0) - m0, dz(p, 1) - m1);
            s00 += a * a;
            s11 += b * b;
            s01 += a * b;
        }
        let denom = np - 1.0;
        let (e00, e11, e01) = (s00 / denom, s11 / denom, s01 / denom);
        let rel = |got: f64, want: f64| (got - want).abs() / want.abs();
        assert!(rel(e00, c[0]) < 0.03, "C00 {e00} vs {}", c[0]);
        assert!(rel(e11, c[3]) < 0.03, "C11 {e11} vs {}", c[3]);
        assert!(rel(e01, c[1]) < 0.05, "C01 {e01} vs {}", c[1]);
    }
}
