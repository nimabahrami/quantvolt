"""Named stress-scenario catalogue (Task 39, Req 9.4 / 9.7).

A :class:`ScenarioShock` is a named vector of *relative* price shocks and
:class:`ScenarioCatalogue` resolves scenario names to shocks, merging
caller-supplied scenarios over the module-level :data:`BUILT_IN_SCENARIOS`
registry (caller entries win) — the same Adapter seam as
:data:`quantvolt.models.commodity.BUILT_IN_COMMODITIES`.

Shock-key convention
--------------------
Shocks are keyed by ``(commodity_id, period)``:

* ``period`` is a :class:`~quantvolt.models.schedule.DeliveryPeriod` — the
  shock targets only that single (commodity, delivery month) exposure; or
* ``period`` is ``None`` — the shock applies commodity-wide, i.e. to every
  delivery period of that commodity.

All built-in macro scenarios are commodity-wide (``period=None``).

Shock-unit convention
---------------------
Shock values are *relative fractional* moves: ``+2.5`` means +250 % (a price
``P`` becomes ``P * (1 + 2.5)``) and ``-0.4`` means -40 %. ``RiskEngine.apply_scenario``
applies them to delta P&L as ``delta * reference_price * shock``, where
``reference_price`` is read from the position's
``PricedPosition.reference_prices`` (populated by every built-in
:mod:`quantvolt.portfolio.valuation` pricer) — see
:mod:`quantvolt.risk.engine`'s module docstring for the full convention,
including the ``reference_price = 1.0`` fallback for positions that never
set it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .._validation import require_non_empty
from ..exceptions import ScenarioNotFoundError
from ..models.schedule import DeliveryPeriod

ShockKey: TypeAlias = tuple[str, DeliveryPeriod | None]
"""``(commodity_id, period)`` — ``period=None`` means the shock is commodity-wide."""


@dataclass(frozen=True, slots=True)
class ScenarioShock:
    """A named vector of relative price shocks.

    ``shocks`` maps ``(commodity_id, period)`` to a relative fractional shock
    (see the module docstring for both conventions). ``period=None`` applies
    the shock commodity-wide across all delivery periods.
    """

    name: str
    shocks: dict[ShockKey, float]

    def __post_init__(self) -> None:
        require_non_empty("name", self.name)
        require_non_empty("shocks", self.shocks)


def _commodity_wide(shocks_by_id: dict[str, float]) -> dict[ShockKey, float]:
    """Lift per-commodity shocks onto the ``(commodity_id, period=None)`` key convention."""
    return {(commodity_id, None): shock for commodity_id, shock in shocks_by_id.items()}


def _flat(commodity_ids: tuple[str, ...], shock: float) -> dict[str, float]:
    """The same relative shock for every commodity id in ``commodity_ids``."""
    return dict.fromkeys(commodity_ids, shock)


# Commodity ids from quantvolt.models.commodity.BUILT_IN_COMMODITIES, grouped
# by asset class so macro scenarios shock whole classes consistently.
_POWER_IDS: tuple[str, ...] = (
    "EEX_PHELIX_DE",
    "EEX_PHELIX_AT",
    "EPEX_DE",
    "EPEX_FR",
    "EPEX_NL",
    "EPEX_BE",
    "EPEX_GB",
)
_GAS_IDS: tuple[str, ...] = ("TTF", "NBP")


# Default scenario registry (Req 9.4). A module-level constant — NOT a
# Singleton and never mutated; extensions merge over it via ScenarioCatalogue.
#
# Shock magnitudes are STYLISED, historically-motivated round numbers for
# stress testing — they are not calibrated to any dataset. Each factory
# function below documents its own historical motivation and exposes its
# shock magnitudes as caller-overridable keyword parameters (Simple Factory,
# coding-style.md section 2); BUILT_IN_SCENARIOS is built by calling each
# factory at its documented defaults, so the registry is unchanged.


def gas_crisis(
    *,
    ttf_shock: float = 3.0,
    nbp_shock: float = 2.5,
    german_power_shock: float = 2.0,
    eua_shock: float = 0.3,
) -> ScenarioShock:
    """ "European Gas Crisis 2022" stress scenario.

    TTF front-month rose from roughly EUR 70-80/MWh in early 2022 to a
    ~EUR 340/MWh peak (Aug 2022), i.e. roughly +300 %; NBP followed slightly
    less tightly; German power followed gas via the merit order; EUA carbon
    drifted up far more modestly. Each shock is a caller-overridable relative
    fractional move (see the module docstring's shock-unit convention); the
    defaults reproduce the documented historical scenario exactly.
    """
    return ScenarioShock(
        name="European Gas Crisis 2022",
        shocks=_commodity_wide(
            {
                "TTF": ttf_shock,
                "NBP": nbp_shock,
                "EEX_PHELIX_DE": german_power_shock,
                "EUA": eua_shock,
            }
        ),
    )


def cold_snap_winter(*, gas_shock: float = 1.0, power_shock: float = 0.8) -> ScenarioShock:
    """ "Cold Snap Winter" stress scenario.

    A sustained 1-in-20 cold spell: gas roughly doubles on heating demand and
    storage draw; power follows at a slightly smaller relative move (gas sets
    the marginal price but not in every hour). ``gas_shock`` / ``power_shock``
    apply uniformly to every gas / power commodity id (see :data:`_GAS_IDS` /
    :data:`_POWER_IDS`); the defaults reproduce the documented historical
    scenario exactly.
    """
    return ScenarioShock(
        name="Cold Snap Winter",
        shocks=_commodity_wide({**_flat(_GAS_IDS, gas_shock), **_flat(_POWER_IDS, power_shock)}),
    )


def mild_winter_demand_slump(
    *, gas_shock: float = -0.4, power_shock: float = -0.3
) -> ScenarioShock:
    """ "Mild Winter Demand Slump" stress scenario.

    The mirror-image demand shock to :func:`cold_snap_winter`: weak heating
    demand and full storage depress gas, dragging power down with it. Both
    shocks apply uniformly across the gas / power commodity ids; the defaults
    reproduce the documented historical scenario exactly.
    """
    return ScenarioShock(
        name="Mild Winter Demand Slump",
        shocks=_commodity_wide({**_flat(_GAS_IDS, gas_shock), **_flat(_POWER_IDS, power_shock)}),
    )


def carbon_price_shock(*, eua_shock: float = 1.0, power_shock: float = 0.25) -> ScenarioShock:
    """ "Carbon Price Shock" stress scenario.

    EUA doubles (policy tightening); fossil marginal costs pass through to
    power at a fraction of the relative carbon move. ``power_shock`` applies
    uniformly across the power commodity ids; the defaults reproduce the
    documented historical scenario exactly.
    """
    return ScenarioShock(
        name="Carbon Price Shock",
        shocks=_commodity_wide({"EUA": eua_shock, **_flat(_POWER_IDS, power_shock)}),
    )


BUILT_IN_SCENARIOS: dict[str, ScenarioShock] = {
    scenario.name: scenario
    for scenario in (
        gas_crisis(),
        cold_snap_winter(),
        mild_winter_demand_slump(),
        carbon_price_shock(),
    )
}


class ScenarioCatalogue:
    """Resolves scenario names to :class:`ScenarioShock` vectors.

    A config-holding service over :data:`BUILT_IN_SCENARIOS` — not a Singleton.
    Caller-supplied ``extra_scenarios`` are merged OVER the built-ins (caller
    wins on name collision); neither input dict is mutated, and later mutation
    of ``extra_scenarios`` by the caller does not affect the catalogue.
    """

    def __init__(self, extra_scenarios: dict[str, ScenarioShock] | None = None) -> None:
        merged = dict(BUILT_IN_SCENARIOS)
        if extra_scenarios is not None:
            merged.update(extra_scenarios)
        self._scenarios: dict[str, ScenarioShock] = merged

    def get(self, name: str) -> ScenarioShock:
        """Return the scenario registered under ``name``.

        Raises :class:`ScenarioNotFoundError` naming the unrecognised scenario
        and listing the available scenario names (sorted) when no match exists.
        """
        try:
            return self._scenarios[name]
        except KeyError:
            available = ", ".join(sorted(self._scenarios))
            raise ScenarioNotFoundError(
                f"scenario name {name!r} is not in the scenario catalogue; "
                f"available scenarios: {available}"
            ) from None

    def names(self) -> list[str]:
        """All available scenario names, sorted."""
        return sorted(self._scenarios)
