"""Shared, deterministic market objects used by the QuantVolt documentation examples."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import quantvolt as qv

MARKET_DATE = date(2026, 7, 15)
OCT_26 = qv.DeliveryPeriod(2026, 10)
NOV_26 = qv.DeliveryPeriod(2026, 11)
DEC_26 = qv.DeliveryPeriod(2026, 12)
JAN_27 = qv.DeliveryPeriod(2027, 1)
MAR_27 = qv.DeliveryPeriod(2027, 3)

TTF = qv.BUILT_IN_COMMODITIES["TTF"]
POWER = qv.BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
EUA = qv.BUILT_IN_COMMODITIES["EUA"]


def _records(prefix: str, commodity: qv.CommodityConfig, prices: tuple[float, ...]):
    periods = (OCT_26, DEC_26, MAR_27)
    return [
        qv.InstrumentPriceRecord(f"{prefix}-{period.year}-{period.month:02d}", commodity, period, price)
        for period, price in zip(periods, prices, strict=True)
    ]


def build_curve(commodity: qv.CommodityConfig, records: list[qv.InstrumentPriceRecord]):
    return qv.CurveBuilder().build(
        commodity,
        MARKET_DATE,
        records,
        interpolation="piecewise_linear",
    ).curve


@dataclass(frozen=True)
class ExampleMarket:
    ttf_curve: qv.ForwardCurve
    power_curve: qv.ForwardCurve
    eua_curve: qv.ForwardCurve
    discount_curve: qv.DiscountCurve


def example_market() -> ExampleMarket:
    """Return the complete curve set shared by documentation examples."""
    discount_curve = qv.DiscountCurve(
        reference_date=MARKET_DATE,
        tenors=(date(2026, 7, 16), date(2028, 12, 31)),
        factors=(1.0, 0.94),
    )
    return ExampleMarket(
        ttf_curve=build_curve(TTF, _records("TTF", TTF, (31.40, 36.85, 34.10))),
        power_curve=build_curve(POWER, _records("POWER", POWER, (84.00, 92.00, 86.50))),
        eua_curve=build_curve(EUA, _records("EUA", EUA, (76.00, 78.00, 79.50))),
        discount_curve=discount_curve,
    )
