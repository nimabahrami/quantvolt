"""Polished-spec extension correctness properties (design Properties 67-74; Task 84).

Covers transport-right payoff/PV (Property 67) and bidirectional subadditivity/constraints
(Property 68), the Schwartz-Smith forward closed form and long-dated limit (Property 69)
and its calibration round-trip (Property 70), the multifactor initial-curve match /
martingale (Property 71) and induced-correlation bounds / PSD / option-variance matching
(Property 72), and the outage reliability KPIs (Properties 73-74).

Deterministic properties (67-69, 72, 73-74) run the full 100-example profile. Property 70
(a Kalman-filter MLE) is a single expensive example; Property 71 (correlated MC) uses a
reduced example count — both noted at the test.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.curvemodels.multifactor import (
    MultifactorForwardModel,
    cumulative_covariance,
    forward_matching_residual,
    induced_correlation,
    induced_covariance,
    matches_option_variance,
    risk_neutral_drift,
    simulate_forwards,
)
from quantvolt.curvemodels.schwartz_smith import (
    SchwartzSmithParams,
    calibrate,
    forward_curve,
    log_forward_curve,
)
from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.market.outages import (
    OutageDataset,
    OutageRecord,
    OutageStatus,
    OutageType,
    availability_factor,
    equivalent_availability_factor,
    forced_outage_rate,
    mtbf,
    outage_frequency,
)
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import TransmissionRight, TransportDirection
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.pricing.transmission_right import value_transport_right
from strategies import correlation_matrices

# ---------------------------------------------------------------------------------------
# Properties 67-68: transport rights.
# ---------------------------------------------------------------------------------------

_HUB_A = CommodityConfig("HUB_A", "EUR/MWh", Hub("HUB_A", "EEX", "EUR/MWh"))
_HUB_B = CommodityConfig("HUB_B", "EUR/MWh", Hub("HUB_B", "EEX", "EUR/MWh"))
_REF = date(2026, 7, 1)

_TransportCase = tuple[
    list[DeliveryPeriod], dict[DeliveryPeriod, float], dict[DeliveryPeriod, float], float, float
]


@st.composite
def _transport_case(draw: st.DrawFn, *, positive: bool = False) -> _TransportCase:
    months = sorted(draw(st.sets(st.integers(min_value=1, max_value=12), min_size=1, max_size=4)))
    periods = [DeliveryPeriod(2027, m) for m in months]
    prices = (
        st.floats(min_value=1.0, max_value=100.0)
        if positive
        else st.floats(min_value=-50.0, max_value=150.0)
    )
    prices_a = {period: draw(prices) for period in periods}
    prices_b = {period: draw(prices) for period in periods}
    tariff = draw(st.floats(min_value=0.0, max_value=20.0))
    quantity = draw(st.floats(min_value=0.0, max_value=100.0))
    return periods, prices_a, prices_b, tariff, quantity


def _make_curve(commodity: CommodityConfig, prices: Mapping[DeliveryPeriod, float]) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=_REF,
        nodes=tuple(
            CurveNode(period, float(price), "observed") for period, price in sorted(prices.items())
        ),
    )


def _make_discount(data: st.DataObject, periods: Sequence[DeliveryPeriod]) -> DiscountCurve:
    factors = tuple(data.draw(st.floats(min_value=0.1, max_value=1.0)) for _ in periods)
    return DiscountCurve(
        reference_date=_REF,
        tenors=tuple(period.last_day for period in periods),
        factors=factors,
    )


# Feature: power-energy-quant-analysis, Property 67: Transport-Right Payoff and PV
@given(case=_transport_case(), data=st.data())
@settings(max_examples=100)
def test_property_67_payoff_and_discounted_pv(case: _TransportCase, data: st.DataObject) -> None:
    periods, prices_a, prices_b, tariff, quantity = case
    curve_a = _make_curve(_HUB_A, prices_a)
    curve_b = _make_curve(_HUB_B, prices_b)
    discount = _make_discount(data, periods)
    right = TransmissionRight(
        origin="HUB_A",
        destination="HUB_B",
        tariff=tariff,
        quantity=quantity,
        schedule=DeliverySchedule(periods=tuple(periods)),
    )
    result = value_transport_right(right, curve_a, curve_b, discount)

    expected_pv = 0.0
    assert len(result.per_period) == len(periods)
    for pv, period in zip(result.per_period, periods, strict=True):
        spread = prices_b[period] - prices_a[period] - tariff
        payoff = quantity * max(spread, 0.0)
        df = discount.discount_factor(period.last_day)
        assert pv.payoff == pytest.approx(payoff, rel=1e-9, abs=1e-9)
        assert pv.intrinsic == pytest.approx(df * payoff, rel=1e-9, abs=1e-9)
        assert pv.extrinsic == 0.0  # no vols -> intrinsic-only path
        expected_pv += df * payoff
    assert result.intrinsic == pytest.approx(expected_pv, rel=1e-9, abs=1e-9)
    assert result.total == pytest.approx(result.intrinsic, rel=1e-12, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 67: Transport-Right Payoff and PV
def test_property_67_no_shared_period_raises() -> None:
    curve_a = _make_curve(_HUB_A, {DeliveryPeriod(2027, 1): 30.0})
    curve_b = _make_curve(_HUB_B, {DeliveryPeriod(2027, 6): 40.0})  # disjoint period
    discount = DiscountCurve(
        reference_date=_REF,
        tenors=(DeliveryPeriod(2027, 1).last_day, DeliveryPeriod(2027, 6).last_day),
        factors=(0.99, 0.97),
    )
    right = TransmissionRight(
        origin="HUB_A",
        destination="HUB_B",
        tariff=1.0,
        quantity=10.0,
        schedule=DeliverySchedule(periods=(DeliveryPeriod(2027, 1),)),
    )
    with pytest.raises(InsufficientDataError, match="share no delivery period"):
        value_transport_right(right, curve_a, curve_b, discount)


# Feature: power-energy-quant-analysis, Property 68: Bidirectional Subadditivity and
# Constraints
# A bidirectional right takes the best of {A->B, B->A, no-flow} each period, so its value
# never exceeds the sum of the two matched one-way rights (intrinsic-only and with vols).
@given(case=_transport_case(positive=True), data=st.data())
@settings(max_examples=100)
def test_property_68_bidirectional_is_subadditive(
    case: _TransportCase, data: st.DataObject
) -> None:
    periods, prices_a, prices_b, tariff_ab, quantity = case
    tariff_ba = data.draw(st.floats(min_value=0.0, max_value=20.0))
    curve_a, curve_b = _make_curve(_HUB_A, prices_a), _make_curve(_HUB_B, prices_b)
    discount = _make_discount(data, periods)
    schedule = DeliverySchedule(periods=tuple(periods))
    use_vols = data.draw(st.booleans())
    vols = (data.draw(st.floats(0.1, 0.8)), data.draw(st.floats(0.1, 0.8))) if use_vols else None
    correlation = data.draw(st.floats(-0.9, 0.9)) if use_vols else None

    bidir = TransmissionRight(
        "HUB_A",
        "HUB_B",
        tariff_ab,
        quantity,
        schedule,
        direction=TransportDirection.BIDIRECTIONAL,
        reverse_tariff=tariff_ba,
    )
    a_to_b = TransmissionRight(
        "HUB_A", "HUB_B", tariff_ab, quantity, schedule, direction=TransportDirection.A_TO_B
    )
    b_to_a = TransmissionRight(
        "HUB_A", "HUB_B", tariff_ba, quantity, schedule, direction=TransportDirection.B_TO_A
    )
    kwargs = {"vols": vols, "correlation": correlation}
    v_bidir = value_transport_right(bidir, curve_a, curve_b, discount, **kwargs).total
    v_ab = value_transport_right(a_to_b, curve_a, curve_b, discount, **kwargs).total
    v_ba = value_transport_right(b_to_a, curve_a, curve_b, discount, **kwargs).total
    assert v_bidir <= v_ab + v_ba + 1e-9


# Feature: power-energy-quant-analysis, Property 68: Bidirectional Subadditivity and
# Constraints
# The delivered quantity honours the loss factor: intrinsic scales by exactly (1 - loss).
@given(case=_transport_case(), loss=st.floats(min_value=0.0, max_value=0.9), data=st.data())
@settings(max_examples=100)
def test_property_68_loss_scales_delivered_quantity(
    case: _TransportCase, loss: float, data: st.DataObject
) -> None:
    periods, prices_a, prices_b, tariff, quantity = case
    curve_a, curve_b = _make_curve(_HUB_A, prices_a), _make_curve(_HUB_B, prices_b)
    discount = _make_discount(data, periods)
    schedule = DeliverySchedule(periods=tuple(periods))
    with_loss = TransmissionRight("HUB_A", "HUB_B", tariff, quantity, schedule, loss=loss)
    no_loss = TransmissionRight("HUB_A", "HUB_B", tariff, quantity, schedule, loss=0.0)
    r_loss = value_transport_right(with_loss, curve_a, curve_b, discount)
    r_no = value_transport_right(no_loss, curve_a, curve_b, discount)
    assert r_loss.intrinsic == pytest.approx((1.0 - loss) * r_no.intrinsic, rel=1e-9, abs=1e-9)


# Feature: power-energy-quant-analysis, Property 68: Bidirectional Subadditivity and
# Constraints
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"quantity": -1.0}, "quantity"),
        ({"loss": 1.0}, "loss"),
        ({"tariff": -1.0}, "tariff"),
    ],
)
def test_property_68_invalid_constructor_arguments_raise(
    kwargs: Mapping[str, float], match: str
) -> None:
    base: dict[str, object] = {
        "origin": "HUB_A",
        "destination": "HUB_B",
        "tariff": 5.0,
        "quantity": 10.0,
        "schedule": DeliverySchedule(periods=(DeliveryPeriod(2027, 1),)),
    }
    base.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        TransmissionRight(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------
# Properties 69-70: Schwartz-Smith.
# ---------------------------------------------------------------------------------------


@st.composite
def _ss_params(draw: st.DrawFn) -> SchwartzSmithParams:
    return SchwartzSmithParams(
        kappa=draw(st.floats(min_value=0.1, max_value=3.0)),
        sigma_chi=draw(st.floats(min_value=0.05, max_value=0.6)),
        sigma_xi=draw(st.floats(min_value=0.05, max_value=0.6)),
        mu_xi=draw(st.floats(min_value=-0.2, max_value=0.2)),
        rho=draw(st.floats(min_value=-0.9, max_value=0.9)),
        lambda_chi=draw(st.floats(min_value=-0.2, max_value=0.2)),
        lambda_xi=draw(st.floats(min_value=-0.2, max_value=0.2)),
    )


def _a_tau_reference(params: SchwartzSmithParams, tau: float) -> float:
    """Independent A(tau) straight off the boxed §31.2 equation (plain ``math.exp``)."""
    k = params.kappa
    return (
        (params.mu_xi - params.lambda_xi) * tau
        - (params.lambda_chi / k) * (1.0 - math.exp(-k * tau))
        + 0.5
        * (
            params.sigma_chi**2 / (2.0 * k) * (1.0 - math.exp(-2.0 * k * tau))
            + params.sigma_xi**2 * tau
            + 2.0 * params.rho * params.sigma_chi * params.sigma_xi / k * (1.0 - math.exp(-k * tau))
        )
    )


# Feature: power-energy-quant-analysis, Property 69: Schwartz-Smith Forward-Curve Closed
# Form
@given(
    params=_ss_params(),
    chi=st.floats(min_value=-2.0, max_value=2.0),
    xi=st.floats(min_value=0.0, max_value=5.0),
    data=st.data(),
)
@settings(max_examples=100)
def test_property_69_reproduces_the_closed_form(
    params: SchwartzSmithParams, chi: float, xi: float, data: st.DataObject
) -> None:
    taus = sorted(
        data.draw(
            st.lists(st.floats(min_value=0.05, max_value=5.0), min_size=1, max_size=5, unique=True)
        )
    )
    tenors = np.array(taus, dtype=np.float64)  # t = 0, so maturities T equal tau
    got = forward_curve(params, chi, xi, 0.0, tenors)
    expected = [
        math.exp(math.exp(-params.kappa * tau) * chi + xi + _a_tau_reference(params, tau))
        for tau in taus
    ]
    assert got == pytest.approx(expected, rel=1e-9)


# Feature: power-energy-quant-analysis, Property 69: Schwartz-Smith Forward-Curve Closed
# Form
# As kappa*tau -> inf the short-factor loading e^(-kappa*tau) -> 0, so a far-dated forward
# is (to machine precision) independent of the short factor chi.
@given(params=_ss_params(), xi=st.floats(min_value=0.0, max_value=5.0))
@settings(max_examples=100)
def test_property_69_long_dated_forward_insensitive_to_chi(
    params: SchwartzSmithParams, xi: float
) -> None:
    far = np.array([40.0 / params.kappa], dtype=np.float64)  # kappa*tau = 40 -> loading ~4e-18
    with_high = log_forward_curve(params, 5.0, xi, 0.0, far)
    with_low = log_forward_curve(params, -5.0, xi, 0.0, far)
    assert abs(float(with_high[0] - with_low[0])) < 1e-9


_SS_TRUE = SchwartzSmithParams(
    kappa=1.2, sigma_chi=0.30, sigma_xi=0.15, mu_xi=0.02, rho=-0.3, lambda_chi=0.05, lambda_xi=0.01
)


def _synthetic_history(
    params: SchwartzSmithParams, n_obs: int, tau: npt.NDArray[np.float64], dt: float, seed: int
) -> npt.NDArray[np.float64]:
    """Observed forward-curve history from known params (P-latent, Q-priced cross-section)."""
    rng = np.random.default_rng(seed)
    k = params.kappa
    decay = math.exp(-k * dt)
    var_chi = params.sigma_chi**2 * (1.0 - math.exp(-2.0 * k * dt)) / (2.0 * k)
    var_xi = params.sigma_xi**2 * dt
    cov = params.rho * params.sigma_chi * params.sigma_xi * (1.0 - decay) / k
    chol = np.linalg.cholesky(np.array([[var_chi, cov], [cov, var_xi]]))
    chi = np.zeros(n_obs)
    xi = np.zeros(n_obs)
    chi[0], xi[0] = 0.2, 3.0
    for n in range(1, n_obs):
        w = chol @ rng.standard_normal(2)
        chi[n] = decay * chi[n - 1] + w[0]  # P-dynamics: no risk-premium drift
        xi[n] = xi[n - 1] + params.mu_xi * dt + w[1]
    log_curves = np.array(
        [log_forward_curve(params, chi[n], xi[n], 0.0, tau) for n in range(n_obs)]
    ) + 0.005 * rng.standard_normal((n_obs, tau.size))
    return np.exp(log_curves)


# Feature: power-energy-quant-analysis, Property 70: Schwartz-Smith Calibration Round-Trip
# Single expensive example (Kalman-filter MLE over 90 weekly curves x 5 tenors): the
# identified parameters are recovered within the documented loose tolerances and the
# diagnostics are reported. Not a hypothesis run — one calibration is already seconds.
def test_property_70_calibration_recovers_parameters_and_reports_diagnostics() -> None:
    tau = np.linspace(1.0 / 12.0, 3.0, 5)
    observed = _synthetic_history(_SS_TRUE, n_obs=90, tau=tau, dt=1.0 / 52.0, seed=11)
    fitted, diagnostics = calibrate(observed, tau, dt=1.0 / 52.0)

    assert fitted.kappa == pytest.approx(_SS_TRUE.kappa, rel=0.15)
    assert fitted.sigma_chi == pytest.approx(_SS_TRUE.sigma_chi, rel=0.20)
    assert fitted.sigma_xi == pytest.approx(_SS_TRUE.sigma_xi, rel=0.25)
    assert fitted.rho == pytest.approx(_SS_TRUE.rho, abs=0.20)
    assert fitted.mu_xi_star == pytest.approx(_SS_TRUE.mu_xi_star, abs=0.03)

    assert diagnostics.converged
    assert math.isfinite(diagnostics.log_likelihood)
    assert diagnostics.n_iterations > 0
    assert "power" in diagnostics.lognormal_power_caveat.lower()
    assert math.isfinite(diagnostics.initial_curve_max_abs_mismatch)


# ---------------------------------------------------------------------------------------
# Properties 71-72: multifactor forward model.
# ---------------------------------------------------------------------------------------


@st.composite
def _loadings_arrays(draw: st.DrawFn) -> npt.NDArray[np.float64]:
    n_steps = draw(st.integers(min_value=1, max_value=3))
    n_factors = draw(st.integers(min_value=1, max_value=4))
    n_tenors = draw(st.integers(min_value=2, max_value=4))
    entries = st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)
    array = draw(
        st.lists(
            st.lists(
                st.lists(entries, min_size=n_tenors, max_size=n_tenors),
                min_size=n_factors,
                max_size=n_factors,
            ),
            min_size=n_steps,
            max_size=n_steps,
        )
    )
    return np.array(array, dtype=np.float64)


# Feature: power-energy-quant-analysis, Property 71: Multifactor Initial-Curve Matching and
# Martingale
# The model reproduces F(0, T) at t = 0 exactly (record 0 of every path) and carries no
# Q-drift in F: the simulated E[F(t, T)] converges to F(0, T). Reduced examples (each draws
# 40k paths through the Rust kernel).
@given(corr=correlation_matrices(min_dim=2, max_dim=3), data=st.data())
@settings(max_examples=6, deadline=None)
def test_property_71_initial_curve_match_and_martingale(
    corr: npt.NDArray[np.float64], data: st.DataObject
) -> None:
    n = int(corr.shape[0])
    vols = np.array(
        data.draw(st.lists(st.floats(min_value=0.1, max_value=0.6), min_size=n, max_size=n)),
        dtype=np.float64,
    )
    model = MultifactorForwardModel.from_target_correlation(corr, vols, n_steps=1, dt=1.0 / 12.0)
    f0 = np.array(
        data.draw(st.lists(st.floats(min_value=10.0, max_value=100.0), min_size=n, max_size=n)),
        dtype=np.float64,
    )
    paths = simulate_forwards(model, f0, steps=1, path_count=40_000, seed=7)
    assert paths[:, 0, :] == pytest.approx(np.broadcast_to(f0, paths[:, 0, :].shape), rel=1e-9)
    mean_terminal = paths[:, -1, :].mean(axis=0)
    assert mean_terminal == pytest.approx(f0, rel=0.05)


# Feature: power-energy-quant-analysis, Property 71: Multifactor Initial-Curve Matching and
# Martingale
@given(loadings=_loadings_arrays())
@settings(max_examples=100)
def test_property_71_risk_neutral_drift_is_the_ito_correction(
    loadings: npt.NDArray[np.float64],
) -> None:
    model = MultifactorForwardModel(loadings, dt=1.0 / 12.0)
    cov = induced_covariance(model, 0) * model.dt
    drift = risk_neutral_drift(cov)
    assert drift == pytest.approx(-0.5 * np.diag(cov), rel=1e-12, abs=1e-15)
    # Forward-matching residual is exactly zero at t = 0 (curve reproduced by construction).
    f0 = np.full(model.n_tenors, 50.0)
    assert forward_matching_residual(f0, f0) == pytest.approx(np.zeros(model.n_tenors), abs=0.0)


# Feature: power-energy-quant-analysis, Property 72: Induced Correlation Bounds and PSD
@given(loadings=_loadings_arrays())
@settings(max_examples=100)
def test_property_72_induced_correlation_bounds_and_psd(
    loadings: npt.NDArray[np.float64],
) -> None:
    model = MultifactorForwardModel(loadings, dt=1.0 / 12.0)
    cov = induced_covariance(model, 0)
    corr = induced_correlation(model, 0)
    variances = np.diag(cov)

    assert float(np.max(np.abs(corr))) <= 1.0 + 1e-9
    for i in range(model.n_tenors):
        if variances[i] > 0.0:
            assert corr[i, i] == pytest.approx(1.0, abs=1e-9)
        else:
            # Zero-variance correlation is mathematically undefined, but the public
            # API deliberately uses a unit-diagonal convention so the matrix remains
            # valid input to build_covariance; off-diagonal entries stay zero.
            assert corr[i, i] == 1.0
    # Induced covariance and the assembled cumulative covariance Gamma are both PSD.
    assert float(np.linalg.eigvalsh(0.5 * (cov + cov.T)).min()) >= -1e-8
    gamma = cumulative_covariance(model)
    assert float(np.linalg.eigvalsh(0.5 * (gamma + gamma.T)).min()) >= -1e-8


# Feature: power-energy-quant-analysis, Property 72: Induced Correlation Bounds and PSD
# The §33.3 option-variance-matching condition and §33.4 correlation-matching hold exactly
# for a model built from a target correlation and per-tenor vols.
@given(corr=correlation_matrices(min_dim=2, max_dim=4), n_steps=st.integers(1, 4), data=st.data())
@settings(max_examples=100)
def test_property_72_option_variance_and_correlation_matching(
    corr: npt.NDArray[np.float64], n_steps: int, data: st.DataObject
) -> None:
    n = int(corr.shape[0])
    vols = np.array(
        data.draw(st.lists(st.floats(min_value=0.1, max_value=0.6), min_size=n, max_size=n)),
        dtype=np.float64,
    )
    dt = 1.0 / 12.0
    model = MultifactorForwardModel.from_target_correlation(corr, vols, n_steps=n_steps, dt=dt)
    expiries = np.full(n, n_steps * dt)
    assert matches_option_variance(model, vols, expiries)
    assert induced_correlation(model, 0) == pytest.approx(corr, abs=1e-9)


# ---------------------------------------------------------------------------------------
# Properties 73-74: outage reliability KPIs.
# ---------------------------------------------------------------------------------------

_OUTAGE_START = datetime(2026, 1, 1, 0, 0)
_OUTAGE_TYPES = tuple(OutageType)


@st.composite
def _outage_record(draw: st.DrawFn) -> OutageRecord:
    installed = draw(st.floats(min_value=50.0, max_value=500.0))
    unavailable = draw(st.floats(min_value=0.0, max_value=installed))
    hours = draw(st.floats(min_value=0.1, max_value=50.0))
    return OutageRecord(
        asset_id="A1",
        unit_id="U1",
        technology="CCGT",
        market_zone="DE",
        outage_id="O1",
        outage_type=draw(st.sampled_from(_OUTAGE_TYPES)),
        status=OutageStatus.COMPLETED,
        announcement_time=_OUTAGE_START - timedelta(days=1),
        start_time=_OUTAGE_START,
        expected_end_time=_OUTAGE_START + timedelta(hours=hours),
        installed_capacity_mw=installed,
        unavailable_capacity_mw=unavailable,
        available_capacity_mw=installed - unavailable,
        source="TSO",
        revision_number=0,
    )


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


# Feature: power-energy-quant-analysis, Property 73: Outage KPI Formulas and Ranges
@given(
    records=st.lists(_outage_record(), min_size=0, max_size=6),
    period_hours=st.floats(min_value=1.0, max_value=200.0),
    installed=st.floats(min_value=50.0, max_value=500.0),
)
@settings(max_examples=100)
def test_property_73_kpis_match_definitions_and_lie_in_unit_interval(
    records: list[OutageRecord], period_hours: float, installed: float
) -> None:
    dataset = OutageDataset(tuple(records))
    af = availability_factor(dataset, period_hours)
    eaf = equivalent_availability_factor(dataset, period_hours, installed)
    forced_out = forced_outage_rate(dataset)

    # Independent recomputation of each §22 definition.
    full_hours = sum(
        r.duration_hours
        for r in records
        if r.unavailable_capacity_mw >= r.installed_capacity_mw - 1e-6
    )
    energy = sum(r.unavailable_capacity_mw * r.duration_hours for r in records)
    forced_hours = sum(r.duration_hours for r in records if r.outage_type is OutageType.FORCED)
    service_hours = sum(r.duration_hours for r in records if r.outage_type is OutageType.SERVICE)
    denom = forced_hours + service_hours

    assert af == pytest.approx(_clamp01(1.0 - full_hours / period_hours), rel=1e-9, abs=1e-12)
    assert eaf == pytest.approx(
        _clamp01(1.0 - energy / (installed * period_hours)), rel=1e-9, abs=1e-12
    )
    expected_for = forced_hours / denom if denom > 0.0 else 0.0
    assert forced_out == pytest.approx(expected_for, rel=1e-9, abs=1e-12)
    for value in (af, eaf, forced_out):
        assert 0.0 <= value <= 1.0


# Feature: power-energy-quant-analysis, Property 74: Outage Record Invariant and Category
# Separation
@given(record=_outage_record())
@settings(max_examples=100)
def test_property_74_record_invariant_holds(record: OutageRecord) -> None:
    assert 0.0 <= record.unavailable_capacity_mw <= record.installed_capacity_mw
    assert record.available_capacity_mw == pytest.approx(
        record.installed_capacity_mw - record.unavailable_capacity_mw, abs=1e-6
    )
    assert record.is_forced is (record.outage_type is OutageType.FORCED)


def _record(**overrides: object) -> OutageRecord:
    params: dict[str, object] = dict(
        asset_id="A1",
        unit_id="U1",
        technology="CCGT",
        market_zone="DE",
        outage_id="O1",
        outage_type=OutageType.FORCED,
        status=OutageStatus.COMPLETED,
        announcement_time=_OUTAGE_START - timedelta(days=1),
        start_time=_OUTAGE_START,
        expected_end_time=_OUTAGE_START + timedelta(hours=10.0),
        installed_capacity_mw=100.0,
        unavailable_capacity_mw=100.0,
        available_capacity_mw=0.0,
        source="TSO",
        revision_number=0,
    )
    params.update(overrides)
    return OutageRecord(**params)  # type: ignore[arg-type]


# Feature: power-energy-quant-analysis, Property 74: Outage Record Invariant and Category
# Separation
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"available_capacity_mw": 55.0}, "available_capacity_mw"),  # breaks the balance
        (
            {"unavailable_capacity_mw": 150.0, "available_capacity_mw": -50.0},
            "unavailable",
        ),  # unavailable > installed
        ({"installed_capacity_mw": 0.0}, "installed_capacity_mw"),  # installed must be > 0
    ],
)
def test_property_74_invalid_records_raise(overrides: Mapping[str, float], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _record(**overrides)


# Feature: power-energy-quant-analysis, Property 74: Outage Record Invariant and Category
# Separation
# A non-positive period drives the range-based KPIs to raise; and the categories stay
# distinct — a planned/unplanned/maintenance outage never enters the forced-outage KPIs.
def test_property_74_period_validation_and_category_separation() -> None:
    dataset = OutageDataset((_record(outage_type=OutageType.FORCED),))
    for bad_period in (0.0, -1.0):
        with pytest.raises(ValidationError, match="period_hours"):
            availability_factor(dataset, bad_period)
        with pytest.raises(ValidationError, match="period_hours"):
            equivalent_availability_factor(dataset, bad_period, 100.0)
        with pytest.raises(ValidationError, match="period_hours"):
            mtbf(dataset, bad_period)
        with pytest.raises(ValidationError, match="period_hours"):
            outage_frequency(dataset, bad_period)

    # Category separation: only FORCED (and SERVICE, for the denominator) enter the FOR /
    # multiplier; planned/unplanned/maintenance never do.
    assert {t.value for t in OutageType} == {
        "planned",
        "forced",
        "unplanned",
        "maintenance",
        "service",
    }
    non_forced = OutageDataset(
        (
            _record(outage_type=OutageType.PLANNED),
            _record(outage_type=OutageType.UNPLANNED),
            _record(outage_type=OutageType.MAINTENANCE),
        )
    )
    assert forced_outage_rate(non_forced) == 0.0  # no forced or service exposure
    assert non_forced.forced_outage_multiplier(100.0, 100.0) == 1.0  # no forced derating
