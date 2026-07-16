"""Execute the native Rust and Monte Carlo guide examples."""

import numpy as np

from quantvolt.numerics import (
    CorrelatedSimulationRequest,
    asian_monte_carlo,
    build_covariance,
    simulate_correlated_forwards,
    simulate_correlated_term_structure,
    simulate_ou_paths,
)


premium, standard_error = asian_monte_carlo(
    forward=36.85,
    strike=38.0,
    sigma=0.55,
    time_to_expiry=0.4,
    discount_factor=0.99,
    averaging_points=12,
    option_type="call",
    geometric=False,
    seed=7,
    path_count=50_000,
    antithetic=True,
)
assert abs(premium - 2.623288902376195) < 1e-12
assert abs(standard_error - 0.0219254698055871) < 1e-12

ou = simulate_ou_paths(
    x0=34.0, kappa=2.5, mu=32.0, sigma=0.65,
    dt=1 / 12, steps=24, path_count=1_000, seed=42,
)
assert ou.shape == (1_000, 25)
assert np.all(ou[:, 0] == 34.0)

forwards = np.array([36.85, 92.0, 78.0])
volatility = np.array([0.55, 0.38, 0.24])
correlation = np.array(
    [[1.00, 0.61, 0.28], [0.61, 1.00, 0.35], [0.28, 0.35, 1.00]]
)
covariance = build_covariance(volatility, correlation, dt=1 / 12)
paths = simulate_correlated_forwards(
    z0=np.log(forwards), drift=-0.5 * np.diag(covariance), cov=covariance,
    steps=12, path_count=2_000, seed=42, antithetic=True,
)
assert paths.shape == (2_000, 13, 3)
assert np.array_equal(paths, simulate_correlated_forwards(
    z0=np.log(forwards), drift=-0.5 * np.diag(covariance), cov=covariance,
    steps=12, path_count=2_000, seed=42, antithetic=True,
))

request = CorrelatedSimulationRequest(
    z0=np.log([36.85, 35.90]),
    drift_steps=np.zeros((3, 2)),
    covariance_steps=np.repeat(
        np.array([[[0.010, 0.003], [0.003, 0.006]]]), 3, axis=0
    ),
    active_steps=np.array([[True, True], [True, True], [False, True]]),
    path_count=1_000,
    seed=42,
    antithetic=True,
)
term = simulate_correlated_term_structure(request)
assert term.shape == (1_000, 4, 2)
assert np.array_equal(term[:, 2, 0], term[:, 3, 0])

print(
    "native Monte Carlo verified: "
    f"asian={premium:.6f} stderr={standard_error:.6f} "
    f"ou={ou.shape} correlated={paths.shape} term={term.shape}"
)
