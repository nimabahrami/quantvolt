"""Monte Carlo VaR by full revaluation.

``monte_carlo_var`` measures the loss distribution of a book of energy positions by
simulating correlated forward-curve scenarios over a holding period under the
physical measure, then fully revaluing every position on every path with the
same pricing functions used for its base NPV: no delta/delta-gamma approximation. This
is the method of choice when a book's value is materially non-linear in the forwards
(options, tolling, storage): a linear parametric VaR would misstate the tails.

Risk specification
-------------------
* sign convention: loss ``L = -ΔNPV``; ``ΔNPV`` is the per-path revalued NPV minus
  the base NPV. VaR at confidence ``alpha`` is the ``alpha``-quantile of ``L`` (upper tail).
* holding period: a single caller-supplied horizon; risk factors are evolved once
  to that horizon (see "Simulation" below).
* confidence / measures reported: 95% and 99% VaR and 97.5% CVaR (expected
  shortfall) by default, matching the house quantile conventions in
  ``quantvolt.risk.engine``; each level is caller-overridable via ``confidences`` /
  ``cvar_confidence``.
* probability measure: physical (real-world) ``P``. The drift is required, is
  tagged with its ``quantvolt.numerics.risk_adjustment.DriftKind``, and a
  risk-neutral drift is rejected before any simulation.
* revaluation method: full revaluation via
  ``quantvolt.portfolio.valuation.value_portfolio`` and ``DEFAULT_PRICERS``.
* distribution method: correlated Monte Carlo.
* liquidity assumption: the holding period is the assumed liquidation/holding
  horizon; short-horizon mark-to-market VaR is only meaningful for liquid positions.
  Long-dated illiquid exposures should use CFaR / scenario analysis instead (see
  ``quantvolt.risk.cfar``).
* limitations: GBM (lognormal) factor dynamics: current forwards must be strictly
  positive, so this surface cannot model factors that trade through zero (negative power
  prices). Parameter/model risk in ``sigma``/``corr``/``physical_drift`` is the caller's;
  reported standard errors quantify sampling error only, not model error.

Request surface
---------------
``monte_carlo_var(positions, factor_model, physical_drift, holding_period, path_count, seed)``

* ``positions: Sequence[Position]``: the raw held instruments (not pre-priced); full
  revaluation reprices them from their definition on every path.
* ``factor_model: FactorModel``: bundles the base market state (its forward curves supply
  the current forwards / ``z0``, plus the discount curve and valuation date needed to
  revalue) with the GBM dynamics (``sigma``, ``corr``) over an explicit, ordered factor
  grid (see ``FactorModel``).
* ``physical_drift: TaggedDrift``: a per-factor physical log-drift rate vector tagged
  with its measure. Required, never defaulting; a ``RISK_NEUTRAL`` tag is rejected.
* ``holding_period: float``: the risk horizon in the same time unit as ``sigma`` and the
  drift rate (e.g. years). Must be ``> 0``.
* ``path_count: int``: number of simulated paths; ``< 1000`` raises before simulating.
* ``seed: int``: makes the whole computation reproducible.

Factor flattening convention
----------------------------
``FactorModel.factors`` is the ordered tuple of ``(commodity_id, delivery_period)``
labels; factor index ``i`` indexes ``z0``/``sigma`` row/column ``i`` and ``corr`` row/col
``i``. The labels are required to be strictly ascending by ``(commodity_id, period)``
(commodities lexicographically, periods chronologically) so for a dense
commodity x period grid this reproduces the row-major ``i·n_periods + j`` flattening used
by ``quantvolt.risk.engine.RiskEngine``.

Simulation and revaluation
--------------------------
The current forwards ``F_0`` are read from the factor model's curves and ``z0 = log F_0``
(GBM, hence ``F_0 > 0`` required). The horizon covariance is
``C = build_covariance(sigma, corr, holding_period)`` and the horizon drift is
``physical_drift.values · holding_period``: drift and variance both scale linearly with
the horizon. Because GBM increments are exact, a single step of length
``holding_period`` yields exactly the horizon distribution
``log F_T ~ N(z0 + drift·h, C)``, so ``steps = 1`` (faster, and exact: no discretisation
error). Paths default to iid (``antithetic=False``); enabling ``antithetic=True``
pairs paths as ``(+ε, -ε)`` (see ``quantvolt.numerics.monte_carlo``) for variance
reduction. The bootstrap standard-error estimator (see "Standard errors" below) adapts
its resampling unit to this choice, so both modes yield consistent SE estimates.

Each path's terminal forwards ``F_T = exp(Z_T)`` are written into fresh, bumped
``ForwardCurve`` objects (only the factor nodes move; the discount curve and valuation
date are held fixed, isolating market-move P&L). The portfolio is revalued with
``value_portfolio``; the path P&L is ``revalued_total_npv - base_total_npv``.

Standard errors
---------------
Each reported quantile carries a nonparametric bootstrap standard error:
``_BOOTSTRAP_REPLICATES`` resamples of the per-path loss array (drawn with replacement by
an RNG seeded deterministically from ``seed``), each recomputing the metric with the
identical estimator, and the sample standard deviation across replicates is the SE. The
bootstrap is chosen over the asymptotic order-statistic formula
``se(q_p) = sqrt(p(1-p)/n) / f̂(q_p)`` because it applies uniformly to both the VaR
quantiles and the CVaR tail-mean (the order-statistic formula covers only quantiles and
needs a separate delta-method formula for expected shortfall) and it avoids a fragile
density estimate ``f̂``. Being proportional to ``1/sqrt(n)`` it shrinks as ``path_count``
grows, and being seeded from ``seed`` it preserves determinism.

The resampling **unit** matches the simulation mode: with the default ``antithetic=False``
each replicate resamples individual path losses (the classic iid bootstrap). With
``antithetic=True`` the simulator's ``(+ε, -ε)`` pairs sit at adjacent indices
``(2k, 2k+1)`` and are strongly (negatively) correlated by construction — resampling
individual losses in that case would treat the pair as independent and bias the SE
(within-pair loss correlation as strong as -0.97 has been observed). Each replicate
instead resamples whole pairs with replacement, preserving that dependence structure
(``bootstrap_replicates >= 2`` is required so a sample standard deviation, ``ddof=1``,
is defined across replicates).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .._validation import require_integer_at_least, require_positive
from ..exceptions import ValidationError
from ..models.curve import CurveNode, ForwardCurve
from ..models.schedule import DeliveryPeriod
from ..numerics.monte_carlo import build_covariance, simulate_correlated_forwards
from ..numerics.risk_adjustment import DriftKind, require_physical_drift
from ..portfolio.model import Portfolio, Position
from ..portfolio.valuation import MarketData, value_portfolio
from ._levels import DEFAULT_CONFIDENCES, DEFAULT_CVAR_CONFIDENCE
from ._levels import loss_metrics as _loss_metrics
from ._levels import validate_confidence_pair as _validate_confidence_pair
from ._levels import validate_single_confidence as _validate_single_confidence

#: Minimum path count (Req 15.5). Requests below this raise before any simulation.
_MIN_PATH_COUNT = 1000
#: One horizon step: GBM increments are exact, so a single step of length
#: ``holding_period`` reproduces the horizon distribution exactly (no discretisation).
_STEPS = 1
#: iid paths (see the module docstring) so bootstrap standard errors are consistent.
_ANTITHETIC = False
#: Bootstrap resamples for the quantile standard errors.
_BOOTSTRAP_REPLICATES = 500
#: Salt combined with ``seed`` to give the bootstrap its own deterministic RNG stream,
#: decoupled from the native simulation stream.
_BOOTSTRAP_SALT = 0x6D_63_76_61_72  # "mcvar"

# DEFAULT_CONFIDENCES (95% / 99%) and DEFAULT_CVAR_CONFIDENCE (97.5%) are re-exported
# public names, sourced from the shared ``risk/_levels.py`` helper (see its module
# docstring) rather than duplicated here.

FactorLabel = tuple[str, DeliveryPeriod]


@dataclass(frozen=True, slots=True, eq=False)
class FactorModel:
    """Base market state plus GBM dynamics over an ordered ``(commodity, period)`` grid.

    Fields:
        market_data: the current/base market state. Its ``forward_curves`` supply the
            current forwards (``z0 = log F_0``) for every factor, and its
            ``discount_curve`` / ``valuation_date`` provide the static revaluation context.
        factors: ordered factor labels; strictly ascending by ``(commodity_id, period)``
            (see the module docstring for the flattening convention). Factor ``i`` indexes
            ``sigma[i]`` and row/column ``i`` of ``corr``.
        sigma: per-factor instantaneous volatility (length ``D``); ``0`` marks an expired,
            frozen factor. Deep numeric validation lives in ``build_covariance``.
        corr: the ``(D, D)`` cross-factor correlation matrix ``R``.

    ``sigma``/``corr`` are snapshot to contiguous ``float64`` at construction. Equality is
    defined explicitly (``eq=False``) so the array fields compare by value to a single
    ``bool`` rather than the element-wise array a generated ``__eq__`` would yield.
    """

    market_data: MarketData
    factors: tuple[FactorLabel, ...]
    sigma: npt.NDArray[np.float64]
    corr: npt.NDArray[np.float64]

    def __post_init__(self) -> None:
        if len(self.factors) == 0:
            raise ValidationError("factor_model.factors must be non-empty")
        for index in range(1, len(self.factors)):
            if self.factors[index - 1] >= self.factors[index]:
                raise ValidationError(
                    "factor_model.factors must be strictly ascending by "
                    "(commodity_id, period) with no duplicates; offending pair at index "
                    f"{index - 1}: {self.factors[index - 1]!r} is not before "
                    f"{self.factors[index]!r}"
                )
        d = len(self.factors)
        sigma = np.ascontiguousarray(self.sigma, dtype=np.float64)
        corr = np.ascontiguousarray(self.corr, dtype=np.float64)
        if sigma.shape != (d,):
            raise ValidationError(
                f"factor_model.sigma must have shape ({d},) to match the {d} factors, "
                f"got {sigma.shape}"
            )
        if corr.shape != (d, d):
            raise ValidationError(
                f"factor_model.corr must have shape ({d}, {d}) to match the {d} factors, "
                f"got {corr.shape}"
            )
        object.__setattr__(self, "sigma", sigma)
        object.__setattr__(self, "corr", corr)
        # Every factor must resolve to a curve node so revaluation can price it; a missing
        # commodity/period raises the usual EnergyQuantError here, at construction.
        for commodity_id, period in self.factors:
            self.market_data.curve_for(commodity_id).price_at(period)

    def current_forwards(self) -> npt.NDArray[np.float64]:
        """Current forward level ``F_0`` per factor, in factor order (length ``D``)."""
        market_data = self.market_data
        return np.array(
            [
                market_data.curve_for(commodity_id).price_at(period)
                for commodity_id, period in self.factors
            ],
            dtype=np.float64,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FactorModel):
            return NotImplemented
        return (
            self.market_data == other.market_data
            and self.factors == other.factors
            and np.array_equal(self.sigma, other.sigma)
            and np.array_equal(self.corr, other.corr)
        )


@dataclass(frozen=True, slots=True, eq=False)
class TaggedDrift:
    """A drift vector tagged with the probability measure it belongs to.

    Used for the required ``physical_drift`` argument: routing the tag through
    ``quantvolt.numerics.risk_adjustment.require_physical_drift`` rejects a
    ``RISK_NEUTRAL`` drift before any simulation runs. ``values``
    are per-factor physical log-drift rates (per unit of the holding period's time
    unit). Snapshot to contiguous ``float64``; equality is value-based (``eq=False``).
    """

    values: npt.NDArray[np.float64]
    kind: DriftKind

    def __post_init__(self) -> None:
        values = np.ascontiguousarray(self.values, dtype=np.float64)
        if values.ndim != 1:
            raise ValidationError(f"TaggedDrift.values must be 1-D, got shape {values.shape}")
        if not bool(np.all(np.isfinite(values))):
            raise ValidationError("TaggedDrift.values must be finite")
        object.__setattr__(self, "values", values)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaggedDrift):
            return NotImplemented
        return self.kind == other.kind and np.array_equal(self.values, other.values)


@dataclass(frozen=True, slots=True)
class McVaRResult:
    """Full-revaluation Monte Carlo VaR outcome.

    ``var_95`` / ``var_99`` are the ``confidences`` percentiles (95th / 99th by default)
    of the loss distribution ``L = -ΔNPV``; ``cvar_975`` is the mean loss at or above the
    ``cvar_confidence`` percentile (97.5th by default, inclusive tail, matching
    ``quantvolt.risk.engine.RiskEngine``). The field names are fixed regardless of
    the levels supplied. Each carries a
    nonparametric bootstrap standard error (``*_se``). ``path_count`` is the number of
    simulated paths the metrics are computed over, and ``holding_period`` / ``seed`` are
    echoed for reproducibility.
    """

    var_95: float
    var_99: float
    cvar_975: float
    var_95_se: float
    var_99_se: float
    cvar_975_se: float
    path_count: int
    holding_period: float
    seed: int


def _bootstrap_standard_errors(
    losses: npt.NDArray[np.float64],
    seed: int,
    var_lo_pct: float,
    var_hi_pct: float,
    cvar_pct: float,
    bootstrap_replicates: int,
    *,
    antithetic: bool,
) -> tuple[float, float, float]:
    """Bootstrap SEs for ``(var_95, var_99, cvar_975)`` (see the module docstring).

    When ``antithetic`` is ``False`` (the default simulation mode), paths are iid so
    each replicate resamples individual losses with replacement — the classic
    nonparametric bootstrap.

    When ``antithetic`` is ``True``, ``losses`` holds the simulator's ``(+ε, -ε)``
    pairs at adjacent indices ``(2k, 2k+1)`` (see ``quantvolt.numerics.monte_carlo``);
    resampling individual losses would treat within-pair losses as independent when
    they are in fact strongly (negatively) correlated by construction, biasing the
    bootstrap SE. Each replicate instead resamples whole pairs with replacement:
    ``losses`` is reshaped to ``(n_pairs, 2)``, pair indices are drawn, and the result is
    flattened back to a loss vector of the original length, which preserves the
    within-pair dependence structure the antithetic construction introduces.
    """
    n = int(losses.shape[0])
    rng = np.random.default_rng([int(seed), _BOOTSTRAP_SALT])
    replicates = np.empty((bootstrap_replicates, 3), dtype=np.float64)
    if antithetic:
        if n % 2 != 0:
            raise ValidationError(
                "losses must have an even length to resample (+eps, -eps) pairs under "
                f"antithetic=True, got {n}"
            )
        pairs = losses.reshape(n // 2, 2)
        n_pairs = pairs.shape[0]
        for row in range(bootstrap_replicates):
            resample = pairs[rng.integers(0, n_pairs, size=n_pairs)].reshape(-1)
            replicates[row, 0], replicates[row, 1], replicates[row, 2] = _loss_metrics(
                resample, var_lo_pct, var_hi_pct, cvar_pct
            )
    else:
        for row in range(bootstrap_replicates):
            resample = losses[rng.integers(0, n, size=n)]
            replicates[row, 0], replicates[row, 1], replicates[row, 2] = _loss_metrics(
                resample, var_lo_pct, var_hi_pct, cvar_pct
            )
    ses = replicates.std(axis=0, ddof=1)
    return float(ses[0]), float(ses[1]), float(ses[2])


def _bumped_market_data(
    base: MarketData,
    index_by_label: dict[FactorLabel, int],
    terminal_forwards: npt.NDArray[np.float64],
) -> MarketData:
    """Rebuild ``base`` with factor nodes moved to their per-path terminal forwards.

    Only nodes whose ``(commodity_id, period)`` is a factor are bumped; any other node
    keeps its base price. The discount curve and valuation date are held fixed, so the
    revaluation isolates forward-market-move P&L (no theta/carry).
    """
    new_curves: dict[str, ForwardCurve] = {}
    for commodity_id, curve in base.forward_curves.items():
        new_nodes = tuple(
            CurveNode(
                period=node.period,
                price=(
                    float(terminal_forwards[index])
                    if (index := index_by_label.get((commodity_id, node.period))) is not None
                    else node.price
                ),
                status=node.status,
            )
            for node in curve.nodes
        )
        new_curves[commodity_id] = ForwardCurve(
            commodity=curve.commodity, market_date=curve.market_date, nodes=new_nodes
        )
    return MarketData(
        forward_curves=new_curves,
        discount_curve=base.discount_curve,
        valuation_date=base.valuation_date,
    )


def monte_carlo_var(
    positions: Sequence[Position],
    factor_model: FactorModel,
    physical_drift: TaggedDrift,
    holding_period: float,
    path_count: int,
    seed: int,
    *,
    confidences: Sequence[float] = DEFAULT_CONFIDENCES,
    cvar_confidence: float = DEFAULT_CVAR_CONFIDENCE,
    antithetic: bool = _ANTITHETIC,
    bootstrap_replicates: int = _BOOTSTRAP_REPLICATES,
    min_path_count: int = _MIN_PATH_COUNT,
) -> McVaRResult:
    """Full-revaluation Monte Carlo VaR/CVaR over a holding period.

    See the module docstring for the request surface, the factor flattening convention,
    the simulation/revaluation mechanics, the sign convention, and the standard-error
    estimator. In short: simulate correlated GBM forward scenarios to the horizon under
    the physical drift, fully revalue the book on each path, and take loss quantiles.

    Args:
        positions: raw held instruments (repriced from their definition each path).
        factor_model: base market state + GBM dynamics over the factor grid.
        physical_drift: required, measure-tagged per-factor log-drift rates.
        holding_period: risk horizon (> 0), in ``sigma``'s time unit.
        path_count: simulated paths (``>= min_path_count``).
        seed: reproducibility seed.
        confidences: The two VaR confidence levels (fractions in ``(0, 1)``, matching
            ``quantvolt.risk.parametric_var``'s convention) reported as ``var_95`` /
            ``var_99``; defaults to ``(0.95, 0.99)``.
        cvar_confidence: The CVaR confidence level (a fraction in ``(0, 1)``) reported
            as ``cvar_975``; defaults to ``0.975``.
        antithetic: Whether the simulation uses antithetic-variate path pairing;
            defaults to ``False`` (iid paths). The bootstrap SE estimator resamples
            individual paths when ``False`` and whole ``(+eps, -eps)`` pairs when
            ``True``, so both modes yield consistent SE estimates; see the module
            docstring.
        bootstrap_replicates: Number of bootstrap resamples for the quantile standard
            errors; defaults to ``500``. Must be an integer ``>= 2`` (a sample standard
            deviation across replicates needs at least 2 of them).
        min_path_count: Minimum accepted ``path_count``; defaults to ``1000``.

    Returns:
        A ``McVaRResult`` with VaR/CVaR at the requested confidence levels
        (reported as ``var_95``/``var_99``/``cvar_975`` regardless of the levels used)
        and bootstrap SEs.

    Raises:
        ValidationError: if ``path_count < min_path_count`` (raised before simulating);
            if ``holding_period <= 0``; if ``physical_drift`` is not tagged
            physical; if ``physical_drift.values`` does not match the factor
            count; if any current forward is not strictly positive (GBM requires
            ``F_0 > 0``); if ``confidences`` does not contain exactly 2 strictly
            ascending levels in ``(0, 1)``; if ``cvar_confidence`` is not in ``(0, 1)``;
            if ``bootstrap_replicates`` is not an integer ``>= 2`` (a standard deviation
            needs at least 2 replicates); or if ``min_path_count`` is not ``>= 1``.
    """
    require_positive("min_path_count", min_path_count)
    # Reject an under-sampled request before any simulation prep.
    if path_count < min_path_count:
        raise ValidationError(
            f"path_count must be >= {min_path_count} for Monte Carlo VaR, got {path_count}"
        )
    require_positive("holding_period", holding_period)
    # A risk-neutral drift is rejected here, before simulating.
    require_physical_drift(physical_drift.kind, "physical_drift")
    var_lo_pct, var_hi_pct = _validate_confidence_pair(confidences)
    cvar_pct = _validate_single_confidence(cvar_confidence, name="cvar_confidence")
    # A bootstrap standard deviation needs >= 2 replicates (ddof=1); a single replicate
    # silently produced a NaN SE before this check existed.
    require_integer_at_least("bootstrap_replicates", bootstrap_replicates, 2)

    n_factors = len(factor_model.factors)
    if physical_drift.values.shape != (n_factors,):
        raise ValidationError(
            f"physical_drift.values must have shape ({n_factors},) to match the "
            f"{n_factors} factors, got {physical_drift.values.shape}"
        )

    forwards = factor_model.current_forwards()
    if not bool(np.all(forwards > 0.0)):
        bad = [
            (label, float(value))
            for label, value in zip(factor_model.factors, forwards, strict=True)
            if not value > 0.0
        ]
        raise ValidationError(
            "every current forward must be strictly positive for lognormal (GBM) "
            f"simulation; non-positive forwards at {bad}"
        )

    portfolio = Portfolio(positions=tuple(positions))
    base_npv = value_portfolio(portfolio, factor_model.market_data).total_npv

    z0 = np.log(forwards)
    covariance = build_covariance(factor_model.sigma, factor_model.corr, holding_period)
    horizon_drift = physical_drift.values * holding_period
    paths = simulate_correlated_forwards(
        z0,
        horizon_drift,
        covariance,
        steps=_STEPS,
        path_count=path_count,
        seed=seed,
        antithetic=antithetic,
    )
    terminal_forwards = np.exp(paths[:, -1, :])  # (n_paths, D)

    index_by_label = {label: index for index, label in enumerate(factor_model.factors)}
    base_market_data = factor_model.market_data
    n_paths = int(terminal_forwards.shape[0])
    pnl = np.empty(n_paths, dtype=np.float64)
    for path in range(n_paths):
        market_data = _bumped_market_data(base_market_data, index_by_label, terminal_forwards[path])
        pnl[path] = value_portfolio(portfolio, market_data).total_npv - base_npv

    losses = -pnl
    var_95, var_99, cvar_975 = _loss_metrics(losses, var_lo_pct, var_hi_pct, cvar_pct)
    var_95_se, var_99_se, cvar_975_se = _bootstrap_standard_errors(
        losses, seed, var_lo_pct, var_hi_pct, cvar_pct, bootstrap_replicates, antithetic=antithetic
    )

    return McVaRResult(
        var_95=var_95,
        var_99=var_99,
        cvar_975=cvar_975,
        var_95_se=var_95_se,
        var_99_se=var_99_se,
        cvar_975_se=cvar_975_se,
        path_count=n_paths,
        holding_period=float(holding_period),
        seed=seed,
    )
