"""Unit tests for composable PPA contract-term objects (`models/ppa_terms.py`).

Covers every validation branch and the pure helper methods (`step_price_at`,
`effective_price`, `triggers`, `out_of_band_mwh`) per
`.kiro/specs/ppa-contract-terms/tasks.md` Task 4.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quantvolt import (
    ChangeInLawAllocation,
    CurtailmentTreatment,
    IndexationStep,
    NegativePriceClause,
    NegativePriceTreatment,
    PpaAvailabilityGuarantee,
    PpaContractMetadata,
    PpaCreditSupportType,
    PpaPriceTerms,
    PpaReconciliationPeriod,
    PpaReconciliationTerms,
    PpaTerms,
    PpaToleranceBand,
    PpaVolumeTerms,
)
from quantvolt.exceptions import ValidationError

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = _T0 + timedelta(hours=1)
_T2 = _T0 + timedelta(hours=2)


# --- IndexationStep ---------------------------------------------------------


def test_indexation_step_requires_tz_aware_utc_and_finite_price() -> None:
    with pytest.raises(ValidationError, match="effective_from_utc"):
        IndexationStep(effective_from_utc=datetime(2026, 1, 1), fixed_price_per_mwh=50.0)
    with pytest.raises(ValidationError, match="fixed_price_per_mwh"):
        IndexationStep(effective_from_utc=_T0, fixed_price_per_mwh=float("nan"))


# --- PpaPriceTerms ----------------------------------------------------------


def test_price_terms_rejects_floor_not_strictly_less_than_cap() -> None:
    with pytest.raises(ValidationError, match="floor_price_per_mwh"):
        PpaPriceTerms(floor_price_per_mwh=50.0, cap_price_per_mwh=50.0)
    with pytest.raises(ValidationError, match="floor_price_per_mwh"):
        PpaPriceTerms(floor_price_per_mwh=60.0, cap_price_per_mwh=50.0)


def test_price_terms_allows_negative_bounds() -> None:
    terms = PpaPriceTerms(floor_price_per_mwh=-50.0, cap_price_per_mwh=-10.0)
    assert terms.floor_price_per_mwh == -50.0
    assert terms.cap_price_per_mwh == -10.0


def test_price_terms_rejects_non_finite_bounds() -> None:
    with pytest.raises(ValidationError, match="floor_price_per_mwh"):
        PpaPriceTerms(floor_price_per_mwh=float("nan"))
    with pytest.raises(ValidationError, match="cap_price_per_mwh"):
        PpaPriceTerms(cap_price_per_mwh=float("inf"))


def test_price_terms_rejects_non_increasing_indexation() -> None:
    with pytest.raises(ValidationError, match=r"indexation\[1\]"):
        PpaPriceTerms(
            indexation=(
                IndexationStep(effective_from_utc=_T1, fixed_price_per_mwh=60.0),
                IndexationStep(effective_from_utc=_T1, fixed_price_per_mwh=70.0),
            )
        )
    with pytest.raises(ValidationError, match=r"indexation\[1\]"):
        PpaPriceTerms(
            indexation=(
                IndexationStep(effective_from_utc=_T1, fixed_price_per_mwh=60.0),
                IndexationStep(effective_from_utc=_T0, fixed_price_per_mwh=70.0),
            )
        )


def test_step_price_at_selects_latest_step_at_or_before() -> None:
    terms = PpaPriceTerms(
        indexation=(
            IndexationStep(effective_from_utc=_T1, fixed_price_per_mwh=60.0),
            IndexationStep(effective_from_utc=_T2, fixed_price_per_mwh=80.0),
        )
    )
    assert terms.step_price_at(_T0, base=50.0) == 50.0
    assert terms.step_price_at(_T1, base=50.0) == 60.0
    assert terms.step_price_at(_T1 + timedelta(minutes=30), base=50.0) == 60.0
    assert terms.step_price_at(_T2, base=50.0) == 80.0


def test_effective_price_clamps_floor_then_cap() -> None:
    terms = PpaPriceTerms(floor_price_per_mwh=40.0, cap_price_per_mwh=100.0)
    assert terms.effective_price(_T0, base=10.0) == 40.0
    assert terms.effective_price(_T0, base=200.0) == 100.0
    assert terms.effective_price(_T0, base=70.0) == 70.0


def test_effective_price_applies_only_the_present_bound() -> None:
    floor_only = PpaPriceTerms(floor_price_per_mwh=40.0)
    assert floor_only.effective_price(_T0, base=10.0) == 40.0
    assert floor_only.effective_price(_T0, base=1_000.0) == 1_000.0
    cap_only = PpaPriceTerms(cap_price_per_mwh=100.0)
    assert cap_only.effective_price(_T0, base=-1_000.0) == -1_000.0
    assert cap_only.effective_price(_T0, base=1_000.0) == 100.0


# --- NegativePriceClause ----------------------------------------------------


def test_negative_price_clause_rejects_invalid_treatment_and_non_finite_threshold() -> None:
    with pytest.raises(ValidationError, match="treatment"):
        NegativePriceClause(treatment="no_compensation")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="threshold_per_mwh"):
        NegativePriceClause(
            treatment=NegativePriceTreatment.NO_COMPENSATION, threshold_per_mwh=float("nan")
        )


def test_negative_price_clause_triggers_strictly_below_threshold() -> None:
    clause = NegativePriceClause(
        treatment=NegativePriceTreatment.PRICE_AT_ZERO, threshold_per_mwh=0.0
    )
    assert clause.triggers(-0.01) is True
    assert clause.triggers(0.0) is False
    assert clause.triggers(0.01) is False


def test_negative_price_clause_min_consecutive_intervals_defaults_to_none() -> None:
    clause = NegativePriceClause(treatment=NegativePriceTreatment.NO_COMPENSATION)
    assert clause.min_consecutive_intervals is None


def test_negative_price_clause_rejects_min_consecutive_intervals_below_two() -> None:
    with pytest.raises(ValidationError, match="min_consecutive_intervals"):
        NegativePriceClause(
            treatment=NegativePriceTreatment.NO_COMPENSATION, min_consecutive_intervals=1
        )
    with pytest.raises(ValidationError, match="min_consecutive_intervals"):
        NegativePriceClause(
            treatment=NegativePriceTreatment.NO_COMPENSATION, min_consecutive_intervals=0
        )
    with pytest.raises(ValidationError, match="min_consecutive_intervals"):
        NegativePriceClause(
            treatment=NegativePriceTreatment.NO_COMPENSATION,
            min_consecutive_intervals=True,  # bool rejected, per require_integer_at_least
        )


def test_negative_price_clause_accepts_min_consecutive_intervals_at_least_two() -> None:
    clause = NegativePriceClause(
        treatment=NegativePriceTreatment.NO_COMPENSATION, min_consecutive_intervals=4
    )
    assert clause.min_consecutive_intervals == 4
    # triggers() itself is interval-local and unaffected by the consecutive-hour field:
    assert clause.triggers(-1.0) is True


# --- PpaToleranceBand -------------------------------------------------------


def test_tolerance_band_validates_fraction_bounds_and_penalty() -> None:
    with pytest.raises(ValidationError, match="min_fraction"):
        PpaToleranceBand(min_fraction=-0.1, max_fraction=1.1, penalty_per_mwh=1.0)
    with pytest.raises(ValidationError, match="min_fraction"):
        PpaToleranceBand(min_fraction=1.1, max_fraction=1.2, penalty_per_mwh=1.0)
    with pytest.raises(ValidationError, match="max_fraction"):
        PpaToleranceBand(min_fraction=0.9, max_fraction=0.95, penalty_per_mwh=1.0)
    with pytest.raises(ValidationError, match="penalty_per_mwh"):
        PpaToleranceBand(min_fraction=0.9, max_fraction=1.1, penalty_per_mwh=-1.0)


def test_out_of_band_mwh_is_zero_inside_band_and_positive_outside() -> None:
    band = PpaToleranceBand(min_fraction=0.9, max_fraction=1.1, penalty_per_mwh=5.0)
    assert band.out_of_band_mwh(metered=95.0, contracted=100.0) == 0.0
    assert band.out_of_band_mwh(metered=90.0, contracted=100.0) == 0.0
    assert band.out_of_band_mwh(metered=110.0, contracted=100.0) == 0.0
    assert band.out_of_band_mwh(metered=80.0, contracted=100.0) == pytest.approx(10.0)
    assert band.out_of_band_mwh(metered=120.0, contracted=100.0) == pytest.approx(10.0)


def test_out_of_band_mwh_handles_negative_contracted_and_metered() -> None:
    # negative bounds/values are valid inputs throughout this framework
    band = PpaToleranceBand(min_fraction=0.0, max_fraction=1.0, penalty_per_mwh=1.0)
    assert band.out_of_band_mwh(metered=-5.0, contracted=0.0) == pytest.approx(5.0)


# --- PpaVolumeTerms ---------------------------------------------------------


def test_volume_terms_rejects_invalid_curtailment_and_tolerance_type() -> None:
    with pytest.raises(ValidationError, match="curtailment"):
        PpaVolumeTerms(curtailment="producer_bears")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="tolerance"):
        PpaVolumeTerms(
            curtailment=CurtailmentTreatment.PRODUCER_BEARS,
            tolerance="not-a-band",  # type: ignore[arg-type]
        )


def test_needs_curtailment_input_true_only_for_deemed_generation() -> None:
    producer_bears = PpaVolumeTerms(curtailment=CurtailmentTreatment.PRODUCER_BEARS)
    deemed_generation = PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)
    assert not producer_bears.needs_curtailment_input
    assert deemed_generation.needs_curtailment_input


# --- PpaAvailabilityGuarantee (Phase 6 / Requirement 10) --------------------


def test_availability_guarantee_requires_a_probability_fraction() -> None:
    with pytest.raises(ValidationError, match="deemed_availability_fraction"):
        PpaAvailabilityGuarantee(deemed_availability_fraction=1.1)
    with pytest.raises(ValidationError, match="deemed_availability_fraction"):
        PpaAvailabilityGuarantee(deemed_availability_fraction=-0.1)


def test_availability_guarantee_shortfall_fraction_is_one_directional() -> None:
    guarantee = PpaAvailabilityGuarantee(deemed_availability_fraction=0.95)
    assert guarantee.shortfall_fraction(0.90) == pytest.approx(0.05)
    assert guarantee.shortfall_fraction(0.95) == 0.0
    # measured beating deemed never produces a negative ("credit") shortfall:
    assert guarantee.shortfall_fraction(1.0) == 0.0


# --- PpaReconciliationTerms (Phase 6 / Requirements 9-11) -------------------


def test_reconciliation_terms_requires_period_and_finite_true_up_price() -> None:
    with pytest.raises(ValidationError, match="period"):
        PpaReconciliationTerms(
            period="monthly",  # type: ignore[arg-type]
            true_up_price_per_mwh=50.0,
        )
    with pytest.raises(ValidationError, match="true_up_price_per_mwh"):
        PpaReconciliationTerms(
            period=PpaReconciliationPeriod.ANNUAL, true_up_price_per_mwh=float("nan")
        )


def test_reconciliation_terms_rejects_wrong_type_volume_band_and_availability() -> None:
    with pytest.raises(ValidationError, match="volume_band"):
        PpaReconciliationTerms(
            period=PpaReconciliationPeriod.QUARTERLY,
            true_up_price_per_mwh=50.0,
            volume_band="not-a-band",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError, match="availability"):
        PpaReconciliationTerms(
            period=PpaReconciliationPeriod.QUARTERLY,
            true_up_price_per_mwh=50.0,
            availability="not-a-guarantee",  # type: ignore[arg-type]
        )


def test_reconciliation_terms_defaults_volume_band_and_availability_to_none() -> None:
    terms = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.MONTHLY, true_up_price_per_mwh=50.0
    )
    assert terms.volume_band is None
    assert terms.availability is None


def test_reconciliation_terms_accepts_volume_band_and_availability() -> None:
    terms = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.MONTHLY,
        true_up_price_per_mwh=50.0,
        volume_band=PpaToleranceBand(min_fraction=0.9, max_fraction=1.1, penalty_per_mwh=3.0),
        availability=PpaAvailabilityGuarantee(deemed_availability_fraction=0.97),
    )
    assert isinstance(terms.volume_band, PpaToleranceBand)
    assert isinstance(terms.availability, PpaAvailabilityGuarantee)


# --- PpaContractMetadata (Phase 7 / Requirement 12) — zero settlement semantics ---


def test_contract_metadata_defaults() -> None:
    metadata = PpaContractMetadata()
    assert metadata.goo_transfer is False
    assert metadata.goo_price_per_mwh is None
    assert metadata.credit_support_type is PpaCreditSupportType.NONE
    assert metadata.credit_support_amount is None
    assert metadata.credit_support_threshold is None
    assert metadata.change_in_law_allocation is None


def test_contract_metadata_rejects_invalid_fields() -> None:
    with pytest.raises(ValidationError, match="goo_transfer"):
        PpaContractMetadata(goo_transfer="yes")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="goo_price_per_mwh"):
        PpaContractMetadata(goo_transfer=True, goo_price_per_mwh=float("nan"))
    with pytest.raises(ValidationError, match="credit_support_type"):
        PpaContractMetadata(credit_support_type="letter_of_credit")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="credit_support_amount"):
        PpaContractMetadata(credit_support_amount=-1.0)
    with pytest.raises(ValidationError, match="credit_support_threshold"):
        PpaContractMetadata(credit_support_threshold=-1.0)
    with pytest.raises(ValidationError, match="change_in_law_allocation"):
        PpaContractMetadata(change_in_law_allocation="producer")  # type: ignore[arg-type]


def test_contract_metadata_accepts_fully_populated_instance() -> None:
    metadata = PpaContractMetadata(
        goo_transfer=True,
        goo_price_per_mwh=1.5,
        credit_support_type=PpaCreditSupportType.LETTER_OF_CREDIT,
        credit_support_amount=2_000_000.0,
        credit_support_threshold=500_000.0,
        change_in_law_allocation=ChangeInLawAllocation.SHARED,
    )
    assert metadata.goo_transfer is True
    assert metadata.credit_support_type is PpaCreditSupportType.LETTER_OF_CREDIT
    assert metadata.change_in_law_allocation is ChangeInLawAllocation.SHARED


# --- PpaTerms aggregate -----------------------------------------------------


def test_ppa_terms_defaults_to_all_none() -> None:
    terms = PpaTerms()
    assert terms.price is None
    assert terms.negative_price is None
    assert terms.volume is None
    assert terms.reconciliation is None
    assert terms.metadata is None


@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("price", "price"),
        ("negative_price", "negative_price"),
        ("volume", "volume"),
        ("reconciliation", "reconciliation"),
        ("metadata", "metadata"),
    ],
)
def test_ppa_terms_rejects_wrong_type_field(field: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        PpaTerms(**{field: object()})  # type: ignore[arg-type]


def test_ppa_terms_accepts_the_declared_type_for_each_field() -> None:
    terms = PpaTerms(
        price=PpaPriceTerms(),
        negative_price=NegativePriceClause(treatment=NegativePriceTreatment.PRICE_AT_ZERO),
        volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.PRODUCER_BEARS),
        reconciliation=PpaReconciliationTerms(
            period=PpaReconciliationPeriod.MONTHLY, true_up_price_per_mwh=50.0
        ),
        metadata=PpaContractMetadata(),
    )
    assert isinstance(terms.price, PpaPriceTerms)
    assert isinstance(terms.reconciliation, PpaReconciliationTerms)
    assert isinstance(terms.metadata, PpaContractMetadata)
