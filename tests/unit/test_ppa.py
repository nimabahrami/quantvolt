"""Hand-computed PPA settlement and realised power-option cash flows."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quantvolt import (
    CurtailmentTreatment,
    IndexationStep,
    MissingImbalancePricePolicy,
    NegativePriceClause,
    NegativePriceTreatment,
    PowerDeliveryInterval,
    PowerHedgeContract,
    PowerHedgePosition,
    PowerHedgeType,
    PpaAvailabilityGuarantee,
    PpaContract,
    PpaDataColumns,
    PpaPriceTerms,
    PpaReconciliationColumns,
    PpaReconciliationPeriod,
    PpaReconciliationTerms,
    PpaSettlementType,
    PpaTerms,
    PpaToleranceBand,
    PpaVolumeBasis,
    PpaVolumeTerms,
    power_cap_payoff,
    power_floor_payoff,
    reconcile_ppa_ledger,
    settle_ppa_frame,
    settle_ppa_interval,
)
from quantvolt.exceptions import ValidationError

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = _START + timedelta(days=1)
_INTERVAL = PowerDeliveryInterval(_START, _START + timedelta(hours=1))


def _contract(
    *,
    volume_basis: PpaVolumeBasis = PpaVolumeBasis.BASELOAD,
    settlement_type: PpaSettlementType = PpaSettlementType.PHYSICAL,
) -> PpaContract:
    return PpaContract(
        contract_id="ppa-1",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=70.0,
        start_utc=_START,
        end_utc=_END,
        volume_basis=volume_basis,
        settlement_type=settlement_type,
    )


def test_physical_shortfall_cashflow_reconciles_by_hand() -> None:
    # Contract 10 MWh at 70; generate 8; buy 2 short at 100.
    result = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=8.0,
        spot_price_per_mwh=90.0,
        shortfall_price_per_mwh=100.0,
        hedge_cashflow=30.0,
        option_payoff=20.0,
        option_premium=5.0,
        variable_cost=80.0,
        transaction_cost=2.0,
    )

    assert result.own_generation_delivered_mwh == 8.0
    assert result.shortfall_mwh == 2.0
    assert result.excess_mwh == 0.0
    assert result.ppa_cashflow == 700.0
    assert result.imbalance_cashflow == -200.0
    assert result.net_cashflow == 700.0 - 200.0 + 30.0 + 20.0 - 5.0 - 80.0 - 2.0
    assert result.component_sum == result.net_cashflow


def test_physical_excess_generation_is_sold_at_explicit_price() -> None:
    result = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=12.0,
        spot_price_per_mwh=50.0,
        excess_price_per_mwh=45.0,
    )

    assert result.shortfall_mwh == 0.0
    assert result.excess_mwh == 2.0
    assert result.ppa_cashflow == 700.0
    assert result.spot_cashflow == 90.0
    assert result.net_cashflow == 790.0


def test_negative_spot_price_flows_through_without_log_normal_assumption() -> None:
    result = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=12.0,
        spot_price_per_mwh=-50.0,
    )

    assert result.spot_cashflow == -100.0
    assert result.net_cashflow == 600.0
    assert power_floor_payoff(-50.0, 0.0, 2.0) == 100.0
    assert power_cap_payoff(-50.0, 0.0, 2.0) == 0.0


def test_financial_cfd_equals_fixed_revenue_when_generation_matches_volume() -> None:
    result = settle_ppa_interval(
        _contract(settlement_type=PpaSettlementType.FINANCIAL_CFD),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=100.0,
    )

    assert result.spot_cashflow == 1_000.0
    assert result.ppa_cashflow == -300.0
    assert result.net_cashflow == 700.0
    assert result.shortfall_mwh == result.excess_mwh == 0.0


def test_pay_as_produced_requires_metered_volume() -> None:
    with pytest.raises(ValidationError, match="pay_as_produced"):
        settle_ppa_interval(
            _contract(volume_basis=PpaVolumeBasis.PAY_AS_PRODUCED),
            _INTERVAL,
            contracted_mwh=10.0,
            metered_generation_mwh=9.0,
            spot_price_per_mwh=50.0,
        )


def test_interval_outside_term_and_negative_volume_are_rejected() -> None:
    outside = PowerDeliveryInterval(_END, _END + timedelta(hours=1))
    with pytest.raises(ValidationError, match="outside PPA term"):
        settle_ppa_interval(
            _contract(),
            outside,
            contracted_mwh=1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=50.0,
        )
    with pytest.raises(ValidationError, match="contracted_mwh"):
        settle_ppa_interval(
            _contract(),
            _INTERVAL,
            contracted_mwh=-1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=50.0,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_market_inputs_are_rejected(bad: float) -> None:
    with pytest.raises(ValidationError, match="spot_price_per_mwh"):
        settle_ppa_interval(
            _contract(),
            _INTERVAL,
            contracted_mwh=1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=bad,
        )


def _caller_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "from": [_START, _START + timedelta(hours=1)],
            "to": [_START + timedelta(hours=1), _START + timedelta(hours=2)],
            "nomination": [10.0, 10.0],
            "meter": [8.0, 12.0],
            "day_ahead": [90.0, 50.0],
            "buy_imbalance": [100.0, 110.0],
            "sell_imbalance": [40.0, 45.0],
        }
    )


_CALLER_COLUMNS = PpaDataColumns(
    interval_start_utc="from",
    interval_end_utc="to",
    contracted_mwh="nomination",
    metered_generation_mwh="meter",
    spot_price_per_mwh="day_ahead",
    shortfall_price_per_mwh="buy_imbalance",
    excess_price_per_mwh="sell_imbalance",
)


def test_frame_settlement_accepts_caller_column_mapping_and_reconciles() -> None:
    source = _caller_frame()
    original = source.clone()

    ledger = settle_ppa_frame(_contract(), source, columns=_CALLER_COLUMNS)

    assert source.equals(original)
    assert ledger["input_row"].to_list() == [0, 1]
    assert ledger["shortfall_mwh"].to_list() == [2.0, 0.0]
    assert ledger["excess_mwh"].to_list() == [0.0, 2.0]
    assert ledger["net_cashflow"].to_list() == [500.0, 790.0]
    component_sum = ledger.select(
        pl.col("ppa_cashflow")
        + pl.col("spot_cashflow")
        + pl.col("imbalance_cashflow")
        + pl.col("hedge_cashflow")
        + pl.col("option_payoff")
        - pl.col("option_premium")
        - pl.col("variable_cost")
        - pl.col("transaction_cost")
    ).to_series()
    assert component_sum.equals(ledger["net_cashflow"])


def test_physical_frame_requires_real_imbalance_prices_by_default() -> None:
    data = _caller_frame().drop("buy_imbalance", "sell_imbalance")

    with pytest.raises(ValidationError, match="missing required columns"):
        settle_ppa_frame(_contract(), data, columns=_CALLER_COLUMNS)

    ledger = settle_ppa_frame(
        _contract(),
        data,
        columns=_CALLER_COLUMNS,
        imbalance_policy=MissingImbalancePricePolicy.USE_SPOT,
    )
    assert ledger["net_cashflow"].to_list() == [520.0, 800.0]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: frame.reverse(), "sorted"),
        (lambda frame: pl.concat([frame, frame.head(1)]), "duplicate"),
        (
            lambda frame: frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 1)
                .then(pl.col("from") + timedelta(minutes=15))
                .otherwise(pl.col("from"))
                .alias("from")
            ),
            "gap or overlap",
        ),
        (
            lambda frame: frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 0)
                .then(None)
                .otherwise(pl.col("meter"))
                .alias("meter")
            ),
            "nulls",
        ),
    ],
)
def test_frame_rejects_unsafe_alignment(
    mutate: Callable[[pl.DataFrame], pl.DataFrame], message: str
) -> None:
    bad = mutate(_caller_frame())
    with pytest.raises(ValidationError, match=message):
        settle_ppa_frame(_contract(), bad, columns=_CALLER_COLUMNS)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_frame_rejects_non_finite_user_volumes(bad: float) -> None:
    data = _caller_frame().with_columns(pl.lit(bad).alias("meter"))
    with pytest.raises(ValidationError, match="metered_generation_mwh"):
        settle_ppa_frame(_contract(), data, columns=_CALLER_COLUMNS)


def test_frame_rejects_non_numeric_columns_and_invalid_policy() -> None:
    text_prices = _caller_frame().with_columns(pl.col("day_ahead").cast(pl.String))
    with pytest.raises(ValidationError, match="must be numeric"):
        settle_ppa_frame(_contract(), text_prices, columns=_CALLER_COLUMNS)
    with pytest.raises(ValidationError, match="invalid imbalance_policy"):
        settle_ppa_frame(
            _contract(),
            _caller_frame(),
            columns=_CALLER_COLUMNS,
            imbalance_policy="error",  # type: ignore[arg-type]
        )


def test_column_mapping_must_be_unambiguous() -> None:
    with pytest.raises(ValidationError, match="distinct column names"):
        PpaDataColumns(contracted_mwh="energy", metered_generation_mwh="energy")


def test_contract_rejects_non_finite_fixed_price() -> None:
    with pytest.raises(ValidationError, match="fixed_price_per_mwh"):
        PpaContract(
            contract_id="bad",
            bidding_zone="DE-LU",
            fixed_price_per_mwh=float("nan"),
            start_utc=_START,
            end_utc=_END,
            volume_basis=PpaVolumeBasis.BASELOAD,
        )


def test_typed_hedge_flows_into_ppa_ledger_without_double_counting() -> None:
    floor = PowerHedgeContract(
        hedge_id="revenue-floor",
        hedge_type=PowerHedgeType.FLOOR,
        position=PowerHedgePosition.LONG,
        start_utc=_START,
        end_utc=_END,
        volume_mwh=10.0,
        strike_per_mwh=80.0,
        allocated_premium_per_mwh=2.0,
    )
    ledger = settle_ppa_frame(_contract(), _caller_frame(), columns=_CALLER_COLUMNS, hedges=[floor])
    assert ledger["hedge_cashflow"].to_list() == [-20.0, 280.0]
    assert ledger["net_cashflow"].to_list() == [480.0, 1_070.0]

    with pytest.raises(ValidationError, match="double count"):
        settle_ppa_frame(
            _contract(),
            _caller_frame().with_columns(pl.lit(1.0).alias("manual_hedge")),
            columns=PpaDataColumns(
                interval_start_utc="from",
                interval_end_utc="to",
                contracted_mwh="nomination",
                metered_generation_mwh="meter",
                spot_price_per_mwh="day_ahead",
                shortfall_price_per_mwh="buy_imbalance",
                excess_price_per_mwh="sell_imbalance",
                hedge_cashflow="manual_hedge",
            ),
            hedges=[floor],
        )


# --- PpaContract.terms attachment and indexation cross-validation (Task 5) ---


def _terms_contract(terms: PpaTerms | None, **overrides: object) -> PpaContract:
    defaults: dict[str, object] = dict(
        contract_id="ppa-terms",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=70.0,
        start_utc=_START,
        end_utc=_END,
        volume_basis=PpaVolumeBasis.BASELOAD,
        terms=terms,
    )
    defaults.update(overrides)
    return PpaContract(**defaults)  # type: ignore[arg-type]


def test_contract_terms_none_and_empty_terms_construct_cleanly() -> None:
    assert _terms_contract(None).terms is None
    assert _terms_contract(PpaTerms()).terms == PpaTerms()


def test_contract_accepts_indexation_step_strictly_inside_the_term() -> None:
    step = IndexationStep(effective_from_utc=_START + timedelta(hours=1), fixed_price_per_mwh=80.0)
    contract = _terms_contract(PpaTerms(price=PpaPriceTerms(indexation=(step,))))
    assert contract.terms is not None
    assert contract.terms.price is not None
    assert contract.terms.price.indexation == (step,)


def test_contract_rejects_indexation_step_at_or_after_end_utc() -> None:
    step_at_end = IndexationStep(effective_from_utc=_END, fixed_price_per_mwh=80.0)
    with pytest.raises(ValidationError, match=r"indexation\[0\]"):
        _terms_contract(PpaTerms(price=PpaPriceTerms(indexation=(step_at_end,))))
    step_after_end = IndexationStep(
        effective_from_utc=_END + timedelta(hours=1), fixed_price_per_mwh=80.0
    )
    with pytest.raises(ValidationError, match=r"indexation\[0\]"):
        _terms_contract(PpaTerms(price=PpaPriceTerms(indexation=(step_after_end,))))


def test_contract_rejects_indexation_step_before_start_utc() -> None:
    step_before_start = IndexationStep(
        effective_from_utc=_START - timedelta(hours=1), fixed_price_per_mwh=80.0
    )
    with pytest.raises(ValidationError, match=r"indexation\[0\]"):
        _terms_contract(PpaTerms(price=PpaPriceTerms(indexation=(step_before_start,))))


def test_contract_accepts_step_exactly_at_start_utc() -> None:
    step_at_start = IndexationStep(effective_from_utc=_START, fixed_price_per_mwh=80.0)
    contract = _terms_contract(PpaTerms(price=PpaPriceTerms(indexation=(step_at_start,))))
    assert contract.terms is not None


def test_contract_rejects_wrong_type_terms() -> None:
    with pytest.raises(ValidationError, match="terms"):
        _terms_contract(object())  # type: ignore[arg-type]


# --- K_eff resolution: indexation -> clamp -> negative-price clause (Task 7) ---


def test_k_eff_resolves_indexation_then_clamp() -> None:
    step_time = _START + timedelta(hours=1)
    price_terms = PpaPriceTerms(
        floor_price_per_mwh=30.0,
        indexation=(IndexationStep(effective_from_utc=step_time, fixed_price_per_mwh=10.0),),
    )
    contract = _terms_contract(
        PpaTerms(price=price_terms),
        fixed_price_per_mwh=50.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    before_step = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=50.0,
    )
    assert before_step.effective_fixed_price_per_mwh == 50.0  # base, floor(30) does not bind

    after_step_interval = PowerDeliveryInterval(step_time, step_time + timedelta(hours=1))
    after_step = settle_ppa_interval(
        _terms_contract(
            PpaTerms(price=price_terms),
            fixed_price_per_mwh=50.0,
            settlement_type=PpaSettlementType.PHYSICAL,
        ),
        after_step_interval,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=50.0,
    )
    # step price (10) is below the floor (30): floor binds after indexation.
    assert after_step.effective_fixed_price_per_mwh == 30.0
    assert after_step.ppa_cashflow == 300.0


@pytest.mark.parametrize("spot", [-0.01, 0.0, 0.01])
def test_negative_price_clause_triggers_strictly_below_threshold(spot: float) -> None:
    clause = NegativePriceClause(
        treatment=NegativePriceTreatment.PRICE_AT_ZERO, threshold_per_mwh=0.0
    )
    contract = _terms_contract(
        PpaTerms(negative_price=clause),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=spot,
    )
    if spot < 0.0:
        assert result.effective_fixed_price_per_mwh == 0.0
        assert result.ppa_cashflow == 0.0
    else:
        assert result.effective_fixed_price_per_mwh == 70.0
        assert result.ppa_cashflow == 700.0


def test_no_compensation_and_price_at_zero_agree_for_physical() -> None:
    contract_kwargs = dict(
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    settle_kwargs = dict(contracted_mwh=10.0, metered_generation_mwh=8.0, spot_price_per_mwh=-10.0)
    no_compensation = settle_ppa_interval(
        _terms_contract(
            PpaTerms(
                negative_price=NegativePriceClause(treatment=NegativePriceTreatment.NO_COMPENSATION)
            ),
            **contract_kwargs,
        ),
        _INTERVAL,
        **settle_kwargs,
    )
    price_at_zero = settle_ppa_interval(
        _terms_contract(
            PpaTerms(
                negative_price=NegativePriceClause(treatment=NegativePriceTreatment.PRICE_AT_ZERO)
            ),
            **contract_kwargs,
        ),
        _INTERVAL,
        **settle_kwargs,
    )
    assert no_compensation.ppa_cashflow == price_at_zero.ppa_cashflow == 0.0
    # Physical imbalance legs are unaffected by the negative-price clause.
    assert no_compensation.imbalance_cashflow == price_at_zero.imbalance_cashflow


def test_no_compensation_and_price_at_zero_differ_for_financial_cfd() -> None:
    contract_kwargs = dict(
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.FINANCIAL_CFD,
    )
    settle_kwargs = dict(contracted_mwh=10.0, metered_generation_mwh=10.0, spot_price_per_mwh=-10.0)
    no_compensation = settle_ppa_interval(
        _terms_contract(
            PpaTerms(
                negative_price=NegativePriceClause(treatment=NegativePriceTreatment.NO_COMPENSATION)
            ),
            **contract_kwargs,
        ),
        _INTERVAL,
        **settle_kwargs,
    )
    price_at_zero = settle_ppa_interval(
        _terms_contract(
            PpaTerms(
                negative_price=NegativePriceClause(treatment=NegativePriceTreatment.PRICE_AT_ZERO)
            ),
            **contract_kwargs,
        ),
        _INTERVAL,
        **settle_kwargs,
    )
    # NO_COMPENSATION suspends the whole difference payment; PRICE_AT_ZERO still pays
    # (0 - spot) on the contracted volume. The spot sale of metered generation, in
    # contrast, is unaffected by either treatment.
    assert no_compensation.ppa_cashflow == 0.0
    assert price_at_zero.ppa_cashflow == 100.0
    assert no_compensation.spot_cashflow == price_at_zero.spot_cashflow == -100.0


def test_deemed_generation_pays_curtailed_mwh_at_effective_price() -> None:
    # AMENDED 2026-07-19 (code review FIX 1): DEEMED_GENERATION no longer adds
    # curtailed_mwh onto the contracted fixed leg; curtailed MWh count AS delivery
    # toward the contracted volume, capped by the metered/contracted gap. Here
    # metered already equals contracted (no shortfall gap), so 3.0 MWh of
    # curtailment offsets nothing and is credited against a zero gap.
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=50.0,
        curtailed_mwh=3.0,
    )
    assert result.shortfall_mwh == 0.0
    assert result.deemed_generation_mwh == 0.0
    assert result.ppa_cashflow == 700.0


def test_deemed_generation_offsets_shortfall_up_to_the_metered_gap_physical() -> None:
    # Curtailed MWh credit against the metered/contracted gap: here the gap is 20
    # (100 - 80) and only 15 MWh were curtailed, so deemed_generation_mwh == 15.0 (all
    # of it credited) and the remaining 5 MWh of gap is a genuine shortfall, bought at
    # shortfall_price. ppa_cashflow is the plain contracted * K_eff (no add-on).
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=100.0,
        metered_generation_mwh=80.0,
        spot_price_per_mwh=60.0,
        curtailed_mwh=15.0,
    )
    assert result.deemed_generation_mwh == 15.0
    assert result.shortfall_mwh == 5.0
    assert result.ppa_cashflow == 100.0 * 70.0
    assert result.imbalance_cashflow == -5.0 * 60.0
    assert result.component_sum == result.net_cashflow


def test_deemed_generation_curtailment_indifference_matches_full_delivery_physical() -> None:
    """Verifier's indifference scenario (code review FIX 1): a producer curtailed by
    exactly the metered/contracted gap is indifferent to full delivery -- the net
    cash flow must equal what settlement would produce had it delivered the
    contracted MWh in full, with zero curtailment (contracted=100, metered=60,
    curtailed=40, K=50, spot=30 -> net 5000, not 5800).
    """
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
        fixed_price_per_mwh=50.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    curtailed = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=100.0,
        metered_generation_mwh=60.0,
        spot_price_per_mwh=30.0,
        curtailed_mwh=40.0,
    )
    full_delivery = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=100.0,
        metered_generation_mwh=100.0,
        spot_price_per_mwh=30.0,
        curtailed_mwh=0.0,
    )
    assert curtailed.net_cashflow == full_delivery.net_cashflow == 5000.0
    assert curtailed.component_sum == curtailed.net_cashflow


def test_deemed_generation_curtailment_indifference_matches_full_delivery_financial_cfd() -> None:
    """Same indifference scenario, FINANCIAL_CFD: the deemed make-whole pays the
    curtailed MWh's lost spot revenue at signed spot, carried on ppa_cashflow, while
    spot_cashflow keeps its plain metered * spot meaning (2000 + 1200 ppa, 1800 spot
    = 5000, matching full delivery).
    """
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
        fixed_price_per_mwh=50.0,
        settlement_type=PpaSettlementType.FINANCIAL_CFD,
    )
    curtailed = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=100.0,
        metered_generation_mwh=60.0,
        spot_price_per_mwh=30.0,
        curtailed_mwh=40.0,
    )
    full_delivery = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=100.0,
        metered_generation_mwh=100.0,
        spot_price_per_mwh=30.0,
        curtailed_mwh=0.0,
    )
    assert curtailed.deemed_generation_mwh == 40.0
    assert curtailed.ppa_cashflow == pytest.approx(2000.0 + 1200.0)
    assert curtailed.spot_cashflow == pytest.approx(1800.0)
    assert curtailed.net_cashflow == full_delivery.net_cashflow == 5000.0
    assert curtailed.component_sum == curtailed.net_cashflow


def test_producer_bears_curtailed_mwh_earns_nothing() -> None:
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.PRODUCER_BEARS)),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=50.0,
        curtailed_mwh=3.0,
    )
    assert result.deemed_generation_mwh == 0.0
    assert result.ppa_cashflow == 700.0
    assert result.curtailed_mwh == 3.0


@pytest.mark.parametrize(
    ("metered_generation_mwh", "expected_penalty"),
    [
        (95.0, 0.0),
        (90.0, 0.0),
        (110.0, 0.0),
        (80.0, -50.0),
        (120.0, -50.0),
    ],
)
def test_tolerance_band_penalizes_only_out_of_band_mwh(
    metered_generation_mwh: float, expected_penalty: float
) -> None:
    band = PpaToleranceBand(min_fraction=0.9, max_fraction=1.1, penalty_per_mwh=5.0)
    contract = _terms_contract(
        PpaTerms(
            volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.PRODUCER_BEARS, tolerance=band)
        ),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    result = settle_ppa_interval(
        contract,
        _INTERVAL,
        contracted_mwh=100.0,
        metered_generation_mwh=metered_generation_mwh,
        spot_price_per_mwh=50.0,
    )
    assert result.tolerance_penalty == pytest.approx(expected_penalty)
    assert result.component_sum == result.net_cashflow


def test_curtailed_mwh_must_be_non_negative_and_finite() -> None:
    with pytest.raises(ValidationError, match="curtailed_mwh"):
        settle_ppa_interval(
            _contract(),
            _INTERVAL,
            contracted_mwh=1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=50.0,
            curtailed_mwh=-1.0,
        )


def test_terms_none_and_empty_terms_are_byte_identical_to_as_built() -> None:
    baseline = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=8.0,
        spot_price_per_mwh=90.0,
        shortfall_price_per_mwh=100.0,
    )
    with_empty_terms = settle_ppa_interval(
        _terms_contract(PpaTerms(), fixed_price_per_mwh=70.0),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=8.0,
        spot_price_per_mwh=90.0,
        shortfall_price_per_mwh=100.0,
    )
    assert baseline.net_cashflow == with_empty_terms.net_cashflow
    assert baseline.ppa_cashflow == with_empty_terms.ppa_cashflow
    assert baseline.imbalance_cashflow == with_empty_terms.imbalance_cashflow
    assert with_empty_terms.effective_fixed_price_per_mwh == 70.0
    assert with_empty_terms.curtailed_mwh == 0.0
    assert with_empty_terms.deemed_generation_mwh == 0.0
    assert with_empty_terms.tolerance_penalty == 0.0


# --- Frame settlement: curtailed-MWh column (Task 9) ------------------------


def test_frame_requires_curtailed_mwh_column_when_deemed_generation_is_active() -> None:
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    data = _caller_frame()
    with pytest.raises(ValidationError, match="curtailed_mwh"):
        settle_ppa_frame(contract, data, columns=_CALLER_COLUMNS)


def test_frame_settles_deemed_generation_with_curtailed_mwh_column() -> None:
    contract = _terms_contract(
        PpaTerms(volume=PpaVolumeTerms(curtailment=CurtailmentTreatment.DEEMED_GENERATION)),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    data = _caller_frame().with_columns(pl.Series("curtailed", [1.0, 2.0]))
    columns = PpaDataColumns(
        interval_start_utc="from",
        interval_end_utc="to",
        contracted_mwh="nomination",
        metered_generation_mwh="meter",
        spot_price_per_mwh="day_ahead",
        shortfall_price_per_mwh="buy_imbalance",
        excess_price_per_mwh="sell_imbalance",
        curtailed_mwh="curtailed",
    )
    ledger = settle_ppa_frame(contract, data, columns=columns)
    assert ledger["curtailed_mwh"].to_list() == [1.0, 2.0]
    # AMENDED 2026-07-19 (code review FIX 1): deemed_generation_mwh is the curtailed
    # MWh actually credited against the metered/contracted gap, not the raw curtailed
    # input. Row 0 (nomination=10, meter=8): gap=2.0, curtailed=1.0 -> credited in full.
    # Row 1 (nomination=10, meter=12): gap=0.0 (meter already exceeds nomination), so
    # the 2.0 MWh of curtailment credits against nothing -> 0.0.
    assert ledger["deemed_generation_mwh"].to_list() == [1.0, 0.0]
    assert ledger["effective_fixed_price_per_mwh"].to_list() == [70.0, 70.0]
    assert ledger["ppa_cashflow"].to_list() == [700.0, 700.0]


def test_frame_defaults_curtailed_mwh_to_zero_when_not_required_and_absent() -> None:
    ledger = settle_ppa_frame(_contract(), _caller_frame(), columns=_CALLER_COLUMNS)
    assert ledger["curtailed_mwh"].to_list() == [0.0, 0.0]
    assert ledger["deemed_generation_mwh"].to_list() == [0.0, 0.0]
    assert ledger["tolerance_penalty"].to_list() == [0.0, 0.0]
    assert ledger["effective_fixed_price_per_mwh"].to_list() == [70.0, 70.0]


def test_frame_identity_when_terms_is_none_or_empty_ppaterms() -> None:
    no_terms_ledger = settle_ppa_frame(_contract(), _caller_frame(), columns=_CALLER_COLUMNS)
    empty_terms_ledger = settle_ppa_frame(
        _terms_contract(
            PpaTerms(),
            bidding_zone="DE-LU",
            fixed_price_per_mwh=70.0,
            volume_basis=PpaVolumeBasis.BASELOAD,
        ),
        _caller_frame(),
        columns=_CALLER_COLUMNS,
    )
    shared_columns = [
        c
        for c in no_terms_ledger.columns
        if c
        not in {
            "effective_fixed_price_per_mwh",
            "curtailed_mwh",
            "deemed_generation_mwh",
            "tolerance_penalty",
        }
    ]
    assert no_terms_ledger.select(shared_columns).equals(empty_terms_ledger.select(shared_columns))


# --- reconcile_ppa_ledger — period reconciliation and true-up (Phase 6, Req 9-11) ---


def _reconciliation_contract(
    reconciliation: PpaReconciliationTerms,
    *,
    negative_price: NegativePriceClause | None = None,
    **overrides: object,
) -> PpaContract:
    defaults: dict[str, object] = dict(
        contract_id="ppa-reconciliation",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=70.0,
        start_utc=_START,
        end_utc=_START + timedelta(days=400),
        volume_basis=PpaVolumeBasis.BASELOAD,
        settlement_type=PpaSettlementType.PHYSICAL,
        terms=PpaTerms(reconciliation=reconciliation, negative_price=negative_price),
    )
    defaults.update(overrides)
    return PpaContract(**defaults)  # type: ignore[arg-type]


def test_reconcile_ppa_ledger_requires_reconciliation_terms() -> None:
    contract = _terms_contract(None)
    ledger = pl.DataFrame(
        {
            "interval_start_utc": [_START],
            "interval_end_utc": [_START + timedelta(hours=1)],
            "contracted_mwh": [10.0],
            "metered_generation_mwh": [10.0],
            "effective_fixed_price_per_mwh": [70.0],
        }
    )
    with pytest.raises(ValidationError, match="reconciliation"):
        reconcile_ppa_ledger(contract, ledger)


def test_reconcile_ppa_ledger_requires_declared_columns() -> None:
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.MONTHLY, true_up_price_per_mwh=10.0
    )
    contract = _reconciliation_contract(reconciliation)
    ledger = pl.DataFrame({"interval_start_utc": [_START]})
    with pytest.raises(ValidationError, match="missing required columns"):
        reconcile_ppa_ledger(contract, ledger)


def test_reconcile_ppa_ledger_hand_computed_volume_band_and_availability_true_up() -> None:
    # Hand-computed: Jan (2 rows) contracted 200, metered 170; band [180, 220] over
    # 200 -> 10 MWh below the lower bound -> -5/MWh * 10 = -50. Availability: measured
    # 170/200 = 0.85 vs deemed 0.95 -> 0.10 shortfall * 200 MWh * 100/MWh = -2000.
    # Feb (1 row) contracted 50, metered 40; band [45, 55] -> 5 MWh below -> -5*5 = -25.
    # Availability: measured 40/50 = 0.8 vs deemed 0.95 -> 0.15 * 50 * 100 = -750.
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.MONTHLY,
        true_up_price_per_mwh=100.0,
        volume_band=PpaToleranceBand(min_fraction=0.9, max_fraction=1.1, penalty_per_mwh=5.0),
        availability=PpaAvailabilityGuarantee(deemed_availability_fraction=0.95),
    )
    contract = _reconciliation_contract(reconciliation)
    ledger = pl.DataFrame(
        {
            "interval_start_utc": [
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 15, tzinfo=UTC),
                datetime(2026, 2, 1, tzinfo=UTC),
            ],
            "interval_end_utc": [
                datetime(2026, 1, 2, tzinfo=UTC),
                datetime(2026, 1, 16, tzinfo=UTC),
                datetime(2026, 2, 2, tzinfo=UTC),
            ],
            "contracted_mwh": [100.0, 100.0, 50.0],
            "metered_generation_mwh": [80.0, 90.0, 40.0],
            "effective_fixed_price_per_mwh": [70.0, 70.0, 70.0],
        }
    )
    result = reconcile_ppa_ledger(contract, ledger)
    assert result["interval_count"].to_list() == [2, 1]
    assert result["total_contracted_mwh"].to_list() == pytest.approx([200.0, 50.0])
    assert result["total_metered_generation_mwh"].to_list() == pytest.approx([170.0, 40.0])
    assert result["volume_band_true_up"].to_list() == pytest.approx([-50.0, -25.0])
    assert result["availability_true_up"].to_list() == pytest.approx([-2000.0, -750.0])
    assert result["consecutive_hour_true_up"].to_list() == [0.0, 0.0]
    assert result["net_true_up"].to_list() == pytest.approx([-2050.0, -775.0])


def test_reconcile_ppa_ledger_quarterly_and_annual_bucketing() -> None:
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.QUARTERLY, true_up_price_per_mwh=10.0
    )
    contract = _reconciliation_contract(reconciliation)
    ledger = pl.DataFrame(
        {
            "interval_start_utc": [
                datetime(2026, 1, 10, tzinfo=UTC),
                datetime(2026, 3, 20, tzinfo=UTC),
                datetime(2026, 4, 5, tzinfo=UTC),
            ],
            "interval_end_utc": [
                datetime(2026, 1, 11, tzinfo=UTC),
                datetime(2026, 3, 21, tzinfo=UTC),
                datetime(2026, 4, 6, tzinfo=UTC),
            ],
            "contracted_mwh": [10.0, 20.0, 30.0],
            "metered_generation_mwh": [10.0, 20.0, 30.0],
            "effective_fixed_price_per_mwh": [70.0, 70.0, 70.0],
        }
    )
    quarterly = reconcile_ppa_ledger(contract, ledger)
    assert quarterly["interval_count"].to_list() == [2, 1]  # Q1 (Jan+Mar), Q2 (Apr)
    assert quarterly["total_contracted_mwh"].to_list() == pytest.approx([30.0, 30.0])
    # no volume_band/availability configured:
    assert quarterly["net_true_up"].to_list() == [0.0, 0.0]

    annual_contract = _reconciliation_contract(
        PpaReconciliationTerms(period=PpaReconciliationPeriod.ANNUAL, true_up_price_per_mwh=10.0)
    )
    annual = reconcile_ppa_ledger(annual_contract, ledger)
    assert annual["interval_count"].to_list() == [3]
    assert annual["total_contracted_mwh"].to_list() == pytest.approx([60.0])


def test_reconciliation_columns_rejects_duplicate_names() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        PpaReconciliationColumns(contracted_mwh="x", metered_generation_mwh="x")


def test_reconcile_ppa_ledger_accepts_custom_column_mapping() -> None:
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.MONTHLY, true_up_price_per_mwh=10.0
    )
    contract = _reconciliation_contract(reconciliation)
    ledger = pl.DataFrame(
        {
            "from": [_START],
            "to": [_START + timedelta(hours=1)],
            "nomination": [10.0],
            "meter": [10.0],
            "k_eff": [70.0],
        }
    )
    columns = PpaReconciliationColumns(
        interval_start_utc="from",
        interval_end_utc="to",
        contracted_mwh="nomination",
        metered_generation_mwh="meter",
        effective_fixed_price_per_mwh="k_eff",
    )
    result = reconcile_ppa_ledger(contract, ledger, columns=columns)
    assert result["total_contracted_mwh"].to_list() == [10.0]


def test_reconcile_ppa_ledger_requires_spot_price_column_for_consecutive_hour_trigger() -> None:
    clause = NegativePriceClause(
        treatment=NegativePriceTreatment.NO_COMPENSATION, min_consecutive_intervals=2
    )
    reconciliation = PpaReconciliationTerms(
        period=PpaReconciliationPeriod.ANNUAL, true_up_price_per_mwh=0.0
    )
    contract = _reconciliation_contract(reconciliation, negative_price=clause)
    ledger = pl.DataFrame(
        {
            "interval_start_utc": [_START],
            "interval_end_utc": [_START + timedelta(hours=1)],
            "contracted_mwh": [10.0],
            "metered_generation_mwh": [10.0],
            "effective_fixed_price_per_mwh": [70.0],
        }
    )
    with pytest.raises(ValidationError, match="spot_price_per_mwh"):
        reconcile_ppa_ledger(contract, ledger)


def test_settle_ppa_interval_ignores_negative_price_clause_when_consecutive_hour_trigger_set() -> (
    None
):
    """Requirement 3.7/11.2: a consecutive-hour clause cannot be evaluated interval-locally,
    so the interval pass treats it as inert -- byte-identical to no clause at all."""
    clause_with_trigger = NegativePriceClause(
        treatment=NegativePriceTreatment.PRICE_AT_ZERO,
        threshold_per_mwh=0.0,
        min_consecutive_intervals=2,
    )
    contract = _terms_contract(
        PpaTerms(negative_price=clause_with_trigger),
        fixed_price_per_mwh=70.0,
        settlement_type=PpaSettlementType.PHYSICAL,
    )
    no_clause = _terms_contract(
        None, fixed_price_per_mwh=70.0, settlement_type=PpaSettlementType.PHYSICAL
    )
    kwargs = dict(contracted_mwh=10.0, metered_generation_mwh=10.0, spot_price_per_mwh=-5.0)
    with_trigger = settle_ppa_interval(contract, _INTERVAL, **kwargs)  # type: ignore[arg-type]
    without_clause = settle_ppa_interval(no_clause, _INTERVAL, **kwargs)  # type: ignore[arg-type]
    assert with_trigger.effective_fixed_price_per_mwh == 70.0
    assert with_trigger.ppa_cashflow == without_clause.ppa_cashflow == 700.0


def _consecutive_hour_contract(
    settlement_type: PpaSettlementType, treatment: NegativePriceTreatment
) -> PpaContract:
    clause = NegativePriceClause(
        treatment=treatment, threshold_per_mwh=0.0, min_consecutive_intervals=3
    )
    return PpaContract(
        contract_id="ppa-eeg",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=70.0,
        start_utc=_START,
        end_utc=_START + timedelta(hours=6),
        volume_basis=PpaVolumeBasis.BASELOAD,
        settlement_type=settlement_type,
        terms=PpaTerms(
            negative_price=clause,
            reconciliation=PpaReconciliationTerms(
                period=PpaReconciliationPeriod.ANNUAL, true_up_price_per_mwh=0.0
            ),
        ),
    )


def _consecutive_hour_frame(spots: list[float]) -> pl.DataFrame:
    starts = [_START + timedelta(hours=h) for h in range(6)]
    ends = [_START + timedelta(hours=h + 1) for h in range(6)]
    return pl.DataFrame(
        {
            "interval_start_utc": starts,
            "interval_end_utc": ends,
            "contracted_mwh": [10.0] * 6,
            "metered_generation_mwh": [10.0] * 6,
            "spot_price_per_mwh": spots,
        }
    )


def test_reconcile_ppa_ledger_consecutive_hour_true_up_hand_computed_physical() -> None:
    # Rows 0-1: spot < 0 for a run of length 2 (< 3) -> no correction.
    # Rows 3-5: spot < 0 for a run of length 3 (>= 3) -> qualifies.
    # PHYSICAL corrects each qualifying row by -(contracted * K_eff) = -(10 * 70) = -700;
    # three rows -> -2100 total.
    spots = [-1.0, -1.0, 5.0, -2.0, -2.0, -2.0]
    contract = _consecutive_hour_contract(
        PpaSettlementType.PHYSICAL, NegativePriceTreatment.NO_COMPENSATION
    )
    data = _consecutive_hour_frame(spots)
    ledger = settle_ppa_frame(contract, data, imbalance_policy=MissingImbalancePricePolicy.USE_SPOT)
    # Interval-pass locality: K_eff and ppa_cashflow are the plain contract values on every
    # row, including rows 3-5 whose spot is strictly below the threshold, because the
    # clause is fully inert at the interval level whenever min_consecutive_intervals is set.
    assert ledger["effective_fixed_price_per_mwh"].to_list() == [70.0] * 6
    assert ledger["ppa_cashflow"].to_list() == [700.0] * 6

    reconciliation_ledger = ledger.with_columns(pl.Series("spot_price_per_mwh", spots))
    result = reconcile_ppa_ledger(contract, reconciliation_ledger)
    assert result["consecutive_hour_true_up"].to_list() == pytest.approx([-2100.0])


def test_reconcile_ppa_ledger_consecutive_hour_true_up_financial_cfd_no_compensation() -> None:
    # NO_COMPENSATION zeroes the whole difference payment for a qualifying row:
    # -(contracted * (K_eff - spot)) = -(10 * (70 - (-2))) = -720; three rows -> -2160.
    spots = [-1.0, -1.0, 5.0, -2.0, -2.0, -2.0]
    contract = _consecutive_hour_contract(
        PpaSettlementType.FINANCIAL_CFD, NegativePriceTreatment.NO_COMPENSATION
    )
    data = _consecutive_hour_frame(spots)
    ledger = settle_ppa_frame(contract, data)
    reconciliation_ledger = ledger.with_columns(pl.Series("spot_price_per_mwh", spots))
    result = reconcile_ppa_ledger(contract, reconciliation_ledger)
    assert result["consecutive_hour_true_up"].to_list() == pytest.approx([-2160.0])


def test_reconcile_ppa_ledger_consecutive_hour_true_up_financial_cfd_price_at_zero() -> None:
    # PRICE_AT_ZERO only zeroes K_eff's own revenue term for a qualifying row:
    # -(contracted * K_eff) = -(10 * 70) = -700; three rows -> -2100 (same as PHYSICAL).
    spots = [-1.0, -1.0, 5.0, -2.0, -2.0, -2.0]
    contract = _consecutive_hour_contract(
        PpaSettlementType.FINANCIAL_CFD, NegativePriceTreatment.PRICE_AT_ZERO
    )
    data = _consecutive_hour_frame(spots)
    ledger = settle_ppa_frame(contract, data)
    reconciliation_ledger = ledger.with_columns(pl.Series("spot_price_per_mwh", spots))
    result = reconcile_ppa_ledger(contract, reconciliation_ledger)
    assert result["consecutive_hour_true_up"].to_list() == pytest.approx([-2100.0])


def test_reconcile_ppa_ledger_consecutive_hour_run_breaks_at_time_gap() -> None:
    """Code review FIX 2: "consecutive" means clock-time contiguous, not merely
    row-order adjacent. Rows starting 01:00, 02:00, 04:00 (a missing 03:00-04:00
    hour) are ALL below threshold; naive row adjacency would treat them as one run
    of length 3 and apply the trigger, but the 04:00 row does not clock-follow the
    02:00 row's end (03:00), so the run breaks there: the length-2 run (01:00-03:00)
    is below the length-3 minimum, and so is the length-1 run (04:00-05:00) -> a
    0.0 true-up. A fully clock-contiguous control (01:00/02:00/03:00) gets the full
    -(contracted * K_eff) * 3 = -(10 * 50) * 3 = -1500 correction.
    """
    clause = NegativePriceClause(
        treatment=NegativePriceTreatment.NO_COMPENSATION,
        threshold_per_mwh=0.0,
        min_consecutive_intervals=3,
    )
    contract = PpaContract(
        contract_id="ppa-eeg-gap",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=50.0,
        start_utc=_START,
        end_utc=_START + timedelta(hours=6),
        volume_basis=PpaVolumeBasis.BASELOAD,
        settlement_type=PpaSettlementType.PHYSICAL,
        terms=PpaTerms(
            negative_price=clause,
            reconciliation=PpaReconciliationTerms(
                period=PpaReconciliationPeriod.ANNUAL, true_up_price_per_mwh=0.0
            ),
        ),
    )

    def _frame(starts_hours: list[float], ends_hours: list[float]) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "interval_start_utc": [_START + timedelta(hours=h) for h in starts_hours],
                "interval_end_utc": [_START + timedelta(hours=h) for h in ends_hours],
                "contracted_mwh": [10.0] * len(starts_hours),
                "metered_generation_mwh": [10.0] * len(starts_hours),
                "spot_price_per_mwh": [-1.0] * len(starts_hours),
            }
        )

    gapped_data = _frame([1.0, 2.0, 4.0], [2.0, 3.0, 5.0])
    gapped_ledger = settle_ppa_frame(
        contract,
        gapped_data,
        imbalance_policy=MissingImbalancePricePolicy.USE_SPOT,
        require_contiguous=False,
    ).with_columns(pl.Series("spot_price_per_mwh", [-1.0, -1.0, -1.0]))
    gapped_result = reconcile_ppa_ledger(contract, gapped_ledger)
    assert gapped_result["consecutive_hour_true_up"].to_list() == pytest.approx([0.0])

    contiguous_data = _frame([1.0, 2.0, 3.0], [2.0, 3.0, 4.0])
    contiguous_ledger = settle_ppa_frame(
        contract,
        contiguous_data,
        imbalance_policy=MissingImbalancePricePolicy.USE_SPOT,
    ).with_columns(pl.Series("spot_price_per_mwh", [-1.0, -1.0, -1.0]))
    contiguous_result = reconcile_ppa_ledger(contract, contiguous_ledger)
    assert contiguous_result["consecutive_hour_true_up"].to_list() == pytest.approx([-1500.0])
