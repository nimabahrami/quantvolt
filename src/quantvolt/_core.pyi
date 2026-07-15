"""Type stubs for the native Rust extension `quantvolt._core` (built by maturin)."""

import numpy as np
import numpy.typing as npt

def asian_monte_carlo(
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
    averaging_points: int,
    is_call: bool,
    geometric: bool,
    seed: int,
    path_count: int,
    antithetic: bool = True,
) -> tuple[float, float]:
    """Return ``(premium, standard_error)``. Native Rust MC kernel (Task 59).

    Driftless GBM under the forward measure with ``averaging_points`` equally spaced
    fixings; ``antithetic`` (default ``True``) draws ``(+eps, -eps)`` pairs (an odd
    ``path_count`` rounds up to the next even number when antithetic is on).
    ``premium = DF * mean(payoff)`` and ``standard_error =
    DF * std(payoff, ddof=1) / sqrt(n)``. Deterministic per ``seed`` (Req 11.2) — the
    stream is seeded-Rust-RNG reproducible, not NumPy-matching. Raises ``ValueError``
    for ``path_count < 1``, ``averaging_points < 1``, or non-finite float inputs.
    """
    ...

def simulate_ou(
    x0: float,
    kappa: float,
    mu: float,
    sigma: float,
    dt: float,
    steps: int,
    seed: int,
    path_count: int,
) -> npt.NDArray[np.float64]:
    """Simulate seeded Ornstein-Uhlenbeck (mean-reverting) paths (Task 59, GBM / OU).

    Euler recursion ``x_{t+dt} = x_t + kappa*(mu - x_t)*dt + sigma*sqrt(dt)*z``. Returns a
    ``float64`` array of shape ``(path_count, steps + 1)`` with ``x0`` in column 0.
    Deterministic per ``seed`` (Req 11.2) — seeded-Rust-RNG reproducible, not
    NumPy-matching. Inputs are validated by the ``numerics.monte_carlo`` wrapper.
    """
    ...

def simulate_correlated_forwards(
    z0: npt.NDArray[np.float64],
    drift: npt.NDArray[np.float64],
    cov: npt.NDArray[np.float64],
    steps: int,
    path_count: int,
    seed: int,
    antithetic: bool,
) -> npt.NDArray[np.float64]:
    """Correlated multi-commodity log-forward simulation (Appendix A, Task 62).

    ``z0``/``drift`` are length-``D`` vectors and ``cov`` a ``(D, D)`` symmetric PSD
    covariance (validated Python-side before this call). Returns a ``float64`` array of
    shape ``(n_paths, steps + 1, D)`` with record 0 equal to ``z0``. Increment law
    ``ΔZ = μ + L·ε`` with ``L = chol(cov)`` (eqs A.9-A.13); a zero-variance state index
    stays frozen (eq A.5). Antithetic variates draw ``(+ε, -ε)`` pairs (odd
    ``path_count`` rounds up). Deterministic per ``seed`` (Req 11.2). Raises
    ``ValueError`` on shape/finiteness violations or a non-PSD ``cov`` (defensive; the
    wrapper already gates PSD).
    """
    ...

def simulate_correlated_forwards_term(
    z0: npt.NDArray[np.float64],
    drift_steps: npt.NDArray[np.float64],
    covariance_steps: npt.NDArray[np.float64],
    active_steps: npt.NDArray[np.bool_],
    path_count: int,
    seed: int,
    antithetic: bool,
) -> npt.NDArray[np.float64]:
    """Simulate time-varying correlated state paths (Appendix A).

    ``drift_steps`` has shape ``(steps, D)``, ``covariance_steps`` has shape
    ``(steps, D, D)``, and ``active_steps`` has shape ``(steps, D)``. An inactive
    coordinate is held exactly fixed during that step, representing the advancing
    first-live-tenor index. Returns ``(n_paths, steps + 1, D)``. Raises ``ValueError``
    for invalid shapes, non-finite inputs, or non-PSD covariance matrices.
    """
    ...
