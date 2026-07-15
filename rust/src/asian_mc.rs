//! Arithmetic / geometric Asian option Monte Carlo pricer (Task 59).
//!
//! The math lives in [`asian_monte_carlo_core`] (pure Rust, covered by `cargo test`);
//! [`asian_monte_carlo`] is the thin PyO3 wrapper registered in `quantvolt._core`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::paths::simulate_gbm_terminal_and_averages;

/// Pure-Rust Asian MC kernel. Returns `(premium, standard_error)`.
///
/// Simulates driftless GBM fixings via [`crate::paths`] with **antithetic variates
/// always on** (an odd `path_count` rounds up to the next even number — see the
/// `paths` module docs). Payoff per path is `max(avg - K, 0)` for a call /
/// `max(K - avg, 0)` for a put on the arithmetic or geometric average per
/// `geometric`. Then
///
/// - `premium = DF * mean(payoff)`
/// - `standard_error = DF * std(payoff, ddof=1) / sqrt(n)` over all `n` paths —
///   a conservative (upward-biased) estimate under antithetic pairing, since the
///   negative within-pair correlation is ignored (when `antithetic` is on).
///
/// Determinism (Req 11.2): identical inputs + `seed` give bit-identical results
/// run-to-run; the stream does not match NumPy's.
#[allow(clippy::too_many_arguments)]
pub fn asian_monte_carlo_core(
    forward: f64,
    strike: f64,
    sigma: f64,
    time_to_expiry: f64,
    discount_factor: f64,
    averaging_points: usize,
    is_call: bool,
    geometric: bool,
    seed: u64,
    path_count: usize,
    antithetic: bool,
) -> Result<(f64, f64), String> {
    if path_count < 1 {
        return Err(format!("path_count must be >= 1, got {path_count}"));
    }
    if averaging_points < 1 {
        return Err(format!(
            "averaging_points must be >= 1, got {averaging_points}"
        ));
    }
    for (name, value) in [
        ("forward", forward),
        ("strike", strike),
        ("sigma", sigma),
        ("time_to_expiry", time_to_expiry),
        ("discount_factor", discount_factor),
    ] {
        if !value.is_finite() {
            return Err(format!("{name} must be finite, got {value}"));
        }
    }

    let paths = simulate_gbm_terminal_and_averages(
        forward,
        sigma,
        time_to_expiry,
        averaging_points,
        seed,
        path_count,
        antithetic,
    );
    let n = paths.len() as f64;
    let payoff = |avg: f64| -> f64 {
        if is_call {
            (avg - strike).max(0.0)
        } else {
            (strike - avg).max(0.0)
        }
    };
    let average = |p: &crate::paths::PathAverages| -> f64 {
        if geometric {
            p.geometric
        } else {
            p.arithmetic
        }
    };

    let mut sum = 0.0_f64;
    let mut sum_sq = 0.0_f64;
    for p in &paths {
        let x = payoff(average(p));
        sum += x;
        sum_sq += x * x;
    }
    let mean = sum / n;
    let premium = discount_factor * mean;
    let standard_error = if paths.len() > 1 {
        let var = ((sum_sq - n * mean * mean) / (n - 1.0)).max(0.0);
        discount_factor * (var / n).sqrt()
    } else {
        0.0
    };
    Ok((premium, standard_error))
}

/// Price an arithmetic/geometric Asian option by Monte Carlo.
/// Returns `(premium, standard_error)`. See [`asian_monte_carlo_core`] for the
/// conventions (antithetic variates default on, standard error, per-seed determinism).
/// `antithetic` is an optional trailing argument (default `true`) so existing
/// positional call sites remain valid.
#[pyfunction]
#[pyo3(signature = (forward, strike, sigma, time_to_expiry, discount_factor,
                    averaging_points, is_call, geometric, seed, path_count, antithetic=true))]
#[allow(clippy::too_many_arguments)]
pub fn asian_monte_carlo(
    forward: f64,
    strike: f64,
    sigma: f64,
    time_to_expiry: f64,
    discount_factor: f64,
    averaging_points: usize,
    is_call: bool,
    geometric: bool,
    seed: u64,
    path_count: usize,
    antithetic: bool,
) -> PyResult<(f64, f64)> {
    asian_monte_carlo_core(
        forward,
        strike,
        sigma,
        time_to_expiry,
        discount_factor,
        averaging_points,
        is_call,
        geometric,
        seed,
        path_count,
        antithetic,
    )
    .map_err(PyValueError::new_err)
}

#[cfg(test)]
mod tests {
    use super::asian_monte_carlo_core;

    // Discrete-fixing geometric Asian closed form (exact for fixings t_k = kT/m),
    // computed independently with scipy:
    //   mean_ln = ln F - sigma^2 T (m+1)/(4m)
    //   var_ln  = sigma^2 T (m+1)(2m+1)/(6 m^2)
    //   Black-76 on (exp(mean_ln + var_ln/2), sqrt(var_ln)).
    const GEO_CALL_REF: f64 = 6.590867916925026; // F=100 K=100 sigma=0.30 T=1.0 DF=0.95 m=12
    const GEO_PUT_REF: f64 = 7.315776045476772; // F=100 K=105 sigma=0.25 T=0.5 DF=0.97 m=12

    #[test]
    fn same_seed_gives_identical_premium_and_se() {
        let run = || {
            asian_monte_carlo_core(
                100.0, 95.0, 0.25, 0.5, 0.97, 12, true, false, 42, 10_000, true,
            )
            .unwrap()
        };
        assert_eq!(run(), run());
    }

    #[test]
    fn different_seeds_give_different_premiums() {
        let price = |seed| {
            asian_monte_carlo_core(
                100.0, 95.0, 0.25, 0.5, 0.97, 12, true, false, seed, 10_000, true,
            )
            .unwrap()
            .0
        };
        assert_ne!(price(1), price(2));
    }

    #[test]
    fn geometric_call_matches_closed_form_within_three_ses() {
        let (premium, se) = asian_monte_carlo_core(
            100.0, 100.0, 0.30, 1.0, 0.95, 12, true, true, 2024, 200_000, true,
        )
        .unwrap();
        assert!(se > 0.0);
        assert!(
            (premium - GEO_CALL_REF).abs() < 3.0 * se,
            "premium {premium} vs reference {GEO_CALL_REF} (se {se})"
        );
    }

    #[test]
    fn geometric_put_matches_closed_form_within_three_ses() {
        let (premium, se) = asian_monte_carlo_core(
            100.0, 105.0, 0.25, 0.5, 0.97, 12, false, true, 7, 200_000, true,
        )
        .unwrap();
        assert!(
            (premium - GEO_PUT_REF).abs() < 3.0 * se,
            "premium {premium} vs reference {GEO_PUT_REF} (se {se})"
        );
    }

    #[test]
    fn arithmetic_call_dominates_geometric_call() {
        // AM-GM pathwise, so with shared inputs the arithmetic premium is >= geometric.
        let price = |geometric| {
            asian_monte_carlo_core(
                100.0, 100.0, 0.30, 1.0, 0.95, 12, true, geometric, 5, 50_000, true,
            )
            .unwrap()
            .0
        };
        assert!(price(false) > price(true));
    }

    #[test]
    fn input_guards_reject_bad_counts_and_non_finite_inputs() {
        let base = |forward: f64, points: usize, paths: usize| {
            asian_monte_carlo_core(
                forward, 95.0, 0.25, 0.5, 0.97, points, true, false, 1, paths, true,
            )
        };
        assert!(base(100.0, 12, 0).unwrap_err().contains("path_count"));
        assert!(base(100.0, 0, 100)
            .unwrap_err()
            .contains("averaging_points"));
        assert!(base(f64::NAN, 12, 100).unwrap_err().contains("forward"));
        assert!(base(f64::INFINITY, 12, 100)
            .unwrap_err()
            .contains("forward"));
    }

    #[test]
    fn deep_itm_call_premium_approaches_discounted_intrinsic() {
        // K << F: payoff ~ avg - K on every path; E[avg] = F, so premium ~ DF*(F - K).
        let (premium, se) = asian_monte_carlo_core(
            100.0, 1.0, 0.10, 0.25, 1.0, 12, true, false, 3, 100_000, true,
        )
        .unwrap();
        assert!((premium - 99.0).abs() < 3.0 * se + 1e-6);
    }

    #[test]
    fn antithetic_false_is_deterministic_and_differs_from_antithetic_true() {
        let run = |antithetic| {
            asian_monte_carlo_core(
                100.0, 95.0, 0.25, 0.5, 0.97, 12, true, false, 42, 10_000, antithetic,
            )
            .unwrap()
        };
        // Same seed, antithetic=false: still bit-identical run-to-run.
        assert_eq!(run(false), run(false));
        // Turning antithetic off changes the draw sequence relative to the
        // antithetic-on default for the same seed.
        assert_ne!(run(false), run(true));
    }
}
