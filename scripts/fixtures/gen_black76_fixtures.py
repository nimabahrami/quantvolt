"""OFFLINE generator: Black-76 golden fixture vs QuantLib (Requirement 3, Task 3).

Maintainer-only tool (spec ``.kiro/specs/external-validation/``). Wheel-excluded, never run in
CI. Writes ``tests/validation/fixtures/black76.json``.

Mathematics is cited, never restated from memory: Black-76 premium / Greeks / implied-vol
inversion live in the base spec ``.kiro/specs/power-energy-quant-analysis/design.md`` §2.7 and
the kernel ``src/quantvolt/numerics/black76.py`` (degenerate ``sigma*sqrt(T)=0`` fallback at
:88-92; Greek sign/carry conventions at :158-180).

References (all read live from the pinned QuantLib):

* **premium** — ``QuantLib.blackFormula(type, K, F, stdDev, DF)`` with ``stdDev = sigma*sqrt(T)``.
  This is *convention-identical* to QuantVolt's forward-based Black-76 (both take the forward
  ``F`` directly and discount by ``DF``), so **no forward-vs-spot re-derivation is introduced**
  (Requirement 3.1). At ``stdDev = 0`` QuantLib returns the discounted intrinsic, matching
  QuantVolt's documented degenerate fallback (black76.py:88-92).
* **delta / gamma / vega** — taken *directly* from QuantLib's forward-native
  ``BlackCalculator(payoff, forward, stdDev, DF)`` via ``deltaForward()`` / ``gammaForward()`` /
  ``vega(T)``. Like ``blackFormula`` this is convention-identical to QuantVolt's forward-based
  Black-76 and needs **no dates**, so it introduces neither a forward-vs-spot re-derivation nor
  the year-fraction rounding a process-based engine would incur at the ``T=0.02`` tail. The
  forward Greeks reduce exactly to QuantVolt's ``DF``-discounted forward Greeks
  (black76.py:158-180).
* **theta / rho** — central finite differences of ``blackFormula`` matching QuantVolt's exact
  conventions (black76.py:158-180): ``theta = -d(price)/dT`` holding ``F`` and ``r`` fixed with
  ``DF = e^{-rT}``; ``rho = d(price)/dr`` holding ``F, sigma, T`` fixed with ``DF = e^{-rT}``.
  ``r = -ln(DF)/T``.
* **implied_vol** — round-trip ``price -> implied stdDev`` via ``blackFormulaImpliedStdDev``
  divided by ``sqrt(T)``, comparable to ``black76_implied_vol`` (only where the inversion is
  well-conditioned: strictly inside the no-arbitrage bounds with meaningful vega).

Tolerances (Requirement 3.5): premium rel 1e-9 and delta/gamma/vega rel 1e-9 (both closed
forms; residual = the two normal-CDF implementations' difference); theta/rho rel 1e-6
(4th-order central finite difference of the reference premium — O(h^4) truncation, not a
modelling difference); implied_vol rel 1e-7 (root-finder termination). Near-zero references
(deep OTM) fall back to an absolute floor since a relative bound is meaningless there.

Usage::

    uv pip install "QuantLib>=1.34"
    python scripts/fixtures/gen_black76_fixtures.py
"""

from __future__ import annotations

import math
from itertools import product
from typing import Any

import QuantLib as ql
from _gen_common import (  # type: ignore[import-not-found]
    check_within,
    degenerate_case,
    fd_first,
    rel,
    tol_for,
    write_quantlib_fixture,
)

from quantvolt.numerics.black76 import black76_greeks, black76_implied_vol, black76_price

# --- deterministic case matrix (Requirement 3.1) -----------------------------------------
MONEYNESS = (0.5, 0.8, 0.95, 1.0, 1.05, 1.25, 2.0)  # F / K
SIGMAS = (0.05, 0.20, 0.55, 1.00)
TENORS = (0.02, 0.25, 1.0, 3.0)
DFS = (1.0, 0.97, 0.85)
TYPES = ("call", "put")
# "an F=100 set plus one energy-realistic set": the F=100 set is the full cross; the energy
# set (F=45 EUR/MWh, TTF-scale) is a representative front/calendar, mid-vol, single-DF grid.
FORWARD_F100 = 100.0
FORWARD_ENERGY = 45.0
ENERGY_SIGMAS = (0.20, 0.55)
ENERGY_TENORS = (0.25, 1.0)
ENERGY_DFS = (0.97,)

_QL_TYPE = {"call": ql.Option.Call, "put": ql.Option.Put}


def _ql_premium(
    option_type: str, forward: float, strike: float, std_dev: float, df: float
) -> float:
    return float(ql.blackFormula(_QL_TYPE[option_type], strike, forward, std_dev, df))


def _calculator_greeks(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float
) -> tuple[float, float, float]:
    """(delta, gamma, vega) from QuantLib's forward-native ``BlackCalculator``.

    ``BlackCalculator(payoff, forward, stdDev, discount)`` is convention-identical to
    QuantVolt's forward-based Black-76 — it takes the forward and ``DF`` directly and needs
    **no dates** (so no forward-vs-spot re-derivation, and no day-count/year-fraction rounding
    that a process-based engine would introduce, which matters at the ``T=0.02`` tail).
    ``deltaForward()`` / ``gammaForward()`` are the forward-based ``DF*N(d1)`` / ``DF*n(d1)/(F
    sigma sqrt T)`` Greeks; ``vega(T)`` is ``DF*F*n(d1)*sqrt(T)`` — exactly QuantVolt's
    conventions (black76.py:158-180).
    """
    calc = ql.BlackCalculator(
        ql.PlainVanillaPayoff(_QL_TYPE[option_type], strike), forward, sigma * math.sqrt(t), df
    )
    return float(calc.deltaForward()), float(calc.gammaForward()), float(calc.vega(t))


def _fd_theta_rho(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float
) -> tuple[float, float]:
    """theta/rho by 4th-order central finite difference of ``blackFormula`` (Req 3.3).

    QuantVolt conventions (black76.py:158-180): ``theta = -d(price)/dT`` with ``F`` and
    ``r`` fixed and ``DF = e^{-rT}``; ``rho = d(price)/dr`` with ``F, sigma, T`` fixed and
    ``DF = e^{-rT}``. ``r = -ln(DF)/T``. The shared 4th-order stencil (:func:`fd_first`,
    O(h^4) truncation) keeps the reference accurate even in the deep-OTM tail where a
    2nd-order stencil loses digits.
    """
    rate = -math.log(df) / t

    def price_t(tv: float) -> float:
        return _ql_premium(
            option_type, forward, strike, sigma * math.sqrt(tv), math.exp(-rate * tv)
        )

    def price_r(rv: float) -> float:
        return _ql_premium(option_type, forward, strike, sigma * math.sqrt(t), math.exp(-rv * t))

    theta = -fd_first(price_t, t, 1e-3 * t)
    rho = fd_first(price_r, rate, 1e-3)
    return theta, rho


def _implied_vol_reference(
    option_type: str,
    premium: float,
    forward: float,
    strike: float,
    t: float,
    df: float,
    sigma: float,
) -> float | None:
    """Round-trip implied vol via QuantLib, only where inversion is well-conditioned.

    Returns ``None`` (no ``implied_vol`` reference emitted) when the premium sits on a
    no-arbitrage bound, has negligible vega, or the inversion fails to recover the input vol
    — those are legitimately un-invertible, not a QuantVolt defect.
    """
    if option_type == "call":
        lower, upper = df * max(forward - strike, 0.0), df * forward
    else:
        lower, upper = df * max(strike - forward, 0.0), df * strike
    if not lower + 1e-10 < premium < upper - 1e-10:
        return None
    try:
        std_dev = ql.blackFormulaImpliedStdDev(
            _QL_TYPE[option_type],
            strike,
            forward,
            premium,
            df,
            0.0,
            sigma * math.sqrt(t),
            1e-12,
            200,
        )
    except RuntimeError:
        return None
    implied = std_dev / math.sqrt(t)
    if not math.isfinite(implied) or abs(implied - sigma) > 1e-3:
        return None
    return float(implied)


def _grid_case(
    forward: float, option_type: str, moneyness: float, sigma: float, t: float, df: float
) -> dict[str, Any]:
    strike = forward / moneyness
    std_dev = sigma * math.sqrt(t)
    premium = _ql_premium(option_type, forward, strike, std_dev, df)
    delta, gamma, vega = _calculator_greeks(option_type, forward, strike, sigma, t, df)
    theta, rho = _fd_theta_rho(option_type, forward, strike, sigma, t, df)

    inputs = {
        "option_type": option_type,
        "forward": forward,
        "strike": strike,
        "sigma": sigma,
        "time_to_expiry": t,
        "discount_factor": df,
    }
    reference: dict[str, float] = {
        "premium": premium,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
        "rho": rho,
    }
    tolerance: dict[str, Any] = {
        "premium": tol_for(premium, 1e-9, 1e-12),
        "delta": tol_for(delta, 1e-9, 1e-12),
        "gamma": tol_for(gamma, 1e-9, 1e-12),
        "vega": tol_for(vega, 1e-9, 1e-12),
        "theta": tol_for(theta, 1e-6, 1e-9),
        "rho": tol_for(rho, 1e-6, 1e-9),
    }

    implied = _implied_vol_reference(option_type, premium, forward, strike, t, df, sigma)
    if implied is not None:
        reference["implied_vol"] = implied
        tolerance["implied_vol"] = rel(1e-7)  # 0.05<=iv<=1.0 by construction, well above any floor

    # Generation self-check against the QuantVolt kernel (fail loudly on a broken fixture).
    case_id = f"{option_type}_F{forward:g}_K{strike:.6g}_s{sigma:g}_T{t:g}_DF{df:g}"
    qv_greeks = black76_greeks(option_type, forward, strike, sigma, t, df)
    check_within(
        black76_price(option_type, forward, strike, sigma, t, df),
        premium,
        tolerance["premium"],
        f"{case_id}.premium",
    )
    check_within(qv_greeks.delta, delta, tolerance["delta"], f"{case_id}.delta")
    check_within(qv_greeks.gamma, gamma, tolerance["gamma"], f"{case_id}.gamma")
    check_within(qv_greeks.vega, vega, tolerance["vega"], f"{case_id}.vega")
    check_within(qv_greeks.theta, theta, tolerance["theta"], f"{case_id}.theta")
    check_within(qv_greeks.rho, rho, tolerance["rho"], f"{case_id}.rho")
    if implied is not None:
        qv_iv = black76_implied_vol(option_type, premium, forward, strike, t, df, tol=1e-12)
        check_within(qv_iv, implied, tolerance["implied_vol"], f"{case_id}.implied_vol")

    return {
        "case_id": case_id,
        "inputs": inputs,
        "reference": reference,
        "tolerance": tolerance,
        "tolerance_rationale": (
            "premium & delta/gamma/vega rel 1e-9: both closed forms; residual = the two "
            "normal-CDF implementations' difference (QuantLib blackFormula / forward-native "
            "BlackCalculator, vs quantvolt black76). "
            "theta/rho rel 1e-6: 4th-order central finite difference of the reference premium "
            "(O(h^4) truncation, ~2e-7 worst-case across the grid). implied_vol rel 1e-7: "
            "root-finder termination. Where a reference number is near zero (deep OTM), a relative "
            "bound is meaningless so an absolute floor is used instead (abs 1e-12 for "
            "premium/greeks, 1e-9 for theta/rho)."
        ),
        "notes": (
            "QuantVolt Greek sign/carry conventions compared (black76.py:158-180): "
            "delta=d(price)/dF, gamma=d2(price)/dF2, vega=d(price)/dsigma, "
            "theta=-d(price)/dT (r,F fixed), rho=d(price)/dr=-T*price (F fixed)."
        ),
    }


def _degenerate_case(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float
) -> dict[str, Any]:
    """A sigma=0 or T=0 edge: QuantLib blackFormula at stdDev=0 == discounted intrinsic.

    Marked ``degenerate: true`` so the comparison test asserts QuantVolt's documented
    discounted-intrinsic identity (black76.py:88-92) rather than inverting QuantLib (Req 3.2).
    """
    return degenerate_case(
        option_type=option_type,
        forward=forward,
        strike=strike,
        sigma=sigma,
        t=t,
        df=df,
        sigma_field="sigma",
        ql_premium=_ql_premium,
        qv_premium=black76_price,
        tolerance_rationale=(
            "degenerate sigma*sqrt(T)=0 edge: reference is QuantLib blackFormula at stdDev=0, "
            "which equals the discounted intrinsic DF*max(F-K,0)/DF*max(K-F,0); the comparison "
            "asserts QuantVolt's documented discounted-intrinsic identity (black76.py:88-92) "
            "to abs 1e-12 (exact arithmetic limit)."
        ),
    )


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    # F=100 full cross.
    for option_type, moneyness, sigma, t, df in product(TYPES, MONEYNESS, SIGMAS, TENORS, DFS):
        cases.append(_grid_case(FORWARD_F100, option_type, moneyness, sigma, t, df))
    # Energy-realistic representative set (F=45 EUR/MWh).
    for option_type, moneyness, sigma, t, df in product(
        TYPES, MONEYNESS, ENERGY_SIGMAS, ENERGY_TENORS, ENERGY_DFS
    ):
        cases.append(_grid_case(FORWARD_ENERGY, option_type, moneyness, sigma, t, df))
    # Degenerate edges: sigma=0 (T from the grid) and T=0 (sigma from the grid).
    for option_type in TYPES:
        for df in DFS:
            for strike in (80.0, 100.0, 125.0):
                cases.append(_degenerate_case(option_type, 100.0, strike, 0.0, 1.0, df))
                cases.append(_degenerate_case(option_type, 100.0, strike, 0.20, 0.0, df))
    return cases


def main() -> None:
    cases = build_cases()
    path = write_quantlib_fixture("black76.json", "scripts/fixtures/gen_black76_fixtures.py", cases)
    n_iv = sum(1 for c in cases if "implied_vol" in c["reference"])
    n_deg = sum(1 for c in cases if c["inputs"].get("degenerate"))
    print(f"wrote {path} : {len(cases)} cases ({n_deg} degenerate, {n_iv} with implied_vol)")


if __name__ == "__main__":
    main()
