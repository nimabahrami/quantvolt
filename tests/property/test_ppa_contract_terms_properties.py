"""PPA contract-terms correctness properties (design Properties 85-90, 95-97;
`.kiro/specs/ppa-contract-terms/` Tasks 10, 12-14).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``), except the deterministic
step-boundary check under Property 86.
"""

from __future__ import annotations

import math
from dataclasses import fields as dc_fields
from datetime import UTC, datetime, timedelta

import polars as pl
from hypothesis import given
from hypothesis import strategies as st

from quantvolt.models.interval import PowerDeliveryInterval
from quantvolt.models.power_hedge import PowerHedgeContract, PowerHedgePosition, PowerHedgeType
from quantvolt.models.ppa import PpaContract, PpaSettlementType, PpaVolumeBasis
from quantvolt.models.ppa_terms import (
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
from quantvolt.pricing.power_hedge import settle_power_hedge_interval
from quantvolt.pricing.ppa import (
    MissingImbalancePricePolicy,
    PpaIntervalSettlement,
    reconcile_ppa_ledger,
    settle_ppa_frame,
    settle_ppa_interval,
)

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = _START + timedelta(days=1)
_INTERVAL = PowerDeliveryInterval(_START, _START + timedelta(hours=1))

_FINITE = st.floats(min_value=-1e5, max_value=1e5, allow_nan=False, allow_infinity=False)
_NON_NEG = st.floats(min_value=0.0, max_value=1e5, allow_nan=False, allow_infinity=False)
_SETTLEMENT_TYPES = st.sampled_from(list(PpaSettlementType))

_INERT_FIELDS = frozenset(
    {"effective_fixed_price_per_mwh", "curtailed_mwh", "deemed_generation_mwh", "tolerance_penalty"}
)
_SHARED_FIELDS = tuple(
    f.name for f in dc_fields(PpaIntervalSettlement) if f.name not in _INERT_FIELDS
)


def _contract(
    settlement_type: PpaSettlementType, terms: PpaTerms | None, *, fixed_price_per_mwh: float = 70.0
) -> PpaContract:
    return PpaContract(
        contract_id="ppa-prop",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=fixed_price_per_mwh,
        start_utc=_START,
        end_utc=_END,
        volume_basis=PpaVolumeBasis.BASELOAD,
        settlement_type=settlement_type,
        terms=terms,
    )


# --- Property 85 — terms-identity regression (Requirement 7) ----------------


@st.composite
def _any_metadata(draw: st.DrawFn) -> PpaContractMetadata:
    """Arbitrary (including fully-populated, non-default) metadata content.

    Property 85's metadata-only branch must hold regardless of *what* the
    metadata carries (Requirement 12.2's zero-settlement-semantics guarantee
    is not limited to the all-default instance).
    """
    return PpaContractMetadata(
        goo_transfer=draw(st.booleans()),
        goo_price_per_mwh=draw(st.one_of(st.none(), _FINITE)),
        credit_support_type=draw(st.sampled_from(list(PpaCreditSupportType))),
        credit_support_amount=draw(st.one_of(st.none(), _NON_NEG)),
        credit_support_threshold=draw(st.one_of(st.none(), _NON_NEG)),
        change_in_law_allocation=draw(
            st.one_of(st.none(), st.sampled_from(list(ChangeInLawAllocation)))
        ),
    )


# Feature: ppa-contract-terms, Property 85: terms-identity regression
@given(
    settlement_type=_SETTLEMENT_TYPES,
    contracted_mwh=_NON_NEG,
    metered_generation_mwh=_NON_NEG,
    spot_price_per_mwh=_FINITE,
    metadata=_any_metadata(),
)
def test_property_85_terms_none_ppaterms_and_metadata_only_are_identical(
    settlement_type: PpaSettlementType,
    contracted_mwh: float,
    metered_generation_mwh: float,
    spot_price_per_mwh: float,
    metadata: PpaContractMetadata,
) -> None:
    kwargs = {
        "contracted_mwh": contracted_mwh,
        "metered_generation_mwh": metered_generation_mwh,
        "spot_price_per_mwh": spot_price_per_mwh,
    }
    baseline = settle_ppa_interval(_contract(settlement_type, None), _INTERVAL, **kwargs)
    empty_terms = settle_ppa_interval(_contract(settlement_type, PpaTerms()), _INTERVAL, **kwargs)
    metadata_only = settle_ppa_interval(
        _contract(settlement_type, PpaTerms(metadata=PpaContractMetadata())), _INTERVAL, **kwargs
    )
    # Requirement 12.2: zero settlement semantics holds for *any* metadata content,
    # not only the all-default instance.
    arbitrary_metadata = settle_ppa_interval(
        _contract(settlement_type, PpaTerms(metadata=metadata)), _INTERVAL, **kwargs
    )
    for candidate in (empty_terms, metadata_only, arbitrary_metadata):
        for field in _SHARED_FIELDS:
            assert getattr(baseline, field) == getattr(candidate, field)
        assert candidate.curtailed_mwh == 0.0
        assert candidate.deemed_generation_mwh == 0.0
        assert candidate.tolerance_penalty == 0.0
        assert candidate.effective_fixed_price_per_mwh == 70.0


def test_property_85_frame_identity_between_no_terms_and_empty_terms() -> None:
    """Property 85 at the frame level: `terms=None` vs `PpaTerms()` (Requirement 7.1)."""
    data = pl.DataFrame(
        {
            "interval_start_utc": [_START, _START + timedelta(hours=1)],
            "interval_end_utc": [_START + timedelta(hours=1), _START + timedelta(hours=2)],
            "contracted_mwh": [10.0, 10.0],
            "metered_generation_mwh": [8.0, 12.0],
            "spot_price_per_mwh": [90.0, -50.0],
            "shortfall_price_per_mwh": [100.0, 100.0],
            "excess_price_per_mwh": [40.0, 40.0],
        }
    )
    no_terms_ledger = settle_ppa_frame(_contract(PpaSettlementType.PHYSICAL, None), data)
    empty_terms_ledger = settle_ppa_frame(_contract(PpaSettlementType.PHYSICAL, PpaTerms()), data)
    shared_columns = [c for c in no_terms_ledger.columns if c not in _INERT_FIELDS]
    assert no_terms_ledger.select(shared_columns).equals(empty_terms_ledger.select(shared_columns))
    for column in _INERT_FIELDS:
        if column == "effective_fixed_price_per_mwh":
            assert (empty_terms_ledger[column] == 70.0).all()
        else:
            assert (empty_terms_ledger[column] == 0.0).all()


# --- Property 86 — clamp bounds and indexation step boundary (Requirement 2) ---


@st.composite
def _floor_cap_pairs(draw: st.DrawFn) -> tuple[float | None, float | None]:
    choice = draw(st.sampled_from(("neither", "floor_only", "cap_only", "both")))
    price = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)
    if choice == "neither":
        return None, None
    if choice == "floor_only":
        return draw(price), None
    if choice == "cap_only":
        return None, draw(price)
    floor = draw(price)
    gap = draw(st.floats(min_value=0.01, max_value=1e3, allow_nan=False, allow_infinity=False))
    return floor, floor + gap


# Feature: ppa-contract-terms, Property 86: clamp bounds
@given(
    bounds=_floor_cap_pairs(),
    base_price=_FINITE,
    spot_price_per_mwh=_FINITE,
    contracted_mwh=_NON_NEG,
    metered_generation_mwh=_NON_NEG,
    settlement_type=_SETTLEMENT_TYPES,
)
def test_property_86_effective_price_respects_floor_and_cap(
    bounds: tuple[float | None, float | None],
    base_price: float,
    spot_price_per_mwh: float,
    contracted_mwh: float,
    metered_generation_mwh: float,
    settlement_type: PpaSettlementType,
) -> None:
    floor, cap = bounds
    contract = _contract(
        settlement_type,
        PpaTerms(price=PpaPriceTerms(floor_price_per_mwh=floor, cap_price_per_mwh=cap)),
        fixed_price_per_mwh=base_price,
    )
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=contracted_mwh,
        metered_generation_mwh=metered_generation_mwh,
        spot_price_per_mwh=spot_price_per_mwh,
    )
    if floor is not None:
        assert result.effective_fixed_price_per_mwh >= floor - 1e-9
    if cap is not None:
        assert result.effective_fixed_price_per_mwh <= cap + 1e-9


# Feature: ppa-contract-terms, Property 86: clamp bounds (step boundary is exact)
def test_property_86_indexation_step_switches_exactly_at_effective_from_utc() -> None:
    step_time = _START + timedelta(hours=5)
    price_terms = PpaPriceTerms(
        indexation=(IndexationStep(effective_from_utc=step_time, fixed_price_per_mwh=99.0),)
    )
    just_before = step_time - timedelta(microseconds=1)
    just_after = step_time + timedelta(microseconds=1)
    assert price_terms.step_price_at(just_before, base=10.0) == 10.0
    assert price_terms.step_price_at(step_time, base=10.0) == 99.0
    assert price_terms.step_price_at(just_after, base=10.0) == 99.0


# --- Property 87 — negative-price clause locality (Requirement 3) -----------


# Feature: ppa-contract-terms, Property 87: negative-price clause locality
@given(
    settlement_type=_SETTLEMENT_TYPES,
    treatment=st.sampled_from(list(NegativePriceTreatment)),
    threshold_per_mwh=st.floats(
        min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False
    ),
    spot_price_per_mwh=st.floats(
        min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False
    ),
    contracted_mwh=_NON_NEG,
    metered_generation_mwh=_NON_NEG,
)
def test_property_87_negative_price_clause_locality(
    settlement_type: PpaSettlementType,
    treatment: NegativePriceTreatment,
    threshold_per_mwh: float,
    spot_price_per_mwh: float,
    contracted_mwh: float,
    metered_generation_mwh: float,
) -> None:
    kwargs = {
        "contracted_mwh": contracted_mwh,
        "metered_generation_mwh": metered_generation_mwh,
        "spot_price_per_mwh": spot_price_per_mwh,
    }
    no_clause = settle_ppa_interval(_contract(settlement_type, None), _INTERVAL, **kwargs)
    with_clause = settle_ppa_interval(
        _contract(
            settlement_type,
            PpaTerms(
                negative_price=NegativePriceClause(
                    treatment=treatment, threshold_per_mwh=threshold_per_mwh
                )
            ),
        ),
        _INTERVAL,
        **kwargs,
    )
    if spot_price_per_mwh >= threshold_per_mwh:
        assert no_clause == with_clause
    else:
        assert with_clause.effective_fixed_price_per_mwh == 0.0
        assert with_clause.spot_cashflow == no_clause.spot_cashflow
        assert with_clause.imbalance_cashflow == no_clause.imbalance_cashflow
        assert with_clause.shortfall_mwh == no_clause.shortfall_mwh
        assert with_clause.excess_mwh == no_clause.excess_mwh
        assert with_clause.own_generation_delivered_mwh == no_clause.own_generation_delivered_mwh


# --- Property 88 — ledger reconciliation for all term combinations (Requirement 5.3) ---


@st.composite
def _ppa_terms_combinations(draw: st.DrawFn) -> PpaTerms:
    price = None
    if draw(st.booleans()):
        floor, cap = draw(_floor_cap_pairs())
        price = PpaPriceTerms(floor_price_per_mwh=floor, cap_price_per_mwh=cap)
    negative_price = None
    if draw(st.booleans()):
        negative_price = NegativePriceClause(
            treatment=draw(st.sampled_from(list(NegativePriceTreatment))),
            threshold_per_mwh=draw(
                st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)
            ),
        )
    volume = None
    if draw(st.booleans()):
        tolerance = None
        if draw(st.booleans()):
            tolerance = PpaToleranceBand(
                min_fraction=draw(
                    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
                max_fraction=draw(
                    st.floats(min_value=1.0, max_value=2.0, allow_nan=False, allow_infinity=False)
                ),
                penalty_per_mwh=draw(
                    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
                ),
            )
        volume = PpaVolumeTerms(
            curtailment=draw(st.sampled_from(list(CurtailmentTreatment))), tolerance=tolerance
        )
    return PpaTerms(price=price, negative_price=negative_price, volume=volume)


# Feature: ppa-contract-terms, Property 88: ledger reconciliation for all term combinations
@given(
    terms=_ppa_terms_combinations(),
    settlement_type=_SETTLEMENT_TYPES,
    base_price=_FINITE,
    contracted_mwh=_NON_NEG,
    metered_generation_mwh=_NON_NEG,
    spot_price_per_mwh=_FINITE,
    curtailed_mwh=_NON_NEG,
)
def test_property_88_component_sum_reconciles_for_every_term_combination(
    terms: PpaTerms,
    settlement_type: PpaSettlementType,
    base_price: float,
    contracted_mwh: float,
    metered_generation_mwh: float,
    spot_price_per_mwh: float,
    curtailed_mwh: float,
) -> None:
    contract = _contract(settlement_type, terms, fixed_price_per_mwh=base_price)
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=contracted_mwh,
        metered_generation_mwh=metered_generation_mwh,
        spot_price_per_mwh=spot_price_per_mwh,
        curtailed_mwh=curtailed_mwh,
    )
    assert math.isclose(result.component_sum, result.net_cashflow, rel_tol=0.0, abs_tol=1e-9)


# --- Property 89 — curtailment monotonicity (Requirement 4) -----------------


# Feature: ppa-contract-terms, Property 89: curtailment monotonicity
#
# AMENDED 2026-07-19 (code review FIX 1): this property now requires spot_price_per_mwh
# >= 0. Under the corrected indifference semantics, DEEMED_GENERATION's make-whole is
# priced at the (signed) spot price -- for a PHYSICAL PPA the make-whole is folded into
# an *avoided* shortfall purchase at shortfall_price (which defaults to spot), and for a
# FINANCIAL_CFD it is `deemed_generation_mwh * spot_price_per_mwh` directly. When spot is
# negative, being made whole for curtailed energy at a negative price is a genuine
# producer *cost* relative to PRODUCER_BEARS (which pays nothing for curtailed MWh at
# all) -- so DEEMED_GENERATION's net cash flow can fall *below* PRODUCER_BEARS's for
# spot < 0. This inversion is economically correct (bearing curtailment is the better
# outcome exactly when the alternative would credit negatively-priced energy), not a
# defect; the monotonicity property is scoped to spot >= 0, where the original intuition
# ("being made whole is never worse") holds.
@given(
    settlement_type=_SETTLEMENT_TYPES,
    base_price=st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    contracted_mwh=_NON_NEG,
    metered_generation_mwh=_NON_NEG,
    spot_price_per_mwh=_NON_NEG,
    curtailed_mwh=_NON_NEG,
)
def test_property_89_deemed_generation_net_at_least_producer_bears(
    settlement_type: PpaSettlementType,
    base_price: float,
    contracted_mwh: float,
    metered_generation_mwh: float,
    spot_price_per_mwh: float,
    curtailed_mwh: float,
) -> None:
    # No floor/cap/negative-price clause attached: K_eff == base_price >= 0 always,
    # satisfying the property's "effective fixed price >= 0" precondition.
    kwargs = {
        "contracted_mwh": contracted_mwh,
        "metered_generation_mwh": metered_generation_mwh,
        "spot_price_per_mwh": spot_price_per_mwh,
        "curtailed_mwh": curtailed_mwh,
    }
    deemed = settle_ppa_interval(
        _contract(
            settlement_type,
            PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
            fixed_price_per_mwh=base_price,
        ),
        _INTERVAL,
        **kwargs,
    )
    bears = settle_ppa_interval(
        _contract(
            settlement_type,
            PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.PRODUCER_BEARS)),
            fixed_price_per_mwh=base_price,
        ),
        _INTERVAL,
        **kwargs,
    )
    assert deemed.net_cashflow >= bears.net_cashflow - 1e-9


# --- Property 90 — embedded-vs-overlay cross-check (Requirement 8.3) --------


# Feature: ppa-contract-terms, Property 90: embedded-vs-overlay cross-check
#
# Replicable configuration: an embedded PpaPriceTerms floor is a deterministic
# clamp on K_eff -- it does not reference spot at all, unlike a
# PowerHedgeContract FLOOR (a genuine spot-linked option payoff). The two are
# NOT interchangeable in general (this is exactly why they are documented as
# economically distinct -- Requirement 8.3). They coincide only for the single
# already-*realized* spot value of one settled interval, by construing the
# overlay's strike relative to that realized spot:
#   embedded:      K_eff = max(F, Fl); ppa_cashflow = contracted * (max(F, Fl) - spot)
#   two-instrument: ppa_cashflow = contracted * (F - spot)
#                   + max(strike - spot, 0) * contracted   [long floor, no premium]
# Choosing strike = spot + max(0, Fl - F) makes the option leg pay out exactly
# max(0, Fl - F) * contracted for *this* realized spot, so the two totals match.
# This is the "replicable configuration" the design scopes Property 90 to: a
# forward-looking option overlay generally cannot replicate a spot-independent
# embedded bound, but a realized-settlement cross-check with the strike fixed
# after the fact can.
@given(
    contracted_mwh=st.floats(min_value=0.01, max_value=1e4, allow_nan=False, allow_infinity=False),
    metered_generation_mwh=_NON_NEG,
    base_price=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    floor_price=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    spot_price_per_mwh=st.floats(
        min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False
    ),
)
def test_property_90_embedded_floor_replicable_by_overlay_for_a_realized_spot(
    contracted_mwh: float,
    metered_generation_mwh: float,
    base_price: float,
    floor_price: float,
    spot_price_per_mwh: float,
) -> None:
    embedded = settle_ppa_interval(
        _contract(
            PpaSettlementType.FINANCIAL_CFD,
            PpaTerms(price=PpaPriceTerms(floor_price_per_mwh=floor_price)),
            fixed_price_per_mwh=base_price,
        ),
        _INTERVAL,
        contracted_mwh=contracted_mwh,
        metered_generation_mwh=metered_generation_mwh,
        spot_price_per_mwh=spot_price_per_mwh,
    )

    uplift = max(0.0, floor_price - base_price)
    hedge = PowerHedgeContract(
        hedge_id="floor-overlay",
        hedge_type=PowerHedgeType.FLOOR,
        position=PowerHedgePosition.LONG,
        start_utc=_START,
        end_utc=_END,
        volume_mwh=contracted_mwh,
        strike_per_mwh=spot_price_per_mwh + uplift,
    )
    hedge_cashflow = settle_power_hedge_interval(hedge, _INTERVAL, spot_price_per_mwh).net_cashflow
    two_instrument = settle_ppa_interval(
        _contract(PpaSettlementType.FINANCIAL_CFD, None, fixed_price_per_mwh=base_price),
        _INTERVAL,
        contracted_mwh=contracted_mwh,
        metered_generation_mwh=metered_generation_mwh,
        spot_price_per_mwh=spot_price_per_mwh,
        hedge_cashflow=hedge_cashflow,
    )
    assert math.isclose(
        embedded.net_cashflow, two_instrument.net_cashflow, rel_tol=1e-9, abs_tol=1e-6
    )


# --- Property 95 — reconciliation-identity (Requirement 9.3) ----------------


@st.composite
def _reconciliation_ledger_rows(
    draw: st.DrawFn,
) -> tuple[list[datetime], list[datetime], list[float], list[float]]:
    n = draw(st.integers(min_value=1, max_value=12))
    offsets = draw(
        st.lists(st.integers(min_value=0, max_value=395), min_size=n, max_size=n, unique=True)
    )
    offsets.sort()
    starts = [_START + timedelta(days=offset) for offset in offsets]
    ends = [start + timedelta(days=1) for start in starts]
    contracted = draw(st.lists(_NON_NEG, min_size=n, max_size=n))
    metered = draw(st.lists(_NON_NEG, min_size=n, max_size=n))
    return starts, ends, contracted, metered


# Feature: ppa-contract-terms, Property 95: reconciliation-identity
@given(
    ledger_rows=_reconciliation_ledger_rows(),
    penalty_per_mwh=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    min_fraction=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    max_fraction=st.floats(min_value=1.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    deemed_availability_fraction=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    true_up_price_per_mwh=_FINITE,
)
def test_property_95_reconciliation_totals_match_independent_period_recomputation(
    ledger_rows: tuple[list[datetime], list[datetime], list[float], list[float]],
    penalty_per_mwh: float,
    min_fraction: float,
    max_fraction: float,
    deemed_availability_fraction: float,
    true_up_price_per_mwh: float,
) -> None:
    starts, ends, contracted, metered = ledger_rows
    volume_band = PpaToleranceBand(
        min_fraction=min_fraction, max_fraction=max_fraction, penalty_per_mwh=penalty_per_mwh
    )
    availability = PpaAvailabilityGuarantee(
        deemed_availability_fraction=deemed_availability_fraction
    )
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.MONTHLY,
        true_up_price_per_mwh=true_up_price_per_mwh,
        volume_band=volume_band,
        availability=availability,
    )
    contract = _contract(PpaSettlementType.PHYSICAL, PpaTerms(reconciliation=reconciliation))
    ledger = pl.DataFrame(
        {
            "interval_start_utc": starts,
            "interval_end_utc": ends,
            "contracted_mwh": contracted,
            "metered_generation_mwh": metered,
            "effective_fixed_price_per_mwh": [70.0] * len(starts),
        }
    )
    result = reconcile_ppa_ledger(contract, ledger)

    # Independent recomputation: bucket by (year, month) in plain Python (no reuse of
    # reconcile_ppa_ledger's own grouping code), and check every period's true-up
    # against the *declared formula* (Requirement 9.3's self-reconciliation).
    buckets: dict[tuple[int, int], list[int]] = {}
    for index, start in enumerate(starts):
        buckets.setdefault((start.year, start.month), []).append(index)
    expected_period_keys = sorted(buckets, key=lambda key: min(starts[i] for i in buckets[key]))
    assert result.height == len(expected_period_keys)
    for row_index, key in enumerate(expected_period_keys):
        indices = buckets[key]
        total_contracted = sum(contracted[i] for i in indices)
        total_metered = sum(metered[i] for i in indices)
        out_of_band = volume_band.out_of_band_mwh(
            metered=total_metered, contracted=total_contracted
        )
        expected_volume_band_true_up = -volume_band.penalty_per_mwh * out_of_band
        measured_fraction = 1.0 if total_contracted == 0.0 else total_metered / total_contracted
        shortfall = availability.shortfall_fraction(measured_fraction)
        expected_availability_true_up = -true_up_price_per_mwh * shortfall * total_contracted

        row = result.row(row_index, named=True)
        assert row["interval_count"] == len(indices)
        assert math.isclose(row["total_contracted_mwh"], total_contracted, abs_tol=1e-6)
        assert math.isclose(row["total_metered_generation_mwh"], total_metered, abs_tol=1e-6)
        assert math.isclose(
            row["volume_band_true_up"], expected_volume_band_true_up, rel_tol=1e-9, abs_tol=1e-6
        )
        assert math.isclose(
            row["availability_true_up"], expected_availability_true_up, rel_tol=1e-9, abs_tol=1e-6
        )
        assert row["consecutive_hour_true_up"] == 0.0
        assert math.isclose(
            row["net_true_up"],
            row["volume_band_true_up"] + row["availability_true_up"],
            rel_tol=0.0,
            abs_tol=1e-9,
        )


# --- Property 96 — availability true-up correctness (Requirement 10) --------


# Feature: ppa-contract-terms, Property 96: availability true-up correctness
@given(
    total_contracted=st.floats(min_value=0.0, max_value=1e4, allow_nan=False, allow_infinity=False),
    total_metered=st.floats(min_value=0.0, max_value=1e4, allow_nan=False, allow_infinity=False),
    deemed_availability_fraction=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    true_up_price_per_mwh=_FINITE,
)
def test_property_96_availability_true_up_is_one_directional_shortfall_only(
    total_contracted: float,
    total_metered: float,
    deemed_availability_fraction: float,
    true_up_price_per_mwh: float,
) -> None:
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.ANNUAL,
        true_up_price_per_mwh=true_up_price_per_mwh,
        availability=PpaAvailabilityGuarantee(
            deemed_availability_fraction=deemed_availability_fraction
        ),
    )
    contract = _contract(PpaSettlementType.PHYSICAL, PpaTerms(reconciliation=reconciliation))
    ledger = pl.DataFrame(
        {
            "interval_start_utc": [_START],
            "interval_end_utc": [_START + timedelta(days=1)],
            "contracted_mwh": [total_contracted],
            "metered_generation_mwh": [total_metered],
            "effective_fixed_price_per_mwh": [70.0],
        }
    )
    result = reconcile_ppa_ledger(contract, ledger)
    availability_true_up = float(result["availability_true_up"][0])
    measured_fraction = 1.0 if total_contracted == 0.0 else total_metered / total_contracted
    if measured_fraction >= deemed_availability_fraction:
        # Measured availability beating the deemed guarantee never produces a credit:
        # the guarantee is one-directional (a declared design decision).
        assert availability_true_up == 0.0
    else:
        shortfall = deemed_availability_fraction - measured_fraction
        expected = -true_up_price_per_mwh * shortfall * total_contracted
        assert math.isclose(availability_true_up, expected, rel_tol=1e-9, abs_tol=1e-6)


# --- Property 97 — consecutive-hour locality (Requirement 11) ---------------


# Feature: ppa-contract-terms, Property 97: consecutive-hour locality
@given(
    below_pattern=st.lists(st.booleans(), min_size=1, max_size=12),
    settlement_type=_SETTLEMENT_TYPES,
    treatment=st.sampled_from(list(NegativePriceTreatment)),
    min_run_length=st.integers(min_value=2, max_value=5),
    contracted_mwh=st.floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False),
    base_price=_FINITE,
)
def test_property_97_consecutive_hour_true_up_locality_and_run_correctness(
    below_pattern: list[bool],
    settlement_type: PpaSettlementType,
    treatment: NegativePriceTreatment,
    min_run_length: int,
    contracted_mwh: float,
    base_price: float,
) -> None:
    n = len(below_pattern)
    spots = [-1.0 if below else 1.0 for below in below_pattern]
    starts = [_START + timedelta(hours=h) for h in range(n)]
    ends = [start + timedelta(hours=1) for start in starts]
    clause = NegativePriceClause(
        treatment=treatment, threshold_per_mwh=0.0, min_consecutive_intervals=min_run_length
    )
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.ANNUAL, true_up_price_per_mwh=0.0
    )
    with_clause = PpaContract(
        contract_id="ppa-eeg-prop",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=base_price,
        start_utc=_START,
        end_utc=starts[-1] + timedelta(hours=1),
        volume_basis=PpaVolumeBasis.BASELOAD,
        settlement_type=settlement_type,
        terms=PpaTerms(negative_price=clause, reconciliation=reconciliation),
    )
    no_clause = PpaContract(
        contract_id="ppa-eeg-prop",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=base_price,
        start_utc=_START,
        end_utc=starts[-1] + timedelta(hours=1),
        volume_basis=PpaVolumeBasis.BASELOAD,
        settlement_type=settlement_type,
        terms=PpaTerms(reconciliation=reconciliation),
    )
    data = pl.DataFrame(
        {
            "interval_start_utc": starts,
            "interval_end_utc": ends,
            "contracted_mwh": [contracted_mwh] * n,
            "metered_generation_mwh": [contracted_mwh] * n,
            "spot_price_per_mwh": spots,
        }
    )
    settled_with_clause = settle_ppa_frame(
        with_clause, data, imbalance_policy=MissingImbalancePricePolicy.USE_SPOT
    )
    settled_no_clause = settle_ppa_frame(
        no_clause, data, imbalance_policy=MissingImbalancePricePolicy.USE_SPOT
    )
    # Locality: a consecutive-hour clause cannot be evaluated interval-locally, so the
    # interval pass treats it as fully inert -- every row, in or out of a qualifying
    # run, is byte-identical to the no-clause ledger.
    assert settled_with_clause.equals(settled_no_clause)

    reconciliation_ledger = settled_with_clause.with_columns(pl.Series("spot_price_per_mwh", spots))
    result = reconcile_ppa_ledger(with_clause, reconciliation_ledger)

    # Independent run detection + correction (mirroring only the *declared* formula,
    # not any private implementation helper).
    expected_total = 0.0
    row = 0
    while row < n:
        if not below_pattern[row]:
            row += 1
            continue
        run_end = row
        while run_end < n and below_pattern[run_end]:
            run_end += 1
        if run_end - row >= min_run_length:
            for k in range(row, run_end):
                effective_price = float(settled_with_clause["effective_fixed_price_per_mwh"][k])
                if settlement_type is PpaSettlementType.PHYSICAL:
                    correction = -(contracted_mwh * effective_price)
                elif treatment is NegativePriceTreatment.NO_COMPENSATION:
                    correction = -(contracted_mwh * (effective_price - spots[k]))
                else:
                    correction = -(contracted_mwh * effective_price)
                expected_total += correction
        row = run_end
    assert math.isclose(
        float(result["consecutive_hour_true_up"][0]), expected_total, rel_tol=1e-9, abs_tol=1e-6
    )
