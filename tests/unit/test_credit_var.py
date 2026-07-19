"""Unit tests for credit_var (Task 68, Req 17.1-17.4, Property 53).

Covers the exact degenerate loss distribution under default probabilities {0, 1}, the
large-sample convergence of expected loss to the closed-form sum for independent
counterparties, netting-derived exposure with the EAD floor at zero, the transition
row-sum / probability domain / recovery domain validation paths (each naming the offending
counterparty or parameter), counterparty-less positions landing in ``credit_risk_free``
without changing losses, seed determinism, the ``var_99 >= var_95 >= 0`` ordering, the
effect of the copula correlation on the tail, and input immutability.
"""

from __future__ import annotations

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.instruments import ForwardContract, FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.risk.credit_var import CounterpartyCreditDetail, CreditVaRResult, credit_var
from quantvolt.testing import assert_input_unchanged

_TTF = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
_JAN = DeliveryPeriod(2026, 1)


def _forward_position(counterparty: str, npv: float) -> PricedPosition:
    forward = ForwardContract(
        _TTF, _JAN, contract_price=30.0, notional=100.0, counterparty=counterparty
    )
    return PricedPosition(position=Position(forward), npv=npv)


def _riskfree_forward(npv: float) -> PricedPosition:
    forward = ForwardContract(_TTF, _JAN, contract_price=30.0, notional=100.0, counterparty=None)
    return PricedPosition(position=Position(forward), npv=npv)


def _riskfree_futures(npv: float) -> PricedPosition:
    futures = FuturesContract(_TTF, _JAN, contract_price=30.0, notional=100.0)
    return PricedPosition(position=Position(futures), npv=npv)


# --- exact degenerate loss distribution (Req 17.1, Property 53) ---------------


def test_degenerate_default_probs_give_exact_loss() -> None:
    """A never-defaults ([1,0]) and B always-defaults ([0,1]) -> loss is deterministic."""
    positions = [_forward_position("A", npv=0.0), _forward_position("B", npv=0.0)]
    transition = {"A": [1.0, 0.0], "B": [0.0, 1.0]}
    exposures = {"A": 500.0, "B": 1000.0}

    result = credit_var(positions, transition, exposures, recovery=0.4, seed=0, path_count=2000)

    # Only B defaults, on every path: loss = LGD_B * EAD_B = 0.6 * 1000 = 600.
    assert result.credit_var_95 == pytest.approx(600.0)
    assert result.credit_var_99 == pytest.approx(600.0)
    assert result.expected_credit_loss == pytest.approx(600.0)

    detail = {d.counterparty: d for d in result.per_counterparty}
    assert isinstance(detail["A"], CounterpartyCreditDetail)
    assert detail["A"].default_probability == 0.0
    assert detail["A"].exposure == 500.0
    assert detail["A"].lgd == pytest.approx(0.6)
    assert detail["A"].expected_loss == 0.0
    assert detail["B"].default_probability == 1.0
    assert detail["B"].exposure == 1000.0
    assert detail["B"].expected_loss == pytest.approx(600.0)


# --- expected loss converges to the closed form (Req 17.1) --------------------


def test_expected_loss_converges_for_independent_counterparties() -> None:
    """rho=0 -> independent defaults; MC mean loss -> sum of p * LGD * EAD."""
    names = ["A", "B", "C"]
    positions = [_forward_position(name, npv=0.0) for name in names]
    transition = {name: [0.9, 0.1] for name in names}  # p_default = 0.1 each
    exposures = {name: 1000.0 for name in names}

    result = credit_var(
        positions,
        transition,
        exposures,
        recovery=0.5,  # LGD = 0.5
        seed=12345,
        path_count=100_000,
        asset_correlation=0.0,
    )

    # analytic per-counterparty expected loss = 0.1 * 0.5 * 1000 = 50; total = 150.
    for detail in result.per_counterparty:
        assert detail.expected_loss == pytest.approx(50.0)
    assert result.expected_credit_loss == pytest.approx(150.0, rel=0.05)


# --- netting-derived exposure and the EAD floor (Req 17.1) --------------------


def test_exposure_derived_from_netted_npv_when_not_supplied() -> None:
    """No exposures mapping -> EAD is the netted (summed) NPV of the counterparty."""
    positions = [_forward_position("B", npv=700.0), _forward_position("B", npv=300.0)]
    transition = {"B": [0.0, 1.0]}  # always defaults

    result = credit_var(positions, transition, recovery=0.4, seed=0, path_count=1000)

    # netted EAD = 700 + 300 = 1000; loss = 0.6 * 1000 = 600.
    assert result.per_counterparty[0].exposure == pytest.approx(1000.0)
    assert result.credit_var_99 == pytest.approx(600.0)


def test_net_negative_exposure_floors_ead_at_zero() -> None:
    """A net out-of-the-money counterparty carries no credit loss even on default."""
    positions = [_forward_position("B", npv=300.0), _forward_position("B", npv=-1000.0)]
    transition = {"B": [0.0, 1.0]}  # always defaults

    result = credit_var(positions, transition, recovery=0.0, seed=0, path_count=1000)

    assert result.per_counterparty[0].exposure == 0.0
    assert result.credit_var_99 == 0.0
    assert result.expected_credit_loss == 0.0


# --- validation: transition rows (Req 17.4, Property 53) ----------------------


def test_transition_row_sum_violation_names_counterparty() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.5, 0.4]}  # sums to 0.9

    with pytest.raises(ValidationError) as excinfo:
        credit_var(positions, transition, {"B": 1000.0}, recovery=0.4, seed=0)

    message = str(excinfo.value)
    assert "'B'" in message  # names the counterparty
    assert "sum" in message  # names the violated constraint


def test_transition_probability_out_of_range_names_counterparty() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [1.2, -0.2]}  # sums to 1.0 but entries out of [0, 1]

    with pytest.raises(ValidationError) as excinfo:
        credit_var(positions, transition, {"B": 1000.0}, recovery=0.4, seed=0)

    message = str(excinfo.value)
    assert "'B'" in message
    assert "[0, 1]" in message


def test_missing_transition_for_credit_bearing_counterparty_raises() -> None:
    positions = [_forward_position("C", npv=100.0)]

    with pytest.raises(ValidationError, match="'C'"):
        credit_var(positions, {}, {"C": 1000.0}, recovery=0.4, seed=0)


# --- validation: recovery and other domains (Req 17.4) ------------------------


def test_scalar_recovery_out_of_range_names_param() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}

    with pytest.raises(ValidationError, match="recovery must be in"):
        credit_var(positions, transition, {"B": 1000.0}, recovery=1.5, seed=0)


def test_per_counterparty_recovery_out_of_range_names_counterparty() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}

    with pytest.raises(ValidationError, match="recovery\\['B'\\]"):
        credit_var(positions, transition, {"B": 1000.0}, recovery={"B": 1.5}, seed=0)


def test_negative_seed_raises() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}

    with pytest.raises(ValidationError, match="seed"):
        credit_var(positions, transition, {"B": 1000.0}, recovery=0.4, seed=-1)


def test_asset_correlation_out_of_range_raises() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}

    with pytest.raises(ValidationError, match="asset_correlation"):
        credit_var(positions, transition, {"B": 1000.0}, seed=0, asset_correlation=1.5)


# --- counterparty-less positions -> credit_risk_free (Req 17.2, Property 53) --


def test_counterparty_less_positions_are_credit_risk_free_and_do_not_change_losses() -> None:
    credit = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.0, 1.0]}
    exposures = {"B": 1000.0}

    base = credit_var(credit, transition, exposures, recovery=0.4, seed=0, path_count=1000)

    # Add a counterparty-less forward and a futures (no counterparty attribute at all).
    riskfree = [_riskfree_forward(npv=5000.0), _riskfree_futures(npv=-3000.0)]
    with_riskfree = credit_var(
        credit + riskfree, transition, exposures, recovery=0.4, seed=0, path_count=1000
    )

    # The risk-free positions are reported, not dropped, and do not change any loss metric.
    assert list(with_riskfree.credit_risk_free) == riskfree
    assert base.credit_risk_free == ()
    assert with_riskfree.credit_var_95 == base.credit_var_95
    assert with_riskfree.credit_var_99 == base.credit_var_99
    assert with_riskfree.expected_credit_loss == base.expected_credit_loss
    # Only the one credit-bearing counterparty enters the detail.
    assert len(with_riskfree.per_counterparty) == 1


# --- determinism (Req 17.3, Property 53) --------------------------------------


def test_seed_determinism_is_exact() -> None:
    positions = [_forward_position("A", npv=0.0), _forward_position("B", npv=0.0)]
    transition = {"A": [0.9, 0.1], "B": [0.8, 0.2]}
    exposures = {"A": 1000.0, "B": 2000.0}

    first = credit_var(positions, transition, exposures, recovery=0.4, seed=42, path_count=50_000)
    second = credit_var(positions, transition, exposures, recovery=0.4, seed=42, path_count=50_000)
    assert first == second
    assert isinstance(first, CreditVaRResult)


def test_different_seed_changes_the_tail() -> None:
    positions = [_forward_position("A", npv=0.0), _forward_position("B", npv=0.0)]
    transition = {"A": [0.9, 0.1], "B": [0.8, 0.2]}
    exposures = {"A": 1000.0, "B": 2000.0}

    first = credit_var(positions, transition, exposures, seed=1, path_count=50_000)
    second = credit_var(positions, transition, exposures, seed=2, path_count=50_000)
    # Same measure, different pseudo-random draw -> the sampled mean loss moves.
    assert first.expected_credit_loss != second.expected_credit_loss


# --- ordering / non-negativity (Req 17.1, Property 53) ------------------------


def test_var_ordering_and_non_negativity() -> None:
    names = ["A", "B", "C"]
    positions = [_forward_position(name, npv=0.0) for name in names]
    transition = {name: [0.85, 0.15] for name in names}
    exposures = {name: 1000.0 for name in names}

    result = credit_var(positions, transition, exposures, recovery=0.3, seed=7)

    assert result.credit_var_99 >= result.credit_var_95 >= 0.0
    assert result.expected_credit_loss >= 0.0


def test_higher_asset_correlation_fattens_the_loss_tail() -> None:
    names = [f"C{i}" for i in range(5)]
    positions = [_forward_position(name, npv=0.0) for name in names]
    transition = {name: [0.9, 0.1] for name in names}
    exposures = {name: 1000.0 for name in names}

    low = credit_var(positions, transition, exposures, recovery=0.0, seed=3, asset_correlation=0.0)
    high = credit_var(
        positions, transition, exposures, recovery=0.0, seed=3, asset_correlation=0.85
    )

    # Correlated defaults pile mass onto many-simultaneous-default paths -> fatter tail,
    # while expected loss is invariant to the copula correlation.
    assert high.credit_var_99 >= low.credit_var_99
    assert high.expected_credit_loss == pytest.approx(low.expected_credit_loss, rel=0.1)


# --- reproducibility echo -----------------------------------------------------


def test_result_echoes_seed_path_count_and_correlation() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}

    result = credit_var(
        positions, transition, {"B": 1000.0}, seed=99, path_count=1234, asset_correlation=0.3
    )
    assert result.seed == 99
    assert result.path_count == 1234
    assert result.asset_correlation == pytest.approx(0.3)


# --- input immutability (Req 11.4, coding-style section 7) --------------------


def test_inputs_are_not_mutated() -> None:
    positions = [_forward_position("A", npv=100.0), _forward_position("B", npv=200.0)]
    # Plain lists (not ndarrays) so the shipped deep-equality check can compare the dict.
    transition = {"A": [0.9, 0.1], "B": [0.8, 0.2]}
    exposures = {"A": 1000.0, "B": 2000.0}
    recovery = {"A": 0.4, "B": 0.5}

    result = assert_input_unchanged(
        credit_var,
        positions,
        transition,
        exposures,
        recovery,
        7,
        path_count=5000,
    )
    assert isinstance(result, CreditVaRResult)
    assert result.credit_var_99 >= result.credit_var_95 >= 0.0


# --- caller-configurable confidence levels (task: expose hardcoded VaR levels) -


def test_default_confidences_match_previous_hardcoded_behaviour() -> None:
    positions = [_forward_position("A", npv=0.0), _forward_position("B", npv=0.0)]
    transition = {"A": [0.9, 0.1], "B": [0.8, 0.2]}
    exposures = {"A": 1000.0, "B": 2000.0}

    baseline = credit_var(positions, transition, exposures, seed=42, path_count=20_000)
    defaulted = credit_var(
        positions,
        transition,
        exposures,
        seed=42,
        path_count=20_000,
        confidences=(0.95, 0.99),
    )
    assert defaulted == baseline


def test_overriding_confidences_changes_reported_credit_var() -> None:
    positions = [_forward_position("A", npv=0.0), _forward_position("B", npv=0.0)]
    transition = {"A": [0.9, 0.1], "B": [0.8, 0.2]}
    exposures = {"A": 1000.0, "B": 2000.0}

    default_result = credit_var(positions, transition, exposures, seed=7, path_count=20_000)
    overridden = credit_var(
        positions,
        transition,
        exposures,
        seed=7,
        path_count=20_000,
        confidences=(0.50, 0.90),
    )
    assert overridden.credit_var_95 != default_result.credit_var_95
    assert overridden.credit_var_99 != default_result.credit_var_99
    # A lower confidence level must yield a smaller quantile of the same loss sample.
    assert overridden.credit_var_95 <= default_result.credit_var_95


def test_confidences_must_have_exactly_two_levels() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}
    with pytest.raises(ValidationError, match="exactly 2 levels"):
        credit_var(positions, transition, {"B": 1000.0}, seed=0, confidences=(0.95,))


def test_confidences_out_of_range_raises() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}
    with pytest.raises(ValidationError, match="open interval"):
        credit_var(positions, transition, {"B": 1000.0}, seed=0, confidences=(0.0, 0.99))


def test_swapped_confidences_are_rejected() -> None:
    """FIX: (0.99, 0.95) used to silently swap credit_var_95/credit_var_99, violating
    the credit_var_99 >= credit_var_95 invariant relied on elsewhere."""
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}
    with pytest.raises(ValidationError, match="strictly ascending"):
        credit_var(positions, transition, {"B": 1000.0}, seed=0, confidences=(0.99, 0.95))


def test_equal_confidences_are_rejected() -> None:
    positions = [_forward_position("B", npv=0.0)]
    transition = {"B": [0.9, 0.1]}
    with pytest.raises(ValidationError, match="strictly ascending"):
        credit_var(positions, transition, {"B": 1000.0}, seed=0, confidences=(0.95, 0.95))
