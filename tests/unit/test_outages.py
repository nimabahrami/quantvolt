"""Unit tests for outage data & reliability KPIs (Task 83, Requirements 26.1-26.5,
Properties 73-74). KPI values are checked against hand computations on a small dataset."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.market.outages import (
    HOURS_PER_YEAR,
    OutageDataset,
    OutageRecord,
    OutageStatus,
    OutageType,
    availability_factor,
    efor,
    equivalent_availability_factor,
    forced_outage_rate,
    mtbf,
    mttr,
    outage_frequency,
    unavailable_energy,
)

_START = datetime(2026, 1, 1, 0, 0)


def _rec(
    *,
    outage_type: OutageType = OutageType.FORCED,
    installed: float = 100.0,
    unavailable: float = 100.0,
    available: float | None = None,
    hours: float = 10.0,
    start: datetime = _START,
    actual_end: datetime | None = None,
    status: OutageStatus = OutageStatus.COMPLETED,
    revision_number: int = 0,
) -> OutageRecord:
    """Build a valid record; ``available`` defaults to ``installed - unavailable``."""
    if available is None:
        available = installed - unavailable
    return OutageRecord(
        asset_id="A1",
        unit_id="U1",
        technology="CCGT",
        market_zone="DE",
        outage_id="O1",
        outage_type=outage_type,
        status=status,
        announcement_time=start - timedelta(days=1),
        start_time=start,
        expected_end_time=start + timedelta(hours=hours),
        installed_capacity_mw=installed,
        unavailable_capacity_mw=unavailable,
        available_capacity_mw=available,
        source="TSO",
        revision_number=revision_number,
        actual_end_time=actual_end,
    )


# Primary hand-computable dataset (period_hours=100, installed=100):
#   R1 FORCED   full   (unavail=100) 10h
#   R2 SERVICE  full   (unavail=100) 30h
#   R3 PLANNED  full   (unavail=100) 20h
#   R4 FORCED   partial(unavail= 50) 10h
_PERIOD_HOURS = 100.0
_INSTALLED = 100.0


def _primary() -> OutageDataset:
    return OutageDataset(
        (
            _rec(outage_type=OutageType.FORCED, unavailable=100.0, hours=10.0),
            _rec(outage_type=OutageType.SERVICE, unavailable=100.0, hours=30.0),
            _rec(outage_type=OutageType.PLANNED, unavailable=100.0, hours=20.0),
            _rec(outage_type=OutageType.FORCED, unavailable=50.0, hours=10.0),
        )
    )


class TestEnums:
    def test_outage_type_members_distinct(self) -> None:
        values = {t.value for t in OutageType}
        assert values == {"planned", "forced", "unplanned", "maintenance", "service"}

    def test_outage_status_members(self) -> None:
        values = {s.value for s in OutageStatus}
        assert values == {"announced", "active", "revised", "cancelled", "completed"}


class TestRecordValidation:
    def test_valid_record_constructs(self) -> None:
        rec = _rec(installed=100.0, unavailable=40.0)
        assert rec.available_capacity_mw == pytest.approx(60.0)

    def test_available_within_tolerance_accepted(self) -> None:
        # available differs from installed-unavailable by < _CAPACITY_TOL -> accepted.
        rec = _rec(installed=100.0, unavailable=40.0, available=60.0 + 1e-9)
        assert rec.unavailable_capacity_mw == 40.0

    def test_invariant_violation_names_available(self) -> None:
        with pytest.raises(ValidationError, match="available_capacity_mw"):
            _rec(installed=100.0, unavailable=40.0, available=55.0)

    def test_unavailable_exceeds_installed_names_unavailable(self) -> None:
        with pytest.raises(ValidationError, match="unavailable_capacity_mw"):
            _rec(installed=100.0, unavailable=120.0, available=-20.0)

    def test_negative_unavailable_names_unavailable(self) -> None:
        with pytest.raises(ValidationError, match="unavailable_capacity_mw"):
            _rec(installed=100.0, unavailable=-1.0, available=101.0)

    def test_non_positive_installed_names_installed(self) -> None:
        with pytest.raises(ValidationError, match="installed_capacity_mw"):
            _rec(installed=0.0, unavailable=0.0, available=0.0)

    def test_negative_revision_names_revision(self) -> None:
        with pytest.raises(ValidationError, match="revision_number"):
            _rec(revision_number=-1)

    def test_expected_end_before_start_names_expected_end(self) -> None:
        with pytest.raises(ValidationError, match="expected_end_time"):
            _rec(hours=-5.0)

    def test_actual_end_before_start_names_actual_end(self) -> None:
        with pytest.raises(ValidationError, match="actual_end_time"):
            _rec(hours=10.0, actual_end=_START - timedelta(hours=1))


class TestRecordProperties:
    def test_duration_uses_actual_end_when_present(self) -> None:
        rec = _rec(hours=10.0, actual_end=_START + timedelta(hours=4))
        assert rec.duration_hours == pytest.approx(4.0)
        assert rec.effective_end_time == _START + timedelta(hours=4)

    def test_duration_falls_back_to_expected_end(self) -> None:
        rec = _rec(hours=7.5)
        assert rec.duration_hours == pytest.approx(7.5)

    def test_is_forced_only_for_forced_type(self) -> None:
        assert _rec(outage_type=OutageType.FORCED).is_forced is True
        assert _rec(outage_type=OutageType.UNPLANNED).is_forced is False
        assert _rec(outage_type=OutageType.PLANNED).is_forced is False

    def test_is_partial_and_is_full(self) -> None:
        partial = _rec(installed=100.0, unavailable=40.0)
        full = _rec(installed=100.0, unavailable=100.0)
        assert partial.is_partial is True
        assert partial.is_full_outage is False
        assert full.is_partial is False
        assert full.is_full_outage is True


class TestDatasetCollection:
    def test_len_and_iteration(self) -> None:
        ds = _primary()
        assert len(ds) == 4
        assert next(iter(ds)).outage_type is OutageType.FORCED

    def test_indexing(self) -> None:
        ds = _primary()
        assert ds[1].outage_type is OutageType.SERVICE

    def test_constructed_from_list_is_tuple_and_immutable(self) -> None:
        records = [_rec(hours=5.0)]
        ds = OutageDataset(records)  # type: ignore[arg-type]
        assert isinstance(ds.records, tuple)
        records.append(_rec(hours=1.0))  # mutating the source must not affect the dataset
        assert len(ds) == 1

    def test_empty_dataset_valid(self) -> None:
        ds = OutageDataset(())
        assert len(ds) == 0


class TestHeadlineKPIs:
    def test_availability_factor(self) -> None:
        # full outage hours = 10 + 30 + 20 = 60 (R4 is partial -> unit still available)
        assert availability_factor(_primary(), _PERIOD_HOURS) == pytest.approx(0.40)

    def test_unavailable_energy(self) -> None:
        # 100*10 + 100*30 + 100*20 + 50*10 = 6500 MWh
        assert unavailable_energy(_primary()) == pytest.approx(6500.0)

    def test_equivalent_availability_factor(self) -> None:
        # EAF = 1 - 6500 / (100 * 100) = 0.35
        assert equivalent_availability_factor(
            _primary(), _PERIOD_HOURS, _INSTALLED
        ) == pytest.approx(0.35)

    def test_forced_outage_rate(self) -> None:
        # forced hours = 20 (R1+R4), service hours = 30 -> 20/50 = 0.40
        assert forced_outage_rate(_primary()) == pytest.approx(0.40)


class TestExtendedKPIs:
    def test_efor(self) -> None:
        # forced equiv hours = 1.0*10 + 0.5*10 = 15; service = 30 -> 15/45
        assert efor(_primary()) == pytest.approx(15.0 / 45.0)

    def test_efor_le_for(self) -> None:
        ds = _primary()
        assert efor(ds) <= forced_outage_rate(ds)

    def test_mttr(self) -> None:
        # forced hours 20 / 2 forced events = 10.0 h
        assert mttr(_primary()) == pytest.approx(10.0)

    def test_mtbf(self) -> None:
        # period 100 / 2 forced events = 50.0 h
        assert mtbf(_primary(), _PERIOD_HOURS) == pytest.approx(50.0)

    def test_outage_frequency(self) -> None:
        # 2 events * 8760 / 100 = 175.2 per year
        assert outage_frequency(_primary(), _PERIOD_HOURS) == pytest.approx(175.2)

    def test_mtbf_frequency_consistency(self) -> None:
        ds = _primary()
        assert outage_frequency(ds, _PERIOD_HOURS) == pytest.approx(
            HOURS_PER_YEAR / mtbf(ds, _PERIOD_HOURS)
        )

    def test_outage_frequency_default_hours_per_year_matches_constant(self) -> None:
        ds = _primary()
        assert outage_frequency(ds, _PERIOD_HOURS) == outage_frequency(
            ds, _PERIOD_HOURS, hours_per_year=HOURS_PER_YEAR
        )

    def test_outage_frequency_custom_hours_per_year_changes_result(self) -> None:
        ds = _primary()
        # 2 events * 8784 (leap year) / 100 = 175.68 per year
        assert outage_frequency(ds, _PERIOD_HOURS, hours_per_year=8784.0) == pytest.approx(175.68)


class TestFactorBounds:
    """Property 73: AF, EAF, FOR all lie in [0, 1], even on degenerate/overlapping input."""

    def test_all_factors_in_unit_interval(self) -> None:
        ds = _primary()
        for value in (
            availability_factor(ds, _PERIOD_HOURS),
            equivalent_availability_factor(ds, _PERIOD_HOURS, _INSTALLED),
            forced_outage_rate(ds),
            efor(ds),
        ):
            assert 0.0 <= value <= 1.0

    def test_overlapping_outages_clamp_to_zero(self) -> None:
        # two full 80h forced outages in a 100h period -> raw 1 - 160/100 < 0, clamps to 0
        ds = OutageDataset(
            (
                _rec(outage_type=OutageType.FORCED, unavailable=100.0, hours=80.0),
                _rec(outage_type=OutageType.FORCED, unavailable=100.0, hours=80.0),
            )
        )
        assert availability_factor(ds, _PERIOD_HOURS) == 0.0
        assert equivalent_availability_factor(ds, _PERIOD_HOURS, _INSTALLED) == 0.0


class TestCategorySeparation:
    """Req 26.2 / Property 74: categories are never merged in type-filtering KPIs."""

    def test_planned_never_counts_in_forced_outage_rate(self) -> None:
        base = OutageDataset(
            (
                _rec(outage_type=OutageType.FORCED, unavailable=100.0, hours=10.0),
                _rec(outage_type=OutageType.SERVICE, unavailable=100.0, hours=30.0),
            )
        )
        planned = _rec(outage_type=OutageType.PLANNED, hours=20.0)
        with_planned = OutageDataset((*base.records, planned))
        # adding a planned outage leaves FOR unchanged (10 / 40 = 0.25)
        assert forced_outage_rate(base) == pytest.approx(0.25)
        assert forced_outage_rate(with_planned) == pytest.approx(0.25)

    def test_only_planned_gives_zero_forced_rate(self) -> None:
        ds = OutageDataset((_rec(outage_type=OutageType.PLANNED, unavailable=100.0, hours=50.0),))
        assert forced_outage_rate(ds) == 0.0
        assert efor(ds) == 0.0
        assert mttr(ds) == 0.0
        assert mtbf(ds, _PERIOD_HOURS) == float("inf")
        assert outage_frequency(ds, _PERIOD_HOURS) == 0.0

    def test_unplanned_and_forced_are_distinct(self) -> None:
        # An unplanned outage is not forced and must not enter forced-type KPIs.
        ds = OutageDataset((_rec(outage_type=OutageType.UNPLANNED, unavailable=100.0, hours=40.0),))
        assert forced_outage_rate(ds) == 0.0
        assert mttr(ds) == 0.0


class TestDispatchSeam:
    def test_forced_outage_multiplier_value(self) -> None:
        # forced energy = 100*10 + 50*10 = 1500; M = 1 - 1500/(100*100) = 0.85
        assert _primary().forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == pytest.approx(0.85)

    def test_multiplier_in_unit_interval(self) -> None:
        m = _primary().forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED)
        assert 0.0 <= m <= 1.0

    def test_multiplier_ignores_non_forced(self) -> None:
        # only planned/service/maintenance -> no forced derating -> M = 1
        ds = OutageDataset(
            (
                _rec(outage_type=OutageType.PLANNED, unavailable=100.0, hours=40.0),
                _rec(outage_type=OutageType.SERVICE, unavailable=100.0, hours=40.0),
            )
        )
        assert ds.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == 1.0


class TestStatusTreatment:
    """Regression tests for the outages.py:240 bug: ``status`` was never consulted, so
    ``CANCELLED`` outages fully derated availability just like real ones. §22.2 lifecycle:
    a ``CANCELLED`` record never happened and must be excluded from every KPI and the
    forced-outage multiplier; ``ANNOUNCED``/``ACTIVE``/``REVISED``/``COMPLETED`` all count."""

    def test_active_and_cancelled_forced_outage_now_differ(self) -> None:
        active = OutageDataset(
            (
                _rec(
                    outage_type=OutageType.FORCED,
                    unavailable=100.0,
                    hours=10.0,
                    status=OutageStatus.ACTIVE,
                ),
            )
        )
        cancelled = OutageDataset(
            (
                _rec(
                    outage_type=OutageType.FORCED,
                    unavailable=100.0,
                    hours=10.0,
                    status=OutageStatus.CANCELLED,
                ),
            )
        )
        # Before the fix these were byte-identical; the cancelled outage must now be a no-op.
        assert availability_factor(active, _PERIOD_HOURS) != availability_factor(
            cancelled, _PERIOD_HOURS
        )
        assert availability_factor(cancelled, _PERIOD_HOURS) == 1.0
        assert forced_outage_rate(cancelled) == 0.0
        assert efor(cancelled) == 0.0
        assert mttr(cancelled) == 0.0
        assert mtbf(cancelled, _PERIOD_HOURS) == float("inf")
        assert outage_frequency(cancelled, _PERIOD_HOURS) == 0.0
        assert unavailable_energy(cancelled) == 0.0
        assert cancelled.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == 1.0

    def test_cancelled_only_dataset_gives_full_availability_and_multiplier(self) -> None:
        ds = OutageDataset(
            (
                _rec(
                    outage_type=OutageType.FORCED,
                    unavailable=100.0,
                    hours=50.0,
                    status=OutageStatus.CANCELLED,
                ),
                _rec(
                    outage_type=OutageType.SERVICE,
                    unavailable=100.0,
                    hours=30.0,
                    status=OutageStatus.CANCELLED,
                ),
            )
        )
        assert availability_factor(ds, _PERIOD_HOURS) == 1.0
        assert equivalent_availability_factor(ds, _PERIOD_HOURS, _INSTALLED) == 1.0
        assert forced_outage_rate(ds) == 0.0
        assert ds.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == 1.0

    def test_cancelled_outage_excluded_but_others_still_counted(self) -> None:
        # Same shape as _primary() but with an extra CANCELLED forced outage that must be a
        # complete no-op alongside the real records.
        base = _primary()
        with_cancelled = OutageDataset(
            (
                *base.records,
                _rec(
                    outage_type=OutageType.FORCED,
                    unavailable=100.0,
                    hours=99.0,
                    status=OutageStatus.CANCELLED,
                ),
            )
        )
        assert availability_factor(with_cancelled, _PERIOD_HOURS) == pytest.approx(
            availability_factor(base, _PERIOD_HOURS)
        )
        assert forced_outage_rate(with_cancelled) == pytest.approx(forced_outage_rate(base))
        assert efor(with_cancelled) == pytest.approx(efor(base))
        assert mttr(with_cancelled) == pytest.approx(mttr(base))
        assert mtbf(with_cancelled, _PERIOD_HOURS) == pytest.approx(mtbf(base, _PERIOD_HOURS))
        assert outage_frequency(with_cancelled, _PERIOD_HOURS) == pytest.approx(
            outage_frequency(base, _PERIOD_HOURS)
        )
        assert unavailable_energy(with_cancelled) == pytest.approx(unavailable_energy(base))
        assert with_cancelled.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == pytest.approx(
            base.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED)
        )

    @pytest.mark.parametrize(
        "status",
        [OutageStatus.ANNOUNCED, OutageStatus.ACTIVE, OutageStatus.REVISED, OutageStatus.COMPLETED],
    )
    def test_non_cancelled_statuses_all_count_identically(self, status: OutageStatus) -> None:
        ds = OutageDataset(
            (_rec(outage_type=OutageType.FORCED, unavailable=100.0, hours=10.0, status=status),)
        )
        reference = OutageDataset(
            (
                _rec(
                    outage_type=OutageType.FORCED,
                    unavailable=100.0,
                    hours=10.0,
                    status=OutageStatus.COMPLETED,
                ),
            )
        )
        assert availability_factor(ds, _PERIOD_HOURS) == availability_factor(
            reference, _PERIOD_HOURS
        )
        assert ds.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == pytest.approx(
            reference.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED)
        )


class TestEmptyDataset:
    def test_kpis_on_empty_dataset(self) -> None:
        ds = OutageDataset(())
        assert availability_factor(ds, _PERIOD_HOURS) == 1.0
        assert equivalent_availability_factor(ds, _PERIOD_HOURS, _INSTALLED) == 1.0
        assert forced_outage_rate(ds) == 0.0
        assert efor(ds) == 0.0
        assert mttr(ds) == 0.0
        assert mtbf(ds, _PERIOD_HOURS) == float("inf")
        assert outage_frequency(ds, _PERIOD_HOURS) == 0.0
        assert unavailable_energy(ds) == 0.0
        assert ds.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == 1.0


class TestGuards:
    """Req 26.5 / Property 74: period_hours <= 0 or installed <= 0 raise before compute."""

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_non_positive_period_hours_raises(self, bad: float) -> None:
        ds = _primary()
        with pytest.raises(ValidationError, match="period_hours"):
            availability_factor(ds, bad)
        with pytest.raises(ValidationError, match="period_hours"):
            equivalent_availability_factor(ds, bad, _INSTALLED)
        with pytest.raises(ValidationError, match="period_hours"):
            mtbf(ds, bad)
        with pytest.raises(ValidationError, match="period_hours"):
            outage_frequency(ds, bad)
        with pytest.raises(ValidationError, match="period_hours"):
            ds.forced_outage_multiplier(bad, _INSTALLED)

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_non_positive_hours_per_year_raises(self, bad: float) -> None:
        ds = _primary()
        with pytest.raises(ValidationError, match="hours_per_year"):
            outage_frequency(ds, _PERIOD_HOURS, hours_per_year=bad)

    @pytest.mark.parametrize("bad", [0.0, -5.0])
    def test_non_positive_installed_raises(self, bad: float) -> None:
        ds = _primary()
        with pytest.raises(ValidationError, match="installed_capacity_mw"):
            equivalent_availability_factor(ds, _PERIOD_HOURS, bad)
        with pytest.raises(ValidationError, match="installed_capacity_mw"):
            ds.forced_outage_multiplier(_PERIOD_HOURS, bad)


class TestImmutabilityAndDeterminism:
    def test_record_is_frozen(self) -> None:
        rec = _rec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            rec.unavailable_capacity_mw = 1.0  # type: ignore[misc]

    def test_dataset_is_frozen(self) -> None:
        ds = _primary()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ds.records = ()  # type: ignore[misc]

    def test_kpis_are_deterministic(self) -> None:
        ds = _primary()
        assert availability_factor(ds, _PERIOD_HOURS) == availability_factor(ds, _PERIOD_HOURS)
        assert forced_outage_rate(ds) == forced_outage_rate(ds)
        assert efor(ds) == efor(ds)
        assert unavailable_energy(ds) == unavailable_energy(ds)
        assert ds.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED) == (
            ds.forced_outage_multiplier(_PERIOD_HOURS, _INSTALLED)
        )
