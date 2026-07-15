"""Unit tests for numerics/risk_adjustment.py (Task 63): price of risk / risk adjustment.

Validates Requirements 19.1 to 19.4 and Correctness Properties 58 (price-of-risk
identities) and 59 (physical-drift guard).
"""

from __future__ import annotations

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.numerics.risk_adjustment import (
    DriftKind,
    PriceOfRiskKind,
    price_of_risk,
    require_physical_drift,
    risk_adjusted_drift,
    tradable_price_of_risk,
)


class TestPriceOfRisk:
    def test_hand_computed(self) -> None:
        # lambda = (mu - r)/sigma = (0.12 - 0.04)/0.20 = 0.4  (eq 10.4)
        assert price_of_risk(mu=0.12, r=0.04, sigma=0.20) == pytest.approx(0.4)

    def test_zero_excess_return_is_zero(self) -> None:
        assert price_of_risk(mu=0.05, r=0.05, sigma=0.30) == 0.0

    def test_negative_excess_return(self) -> None:
        # mu below r gives a negative price of risk.
        assert price_of_risk(mu=0.02, r=0.05, sigma=0.10) == pytest.approx(-0.3)

    def test_sigma_non_positive_raises_naming_sigma(self) -> None:
        with pytest.raises(ValidationError, match="sigma"):
            price_of_risk(mu=0.1, r=0.04, sigma=0.0)
        with pytest.raises(ValidationError, match="sigma"):
            price_of_risk(mu=0.1, r=0.04, sigma=-0.2)


class TestTradablePriceOfRisk:
    def test_hand_computed(self) -> None:
        # lambda_S = (mu + y - r)/sigma = (0.10 + 0.03 - 0.04)/0.30 = 0.09/0.30 = 0.3  (eq 10.6)
        assert tradable_price_of_risk(mu=0.10, y=0.03, r=0.04, sigma=0.30) == pytest.approx(0.3)

    def test_zero_convenience_yield_matches_plain_price_of_risk(self) -> None:
        # With y = 0, eq 10.6 reduces to eq 10.4.
        assert tradable_price_of_risk(mu=0.12, y=0.0, r=0.04, sigma=0.20) == pytest.approx(
            price_of_risk(mu=0.12, r=0.04, sigma=0.20)
        )

    def test_sigma_non_positive_raises_naming_sigma(self) -> None:
        with pytest.raises(ValidationError, match="sigma"):
            tradable_price_of_risk(mu=0.1, y=0.02, r=0.04, sigma=0.0)
        with pytest.raises(ValidationError, match="sigma"):
            tradable_price_of_risk(mu=0.1, y=0.02, r=0.04, sigma=-1.0)


class TestRiskAdjustedDrift:
    def test_hand_computed(self) -> None:
        # mu - lambda_S*sigma = 0.12 - 0.4*0.20 = 0.12 - 0.08 = 0.04  (eq 10.5)
        assert risk_adjusted_drift(mu=0.12, lambda_s=0.4, sigma=0.20) == pytest.approx(0.04)

    def test_zero_lambda_leaves_drift_unchanged(self) -> None:
        assert risk_adjusted_drift(mu=0.09, lambda_s=0.0, sigma=0.25) == pytest.approx(0.09)

    def test_sigma_non_positive_raises_naming_sigma(self) -> None:
        with pytest.raises(ValidationError, match="sigma"):
            risk_adjusted_drift(mu=0.1, lambda_s=0.3, sigma=0.0)
        with pytest.raises(ValidationError, match="sigma"):
            risk_adjusted_drift(mu=0.1, lambda_s=0.3, sigma=-0.5)


class TestProperty58TradableIdentity:
    """Property 58: for a tradable underlying the risk-adjusted drift collapses to r - y."""

    def test_identity_holds_exactly(self) -> None:
        mu, y, r, sigma = 0.10, 0.03, 0.04, 0.30
        lambda_s = tradable_price_of_risk(mu=mu, y=y, r=r, sigma=sigma)
        assert risk_adjusted_drift(mu=mu, lambda_s=lambda_s, sigma=sigma) == pytest.approx(r - y)

    @pytest.mark.parametrize(
        ("mu", "y", "r", "sigma"),
        [
            (0.12, 0.00, 0.05, 0.20),
            (0.08, 0.06, 0.03, 0.45),
            (-0.02, 0.01, 0.04, 0.15),  # negative drift (real negative power prices)
            (0.20, -0.05, 0.04, 0.60),  # negative net convenience yield (storage-cost heavy)
        ],
    )
    def test_identity_across_parameters(self, mu: float, y: float, r: float, sigma: float) -> None:
        lambda_s = tradable_price_of_risk(mu=mu, y=y, r=r, sigma=sigma)
        assert risk_adjusted_drift(mu=mu, lambda_s=lambda_s, sigma=sigma) == pytest.approx(r - y)


class TestRequirePhysicalDrift:
    """Property 59: a risk-neutral-tagged drift is rejected for VaR/CFaR."""

    def test_physical_drift_accepted(self) -> None:
        # Returns None and does not raise.
        assert require_physical_drift(DriftKind.PHYSICAL) is None

    def test_risk_neutral_drift_rejected(self) -> None:
        with pytest.raises(ValidationError):
            require_physical_drift(DriftKind.RISK_NEUTRAL)

    def test_rejection_names_the_field(self) -> None:
        with pytest.raises(ValidationError, match="physical_drift"):
            require_physical_drift(DriftKind.RISK_NEUTRAL, field_name="physical_drift")

    def test_rejection_explains_measure_reason(self) -> None:
        with pytest.raises(ValidationError, match="P, not the risk-neutral measure Q"):
            require_physical_drift(DriftKind.RISK_NEUTRAL)


class TestStrEnumValues:
    def test_price_of_risk_kind_values(self) -> None:
        assert PriceOfRiskKind.MARKET == "market"
        assert PriceOfRiskKind.CORPORATE == "corporate"
        assert {k.value for k in PriceOfRiskKind} == {"market", "corporate"}

    def test_drift_kind_values(self) -> None:
        assert DriftKind.PHYSICAL == "physical"
        assert DriftKind.RISK_NEUTRAL == "risk_neutral"
        assert {k.value for k in DriftKind} == {"physical", "risk_neutral"}
