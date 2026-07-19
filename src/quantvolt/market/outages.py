"""Outage data & reliability KPIs.

Pure computation: the caller supplies a validated ``OutageDataset`` and the
period context (``period_hours``, ``installed_capacity_mw``); the library returns
reliability KPIs. No fetching, I/O, or persistence.

Sources of mathematical truth
-----------------------------
- Record schema and the three headline KPIs (``Availability Factor`` /
  ``Equivalent Availability Factor`` / ``Forced Outage Rate``).
- The remaining KPIs (``efor``, ``mtbf``, ``mttr``, ``outage_frequency``,
  ``unavailable_energy``) follow IEEE Std 762 (IEEE Standard Definitions for Use
  in Reporting Electric Generating Unit Reliability, Availability, and
  Productivity), adapted to this library's category-based hour partition.

Correctness properties
-----------------------
- ``AF``, ``EAF``, ``FOR`` equal their documented definitions and lie in
  ``[0, 1]``; ``FOR = forced / (forced + service)``.
- Record invariant ``available = installed - unavailable`` within
  tolerance and ``0 <= unavailable <= installed``; planned/forced/unplanned/
  service categories are never merged; ``period_hours <= 0`` or
  ``installed <= 0`` raise.

Category separation
--------------------
``OutageType`` keeps ``PLANNED``, ``FORCED``, ``UNPLANNED``, ``MAINTENANCE``
and ``SERVICE`` distinct. Every KPI that filters by type does so explicitly, so a
planned outage never contributes to ``forced_outage_rate`` and the categories
are never silently merged.

Status treatment
-----------------
``OutageStatus`` is consulted by every KPI and by
``OutageDataset.forced_outage_multiplier``, exactly as explicitly as type filtering
above: a record whose ``status`` is ``CANCELLED`` never happened and is excluded from
every hour/energy aggregation (it contributes to none of ``availability_factor``,
``equivalent_availability_factor``, ``forced_outage_rate``, ``efor``, ``mtbf``, ``mttr``,
``outage_frequency``, ``unavailable_energy``, or ``forced_outage_multiplier``).
``ANNOUNCED``, ``ACTIVE``, ``REVISED``, and ``COMPLETED`` all count: an outage that was
announced, is in progress, has been revised, or has completed is a real event regardless
of which of those four lifecycle stages it is currently in.

Dispatch seam
-------------
``OutageDataset.forced_outage_multiplier`` derives the per-period available-
capacity fraction attributable to forced outages. This is the value a stochastic
dispatch optimizer (``assets/dispatch``) consumes as its forced-outage
multiplier ``M`` applied to available capacity ``c_max``; it maps to the plant's
stochastic forced-outage rate ``λ``. See the method docstring.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .._validation import require_non_negative, require_positive
from ..exceptions import ValidationError

# Capacity comparisons use MW; a small absolute tolerance absorbs float round-off in the
# record invariant available = installed - unavailable and in full-vs-partial classification.
_CAPACITY_TOL = 1e-6

# Reference hours in a (non-leap) year, used to annualize outage_frequency (events/year).
HOURS_PER_YEAR = 8760.0


class OutageType(StrEnum):
    """Outage category. Planned, forced, unplanned, and service events stay
    distinct and are never silently merged."""

    PLANNED = "planned"
    FORCED = "forced"
    UNPLANNED = "unplanned"
    MAINTENANCE = "maintenance"
    SERVICE = "service"


class OutageStatus(StrEnum):
    """Outage lifecycle status."""

    ANNOUNCED = "announced"
    ACTIVE = "active"
    REVISED = "revised"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class OutageRecord:
    """A single outage event, as an immutable value object.

    Capacity invariant, validated at construction:

    - ``0 <= unavailable_capacity_mw <= installed_capacity_mw``;
    - ``available_capacity_mw == installed_capacity_mw - unavailable_capacity_mw`` within
      ``_CAPACITY_TOL``.

    Violations raise ``ValidationError`` naming the offending field.
    ``installed_capacity_mw`` must be strictly positive (a generating unit has
    capacity; this also keeps the per-record derating fraction ``unavailable/installed``
    well defined). End times must not precede ``start_time`` so ``duration_hours``
    is non-negative.

    ``is_partial`` and ``is_forced`` are exposed as derived properties so they can
    never contradict the stored capacities/type.
    """

    asset_id: str
    unit_id: str
    technology: str
    market_zone: str
    outage_id: str
    outage_type: OutageType
    status: OutageStatus
    announcement_time: datetime
    start_time: datetime
    expected_end_time: datetime
    installed_capacity_mw: float
    unavailable_capacity_mw: float
    available_capacity_mw: float
    source: str
    revision_number: int
    actual_end_time: datetime | None = None
    reason_code: str | None = None
    reason_text: str | None = None

    def __post_init__(self) -> None:
        require_positive("installed_capacity_mw", self.installed_capacity_mw)
        require_non_negative("unavailable_capacity_mw", self.unavailable_capacity_mw)
        require_non_negative("revision_number", self.revision_number)
        if self.unavailable_capacity_mw > self.installed_capacity_mw + _CAPACITY_TOL:
            raise ValidationError(
                "unavailable_capacity_mw must satisfy 0 <= unavailable <= installed, got "
                f"unavailable_capacity_mw={self.unavailable_capacity_mw!r} > "
                f"installed_capacity_mw={self.installed_capacity_mw!r}"
            )
        expected_available = self.installed_capacity_mw - self.unavailable_capacity_mw
        if abs(self.available_capacity_mw - expected_available) > _CAPACITY_TOL:
            raise ValidationError(
                "available_capacity_mw must equal installed - unavailable within "
                f"{_CAPACITY_TOL}, got available_capacity_mw={self.available_capacity_mw!r}, "
                f"expected {expected_available!r} "
                f"(installed={self.installed_capacity_mw!r}, "
                f"unavailable={self.unavailable_capacity_mw!r})"
            )
        if self.expected_end_time < self.start_time:
            raise ValidationError(
                "expected_end_time must not precede start_time, got "
                f"expected_end_time={self.expected_end_time!r} < "
                f"start_time={self.start_time!r}"
            )
        if self.actual_end_time is not None and self.actual_end_time < self.start_time:
            raise ValidationError(
                "actual_end_time must not precede start_time, got "
                f"actual_end_time={self.actual_end_time!r} < start_time={self.start_time!r}"
            )

    @property
    def effective_end_time(self) -> datetime:
        """Realised end when known (``actual_end_time``), else the ``expected_end_time``."""
        return self.actual_end_time if self.actual_end_time is not None else self.expected_end_time

    @property
    def duration_hours(self) -> float:
        """Outage length in hours, ``effective_end_time - start_time``. Non-negative."""
        return (self.effective_end_time - self.start_time).total_seconds() / 3600.0

    @property
    def is_full_outage(self) -> bool:
        """True when essentially all installed capacity is unavailable (full outage)."""
        return self.unavailable_capacity_mw >= self.installed_capacity_mw - _CAPACITY_TOL

    @property
    def is_partial(self) -> bool:
        """True for a derating: some but not all capacity unavailable."""
        return (
            _CAPACITY_TOL
            < self.unavailable_capacity_mw
            < (self.installed_capacity_mw - _CAPACITY_TOL)
        )

    @property
    def is_forced(self) -> bool:
        """True iff this is a ``FORCED`` outage; other categories
        (unplanned, planned, maintenance, service) are kept distinct."""
        return self.outage_type is OutageType.FORCED


@dataclass(frozen=True, slots=True)
class OutageDataset:
    """An immutable, iterable collection of ``OutageRecord``.

    Records are snapshot into a tuple at construction, so the dataset is immutable even
    if the caller passes a list and later mutates it. Each record self-validates, so a
    constructed dataset holds only valid records. An empty dataset is valid: it denotes a
    period with no outages (fully available).

    KPI functions treat the dataset as a single reliability context: one unit, or an
    aggregate the caller has already scoped to a common ``installed_capacity_mw`` and
    ``period_hours``. Records are assumed non-overlapping in time; the factor KPIs clamp
    to ``[0, 1]`` so overlapping or over-period inputs still stay well formed.
    """

    records: tuple[OutageRecord, ...]

    def __post_init__(self) -> None:
        # Coerce any iterable of records to an immutable tuple (defensive snapshot).
        object.__setattr__(self, "records", tuple(self.records))

    def __iter__(self) -> Iterator[OutageRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> OutageRecord:
        return self.records[index]

    def forced_outage_multiplier(self, period_hours: float, installed_capacity_mw: float) -> float:
        """Per-period available-capacity fraction attributable to forced outages ∈ ``[0, 1]``.

        This is the dispatch seam: a stochastic dispatch optimizer applies the returned
        value as its forced-outage multiplier ``M`` to available capacity ``c_max``. Only
        ``FORCED`` events count; they map to the plant's stochastic forced-outage rate
        ``λ``. Planned/maintenance outages are scheduled deterministically, and
        unplanned/service events are tracked by their own KPIs; none of them enter ``M``
        here, preserving category separation.

        ``M = 1 - forced_unavailable_energy / (installed_capacity_mw * period_hours)``, where
        ``forced_unavailable_energy = Σ unavailable_capacity_mw * duration_hours`` over
        ``FORCED`` records (MWh). Clamped to ``[0, 1]``. ``CANCELLED`` records are excluded
        (a cancelled outage never happened, so it never derates ``M``); every other status
        (``ANNOUNCED``/``ACTIVE``/``REVISED``/``COMPLETED``) counts.

        Args:
            period_hours: Length of the dispatch period in hours. Must be ``> 0``.
            installed_capacity_mw: Installed capacity of the dispatch context. Must be ``> 0``.

        Returns:
            The available fraction ``M`` in ``[0, 1]`` (``1.0`` means no forced derating).

        Raises:
            ValidationError: If ``period_hours <= 0`` or ``installed_capacity_mw <= 0``.
        """
        require_positive("period_hours", period_hours)
        require_positive("installed_capacity_mw", installed_capacity_mw)
        forced_energy = sum(
            r.unavailable_capacity_mw * r.duration_hours for r in _active(self) if r.is_forced
        )
        return _clamp01(1.0 - forced_energy / (installed_capacity_mw * period_hours))


# --------------------------------------------------------------------------------------
# Internal hour/energy aggregations (all read-only over the dataset).
# --------------------------------------------------------------------------------------


def _clamp01(value: float) -> float:
    """Clamp to ``[0, 1]`` so the factor KPIs stay well formed on any input."""
    return min(1.0, max(0.0, value))


def _active(dataset: OutageDataset) -> tuple[OutageRecord, ...]:
    """Records excluding ``CANCELLED`` ones: a cancelled outage never happened, so
    it is excluded from every KPI and the forced-outage multiplier."""
    return tuple(r for r in dataset.records if r.status is not OutageStatus.CANCELLED)


def _hours_of_type(dataset: OutageDataset, outage_type: OutageType) -> float:
    """Total clock hours of non-``CANCELLED`` records of exactly ``outage_type`` (categories
    kept distinct)."""
    return sum(r.duration_hours for r in _active(dataset) if r.outage_type is outage_type)


def _full_outage_hours(dataset: OutageDataset) -> float:
    """Clock hours during which a unit is fully unavailable, across all outage types.

    Partial (derated) outages leave the unit available (running derated), so they do not
    reduce time-based availability; only full outages do (captured by the AF definition).
    ``CANCELLED`` records are excluded.
    """
    return sum(r.duration_hours for r in _active(dataset) if r.is_full_outage)


def _forced_equivalent_hours(dataset: OutageDataset) -> float:
    """Equivalent forced-outage hours: each forced record weighted by its unavailable
    fraction ``unavailable/installed`` (IEEE 762 equivalent-hours concept). A full forced
    outage contributes its whole duration; a partial forced outage contributes pro-rata.
    ``CANCELLED`` records are excluded."""
    return sum(
        (r.unavailable_capacity_mw / r.installed_capacity_mw) * r.duration_hours
        for r in _active(dataset)
        if r.is_forced
    )


def _count_forced(dataset: OutageDataset) -> int:
    """Number of non-``CANCELLED`` forced-outage events."""
    return sum(1 for r in _active(dataset) if r.is_forced)


# --------------------------------------------------------------------------------------
# Reliability KPIs.
# --------------------------------------------------------------------------------------


def availability_factor(dataset: OutageDataset, period_hours: float) -> float:
    """Availability Factor ``AF = available_hours / period_hours`` ∈ ``[0, 1]``.

    ``available_hours = period_hours - full_outage_hours``, where ``full_outage_hours`` sums
    the duration of every full outage (any type). Partial deratings leave the unit available
    and so do not reduce ``AF``; the equivalent (capacity-weighted) loss is captured by
    ``equivalent_availability_factor``. Clamped to ``[0, 1]``. ``CANCELLED``
    records are excluded (a cancelled outage never happened).

    Raises:
        ValidationError: If ``period_hours <= 0``.
    """
    require_positive("period_hours", period_hours)
    return _clamp01(1.0 - _full_outage_hours(dataset) / period_hours)


def equivalent_availability_factor(
    dataset: OutageDataset, period_hours: float, installed_capacity_mw: float
) -> float:
    """Equivalent Availability Factor ∈ ``[0, 1]``.

    ``EAF = 1 - equivalent_unavailable_capacity_hours / (installed_capacity * period_hours)``,
    where ``equivalent_unavailable_capacity_hours`` is ``unavailable_energy`` (MWh). Unlike
    ``availability_factor`` this credits partial deratings capacity-for-capacity. Clamped
    to ``[0, 1]``. ``CANCELLED`` records are excluded via ``unavailable_energy``.

    Raises:
        ValidationError: If ``period_hours <= 0`` or ``installed_capacity_mw <= 0``.
    """
    require_positive("period_hours", period_hours)
    require_positive("installed_capacity_mw", installed_capacity_mw)
    equivalent_unavailable = unavailable_energy(dataset)
    return _clamp01(1.0 - equivalent_unavailable / (installed_capacity_mw * period_hours))


def forced_outage_rate(dataset: OutageDataset) -> float:
    """Forced Outage Rate ``FOR = forced_hours / (forced_hours + service_hours)`` ∈ ``[0, 1]``.

    ``forced_hours`` sums the duration of ``FORCED`` outages;
    ``service_hours`` sums the duration of ``SERVICE`` outages. Categories stay distinct: a
    planned, unplanned, or maintenance outage never enters this KPI. ``CANCELLED`` records are
    excluded from both sums (a cancelled outage never happened). Returns
    ``0.0`` when there is neither forced nor service exposure (documented convention for the
    ``0/0`` case).
    """
    forced_hours = _hours_of_type(dataset, OutageType.FORCED)
    service_hours = _hours_of_type(dataset, OutageType.SERVICE)
    denominator = forced_hours + service_hours
    if denominator == 0.0:
        return 0.0
    return forced_hours / denominator


def efor(dataset: OutageDataset) -> float:
    """Equivalent Forced Outage Rate ∈ ``[0, 1]`` (IEEE 762).

    The capacity-equivalent analog of ``forced_outage_rate``: full forced-outage hours
    are replaced by equivalent forced-outage hours (each forced event weighted by its
    unavailable fraction ``unavailable/installed``), so a partial (derated) forced outage
    counts pro-rata rather than at full duration:

        ``EFOR = forced_equiv_hours / (forced_equiv_hours + service_hours)``.

    Because ``forced_equiv_hours <= forced_hours``, ``EFOR <= FOR``; it reduces to ``FOR``
    when every forced outage is a full outage. ``SERVICE`` events supply the denominator's
    service hours, keeping categories distinct. ``CANCELLED`` records
    are excluded from both terms. Returns ``0.0`` for the ``0/0`` case (no
    equivalent-forced and no service exposure).
    """
    forced_equiv = _forced_equivalent_hours(dataset)
    service_hours = _hours_of_type(dataset, OutageType.SERVICE)
    denominator = forced_equiv + service_hours
    if denominator == 0.0:
        return 0.0
    return forced_equiv / denominator


def mttr(dataset: OutageDataset) -> float:
    """Mean Time To Repair, in hours (IEEE 762).

    ``MTTR = forced_outage_hours / number_of_forced_outages``: the average length of a
    forced outage. ``CANCELLED`` records are excluded from both the hours and the count
    (a cancelled outage never happened). Returns ``0.0`` when there are no
    (non-cancelled) forced outages (no repair burden; documented convention).
    """
    n_forced = _count_forced(dataset)
    if n_forced == 0:
        return 0.0
    return _hours_of_type(dataset, OutageType.FORCED) / n_forced


def mtbf(dataset: OutageDataset, period_hours: float) -> float:
    """Mean Time Between Failures, in hours (IEEE 762).

    ``MTBF = period_hours / number_of_forced_outages``: the reciprocal of the forced-outage
    (failure) rate ``λ``, i.e. the mean observation time per forced outage. ``CANCELLED``
    records never count as a forced outage. Returns ``float('inf')`` when
    there are no (non-cancelled) forced outages (infinitely long expected time between
    failures). Consistent with ``outage_frequency``: ``outage_frequency = HOURS_PER_YEAR
    / MTBF``.

    Raises:
        ValidationError: If ``period_hours <= 0``.
    """
    require_positive("period_hours", period_hours)
    n_forced = _count_forced(dataset)
    if n_forced == 0:
        return float("inf")
    return period_hours / n_forced


def outage_frequency(
    dataset: OutageDataset, period_hours: float, *, hours_per_year: float = HOURS_PER_YEAR
) -> float:
    """Forced-outage frequency, annualized to events per year (IEEE 762).

    ``f = number_of_forced_outages * hours_per_year / period_hours``: the failure rate ``λ``
    expressed per year. ``CANCELLED`` records never count as a forced outage. Zero
    when there are no (non-cancelled) forced outages. Consistent with
    ``mtbf``: ``f = hours_per_year / MTBF``.

    Args:
        dataset: The outage dataset.
        period_hours: Length of the observation period in hours. Must be ``> 0``.
        hours_per_year: Reference hours used to annualize the frequency (default
            ``HOURS_PER_YEAR``, ``8760.0``, a non-leap year). Must be ``> 0``.

    Raises:
        ValidationError: If ``period_hours <= 0`` or ``hours_per_year <= 0``.
    """
    require_positive("period_hours", period_hours)
    require_positive("hours_per_year", hours_per_year)
    return _count_forced(dataset) * hours_per_year / period_hours


def unavailable_energy(dataset: OutageDataset) -> float:
    """Unavailable energy in MWh (IEEE 762 equivalent unavailable capacity-hours).

    ``Σ unavailable_capacity_mw * duration_hours`` over every non-``CANCELLED`` record
    (partial and full; a cancelled outage never happened). This is the
    ``equivalent_unavailable_capacity_hours`` term used by
    ``equivalent_availability_factor``. Non-negative.
    """
    return sum(r.unavailable_capacity_mw * r.duration_hours for r in _active(dataset))
