"""Validated price-unit value object and energy-unit conversion utilities (Req 1-5).

Introduces no new layer and no numerics kernel: unit conversion is deterministic
fixed-constant arithmetic. Everything here is a pure, immutable value object plus a
handful of pure functions — Layer 1 (``models/``) per the base-spec module tree.

``PriceUnit`` is the *validator and converter*; ``price_unit`` remains a plain ``str``
on :class:`quantvolt.models.commodity.Hub` / ``CommodityConfig` for backward
compatibility (see ``models/commodity.py``), validated via ``PriceUnit.parse`` in
``__post_init__``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .._validation import require_finite
from ..exceptions import ValidationError

# --- Energy-unit constants (single source of truth; see design References) ---
# Statutory therm = 29.3071 kWh (International Table Btu).
# source: ICE UK NBP Natural Gas Futures contract specification -- "1 therm = 29.3071
# kilowatt hours" (see docs/market_conventions.json, NBP entry, fetched 2026-07-18); cf.
# polished_energy_derivatives_modeling_specification.md:114-123 for the design rationale.
KWH_PER_THERM: float = 29.3071
MWH_PER_THERM: float = KWH_PER_THERM / 1000.0  # 0.0293071 MWh/therm
# 1 MMBtu = 1,000,000 Btu, 1 therm = 100,000 Btu -> exactly 10 therms/MMBtu.
# source: definitional unit identity (SI mega- prefix applied to the International Table
# Btu already sourced via KWH_PER_THERM above); not a market-specific convention, so no
# external market-quote citation applies -- see .kiro/steering/provenance.md on definitional
# constants.
THERMS_PER_MMBTU: float = 10.0
# Derived, NEVER re-literalled: 10 * 0.0293071 = 0.293071 MWh/MMBtu (agrees with source doc:119).
MWH_PER_MMBTU: float = THERMS_PER_MMBTU * MWH_PER_THERM
# source: definitional -- 1 GBP = 100 GBp (pence), UK decimal-currency subdivision; not a
# market-specific convention (cf. polished_energy_derivatives_modeling_specification.md:108-112).
PENCE_PER_POUND: float = 100.0

_ENERGY_DENOMINATORS = ("MWh", "therm", "MMBtu")
# Energy-inconvertible denominators (Requirement 7 follow-up / Task 14, deferred): each is a
# definitional trade unit with no fixed energy-content constant in this library -- converting
# it to/from an energy denominator would require a calorific/heat-content assumption that is
# contractual, not universal, so it is out of scope (mirrors the existing "tCO2" pattern).
# "bbl" = barrel (crude oil / refined products); "t" = metric tonne (e.g. API2 coal).
_INERT_DENOMINATORS = ("tCO2", "bbl", "t")
_ALL_DENOMINATORS = (*_ENERGY_DENOMINATORS, *_INERT_DENOMINATORS)

# MWh-per-<denominator> table; the single lookup every energy conversion routes through.
_MWH_PER: dict[str, float] = {
    "MWh": 1.0,
    "therm": MWH_PER_THERM,
    "MMBtu": MWH_PER_MMBTU,
}

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True, slots=True)
class PriceUnit:
    """A validated ``currency/denominator`` price unit (Req 1).

    ``currency`` is either three uppercase ASCII letters (ISO 4217, e.g. ``"EUR"``,
    ``"GBP"``, ``"USD"``) or the literal ``"GBp"`` (pence sterling). ``denominator``
    is one of ``{"MWh", "therm", "MMBtu", "tCO2", "bbl", "t"}``. ``"tCO2"`` (emissions),
    ``"bbl"`` (barrel, crude/refined products), and ``"t"`` (metric tonne, e.g. coal) are
    *energy-inconvertible*: they parse and round-trip like any other denominator, but
    :func:`convert_price` refuses to convert between them and an energy denominator (no
    calorific-value assumption is made).
    """

    currency: str
    denominator: str

    def __post_init__(self) -> None:
        if not (self.currency == "GBp" or _CURRENCY_RE.match(self.currency)):
            raise ValidationError(
                f"currency must be exactly three uppercase ASCII letters (e.g. 'EUR', "
                f"'GBP', 'USD') or the literal 'GBp' (pence sterling), got {self.currency!r}"
            )
        if self.denominator == "MBtu":
            raise ValidationError(
                "denominator 'MBtu' is not a recognised energy unit (did you mean MMBtu?); "
                f"recognised units: {_ALL_DENOMINATORS}"
            )
        if self.denominator not in _ALL_DENOMINATORS:
            raise ValidationError(
                f"denominator must be one of {_ALL_DENOMINATORS}, got {self.denominator!r}"
            )

    @classmethod
    def parse(cls, text: str) -> PriceUnit:
        """Parse ``"CCY/denominator"`` into a validated :class:`PriceUnit` (Req 2).

        Splits on a single ``/``; rejects strings with no ``/``, more than one ``/``,
        or empty currency/denominator parts, each raising :class:`ValidationError`
        naming ``text``. No whitespace normalisation is performed: the parts are used
        verbatim so ``str(PriceUnit.parse(text)) == text`` holds for any parseable
        ``text``.
        """
        parts = text.split("/")
        if len(parts) != 2:
            raise ValidationError(
                f"text must contain exactly one '/' separating currency and denominator, "
                f"got {text!r}"
            )
        currency, denominator = parts
        if not currency or not denominator:
            raise ValidationError(
                f"text must have non-empty currency and denominator parts, got {text!r}"
            )
        return cls(currency, denominator)

    def __str__(self) -> str:
        return f"{self.currency}/{self.denominator}"


def therms_to_mwh(value: float) -> float:
    """Convert an energy quantity from therm to MWh (Req 4)."""
    require_finite("value", value)
    return value * MWH_PER_THERM


def mwh_to_therms(value: float) -> float:
    """Convert an energy quantity from MWh to therm (Req 4)."""
    require_finite("value", value)
    return value / MWH_PER_THERM


def mmbtu_to_mwh(value: float) -> float:
    """Convert an energy quantity from MMBtu to MWh (Req 4)."""
    require_finite("value", value)
    return value * MWH_PER_MMBTU


def mwh_to_mmbtu(value: float) -> float:
    """Convert an energy quantity from MWh to MMBtu (Req 4)."""
    require_finite("value", value)
    return value / MWH_PER_MMBTU


# Minor-currency-unit table: {minor_currency: (major_currency, minor_units_per_major)}.
# Two currencies are convertible without an FX rate iff they resolve to the same major
# currency (a major currency resolves to itself); the conversion factor is then the ratio
# of their minor-unit scales, with a major currency's own scale defined as 1.0. Adding a
# future minor unit (e.g. "EURc", euro cents) is one new row here -- convert_price's control
# flow does not change.
_MINOR_UNITS: dict[str, tuple[str, float]] = {
    # source: definitional -- 1 GBP = 100 GBp (pence), UK decimal-currency subdivision; not a
    # market-specific convention (cf.
    # polished_energy_derivatives_modeling_specification.md:108-112).
    "GBp": ("GBP", PENCE_PER_POUND),
}


def _major_currency(currency: str) -> str:
    """The major currency ``currency`` resolves to (itself, unless a minor unit)."""
    major, _ = _MINOR_UNITS.get(currency, (currency, 1.0))
    return major


def _minor_scale(currency: str) -> float:
    """Minor-units-per-major-unit for ``currency`` (``1.0`` for a major currency itself)."""
    _, scale = _MINOR_UNITS.get(currency, (currency, 1.0))
    return scale


def convert_price(value: float, from_unit: PriceUnit | str, to_unit: PriceUnit | str) -> float:
    """Convert a *per-unit price* from ``from_unit`` to ``to_unit`` (Req 5).

    Same-currency energy-denominator conversion multiplies by the reciprocal of the
    quantity factor: a price per therm converted to per MWh is *divided* by
    ``MWH_PER_THERM`` (there are ~34 therms in an MWh, so the per-MWh price is ~34x
    larger). Two currencies that resolve to the same major currency (see
    ``_MINOR_UNITS``, e.g. ``GBp``/``GBP``) additionally scale by the ratio of their
    minor-unit scales. Cross-*major*-currency conversion raises :class:`ValidationError`.
    Any *energy-inconvertible* denominator (``"tCO2"``, ``"bbl"``, ``"t"``) paired with a
    different denominator also raises :class:`ValidationError`: these are definitional
    trade units with no fixed energy-content constant, so converting them to/from an
    energy denominator (or to a different inconvertible denominator) would require a
    calorific/heat-content assumption this function does not make.

    Units may be given as ``PriceUnit`` objects or as their string renderings
    (parsed via :meth:`PriceUnit.parse`, so a malformed string raises the same
    :class:`ValidationError` it would anywhere else).

    Worked example (Req 5.7): ``convert_price(85.0, "GBp/therm", "GBp/MWh")
    == 85.0 / MWH_PER_THERM ~= 2900.32`` GBp/MWh.
    """
    require_finite("value", value)
    if isinstance(from_unit, str):
        from_unit = PriceUnit.parse(from_unit)
    if isinstance(to_unit, str):
        to_unit = PriceUnit.parse(to_unit)

    same_currency = from_unit.currency == to_unit.currency
    if not same_currency and _major_currency(from_unit.currency) != _major_currency(
        to_unit.currency
    ):
        raise ValidationError(
            "convert_price: cross-currency conversion requires an FX rate and is out of "
            f"scope, got from_unit.currency={from_unit.currency!r}, "
            f"to_unit.currency={to_unit.currency!r}"
        )

    from_is_inert = from_unit.denominator in _INERT_DENOMINATORS
    to_is_inert = to_unit.denominator in _INERT_DENOMINATORS
    if from_is_inert or to_is_inert:
        if from_unit.denominator != to_unit.denominator:
            raise ValidationError(
                f"convert_price: {from_unit.denominator!r} has no energy-content "
                "conversion (a heat-content/calorific-value assumption would be "
                f"required); it converts only to the same denominator, got "
                f"from_unit.denominator={from_unit.denominator!r}, "
                f"to_unit.denominator={to_unit.denominator!r}"
            )
        energy_factor = 1.0
    else:
        energy_factor = _MWH_PER[to_unit.denominator] / _MWH_PER[from_unit.denominator]

    result = value * energy_factor
    if not same_currency:
        result = result * (_minor_scale(to_unit.currency) / _minor_scale(from_unit.currency))
    return result
