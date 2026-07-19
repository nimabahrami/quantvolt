"""OFFLINE generator: Bachelier (normal) golden fixture vs QuantLib.

Maintainer-only tool (spec ``.kiro/specs/bachelier-negative-forwards/``). Wheel-excluded, never
run in CI. Writes ``tests/validation/fixtures/bachelier.json``.

Mathematics is cited, never restated from memory: the Bachelier premium / Greeks / implied-vol
inversion live in ``.kiro/specs/bachelier-negative-forwards/design.md`` and the kernel
``src/quantvolt/numerics/bachelier.py`` (premium Eq. (1) / Footnote 5; degenerate
``sigma_N*sqrt(T)=0`` fallback; Greek sign/carry conventions derived from Eq. (1), mirroring
``black76.py:158-180``).

The whole point of this fixture is that **negative and zero forwards and strikes are valid** — the
matrix deliberately spans ``F, K < 0``.

References (read live from the pinned QuantLib 1.43):

* **premium** — ``QuantLib.bachelierBlackFormula(optionType, strike, forward, stdDev, discount)``.
  **Argument-order mapping (verified live via ``help(ql.bachelierBlackFormula)`` on QuantLib
  1.43):** the signature is ``(optionType, strike, forward, stdDev, discount=1.0)`` — note
  **strike comes before forward** (same order as ``ql.blackFormula``), and ``stdDev = sigma_N *
  sqrt(T)`` is the *total* normal standard deviation over ``[0, T]`` (not the per-sqrt(year)
  rate). This is convention-identical to QuantVolt's forward-based Bachelier (both take the
  forward ``F`` directly and discount by ``DF``), so no forward-vs-spot re-derivation is
  introduced. At ``stdDev = 0`` it returns the discounted intrinsic, matching QuantVolt's
  degenerate fallback.
* **delta / gamma / vega** — central finite differences of ``bachelierBlackFormula`` matching
  QuantVolt's exact conventions: ``delta = d(price)/dF``, ``gamma = d2(price)/dF2``,
  ``vega = d(price)/d(sigma_N)`` (bump the per-sqrt(year) ``sigma_N``, i.e. bump ``stdDev`` by
  ``dSigma * sqrt(T)``). QuantLib exposes no forward-native Bachelier calculator, so a
  finite-difference reference of its own closed form is the cleanest external anchor.
* **theta / rho** — central finite differences of ``bachelierBlackFormula``: ``theta =
  -d(price)/dT`` holding ``F`` and ``r`` fixed with ``DF = e^{-rT}``; ``rho = d(price)/dr``
  holding ``F, sigma_N, T`` fixed with ``DF = e^{-rT}``; ``r = -ln(DF)/T``.
* **implied_vol** — ``ql.bachelierBlackFormulaImpliedVol(optionType, strike, forward, tte,
  bachelierPrice, discount)`` returns the per-sqrt(year) ``sigma_N`` **directly** (it takes
  ``tte`` and divides internally), so — unlike the Black-76 generator, which divides
  ``blackFormulaImpliedStdDev`` by ``sqrt(T)`` — NO ``sqrt(T)`` division is applied here.

Tolerances: premium rel 1e-9 (both closed forms; residual = the two normal-CDF implementations'
difference). delta/gamma/vega/theta/rho rel 1e-6 (4th-order central finite difference of the
reference premium — O(h^4) truncation, not a modelling difference; same precedent as the Black-76
theta/rho fixtures). implied_vol rel 1e-7 (root-finder termination). Near-zero references (deep
OTM) fall back to an absolute floor since a relative bound is meaningless there.

Usage::

    uv pip install "QuantLib>=1.43"
    python scripts/fixtures/gen_bachelier_fixtures.py
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
    tol_for,
    write_quantlib_fixture,
)

from quantvolt.numerics.bachelier import (
    bachelier_greeks,
    bachelier_implied_vol,
    bachelier_price,
)

# --- deterministic case matrix (negative F, K are the point) ------------------------------
FORWARDS = (-25.0, -5.0, 0.0, 5.0, 45.0, 100.0)
STRIKES = (-30.0, -10.0, 0.0, 10.0, 50.0, 100.0)
SIGMAS = (1.0, 5.0, 20.0, 50.0)
TENORS = (0.02, 0.25, 1.0, 3.0)
DFS = (1.0, 0.97, 0.85)
TYPES = ("call", "put")

# "meaningful pairs": keep |F - K| within a few normal-vol std devs at the shortest tenor so the
# grid concentrates where the option has non-negligible value / invertible vega, while still
# spanning the sign combinations (F<0<K, F=K, K<0<F, both negative, zeros). At the largest
# |F - K| = 130 (F=-30ish vs K=100), even sigma_N=50, T=3 gives stdDev ~ 87, so the option is
# ~1.5 std deep -- still meaningful. So we keep the full cross but skip the single most extreme
# corner combinations that are numerically all-intrinsic at every sigma (|F - K| > 120 with the
# smallest sigma*sqrt(T)).
_MAX_MEANINGFUL_GAP = 120.0

_QL_TYPE = {"call": ql.Option.Call, "put": ql.Option.Put}


def _ql_premium(
    option_type: str, forward: float, strike: float, std_dev: float, df: float
) -> float:
    """QuantLib Bachelier premium. Arg order: (type, STRIKE, FORWARD, stdDev, discount)."""
    return float(ql.bachelierBlackFormula(_QL_TYPE[option_type], strike, forward, std_dev, df))


def _reference_greeks(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float
) -> tuple[float, float, float, float, float]:
    """(delta, gamma, vega, theta, rho) by finite difference of ``bachelierBlackFormula``."""
    sqrt_t = math.sqrt(t)
    rate = -math.log(df) / t

    def price_f(fv: float) -> float:
        return _ql_premium(option_type, fv, strike, sigma * sqrt_t, df)

    def price_sigma(sv: float) -> float:
        return _ql_premium(option_type, forward, strike, sv * sqrt_t, df)

    def price_t(tv: float) -> float:
        return _ql_premium(
            option_type, forward, strike, sigma * math.sqrt(tv), math.exp(-rate * tv)
        )

    def price_r(rv: float) -> float:
        return _ql_premium(option_type, forward, strike, sigma * sqrt_t, math.exp(-rv * t))

    scale = max(abs(forward), abs(strike), sigma, 1.0)
    h_f = 1e-3 * scale
    delta = fd_first(price_f, forward, h_f)
    # gamma = d2(price)/dF2 via the O(h^4) 5-point second-derivative stencil. Its step must
    # scale with the gamma-peak *width* sigma_N*sqrt(T) (not the price scale): a price-scaled h
    # straddles the peak and blows up the truncation error. alpha=0.03 is the empirical sweet
    # spot (worst rel ~6e-6 for gamma>1e-6, worst abs ~8e-8 across the grid).
    h_g = 0.03 * sigma * sqrt_t
    gamma = (
        -price_f(forward + 2 * h_g)
        + 16.0 * price_f(forward + h_g)
        - 30.0 * price_f(forward)
        + 16.0 * price_f(forward - h_g)
        - price_f(forward - 2 * h_g)
    ) / (12.0 * h_g * h_g)
    h_s = 1e-3 * sigma
    vega = fd_first(price_sigma, sigma, h_s)
    h_t = 1e-3 * t
    theta = -fd_first(price_t, t, h_t)
    h_r = 1e-3
    rho = fd_first(price_r, rate, h_r)
    return delta, gamma, vega, theta, rho


def _implied_vol_reference(
    option_type: str,
    premium: float,
    forward: float,
    strike: float,
    t: float,
    df: float,
    sigma: float,
) -> float | None:
    """Round-trip implied vol via QuantLib, only where the inversion is well-conditioned.

    Returns ``None`` when the premium sits on the intrinsic lower bound / has negligible vega, or
    QuantLib fails to recover the input vol -- those are legitimately un-invertible.
    """
    intrinsic = df * (
        max(forward - strike, 0.0) if option_type == "call" else max(strike - forward, 0.0)
    )
    if not premium > intrinsic + 1e-8:
        return None
    try:
        implied = ql.bachelierBlackFormulaImpliedVol(
            _QL_TYPE[option_type], strike, forward, t, premium, df
        )
    except RuntimeError:
        return None
    if not math.isfinite(implied) or abs(implied - sigma) > 1e-4 * sigma:
        return None
    return float(implied)


def _grid_case(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float
) -> dict[str, Any]:
    std_dev = sigma * math.sqrt(t)
    premium = _ql_premium(option_type, forward, strike, std_dev, df)
    delta, gamma, vega, theta, rho = _reference_greeks(option_type, forward, strike, sigma, t, df)

    inputs = {
        "option_type": option_type,
        "forward": forward,
        "strike": strike,
        "normal_sigma": sigma,
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
        "delta": tol_for(delta, 1e-6, 1e-8),
        "gamma": tol_for(gamma, 1e-5, 1e-6),
        "vega": tol_for(vega, 1e-6, 1e-9),
        "theta": tol_for(theta, 1e-6, 1e-8),
        "rho": tol_for(rho, 1e-6, 1e-8),
    }

    implied = _implied_vol_reference(option_type, premium, forward, strike, t, df, sigma)
    if implied is not None:
        reference["implied_vol"] = implied
        tolerance["implied_vol"] = tol_for(implied, 1e-7, 1e-9)

    case_id = f"{option_type}_F{forward:g}_K{strike:g}_s{sigma:g}_T{t:g}_DF{df:g}"

    # Generation self-check against the QuantVolt kernel (fail loudly on a broken fixture).
    qv_greeks = bachelier_greeks(option_type, forward, strike, sigma, t, df)
    check_within(
        bachelier_price(option_type, forward, strike, sigma, t, df),
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
        qv_iv = bachelier_implied_vol(option_type, premium, forward, strike, t, df, tol=1e-12)
        check_within(qv_iv, implied, tolerance["implied_vol"], f"{case_id}.implied_vol")

    return {
        "case_id": case_id,
        "inputs": inputs,
        "reference": reference,
        "tolerance": tolerance,
        "tolerance_rationale": (
            "premium rel 1e-9 (abs floor 1e-12): both closed forms; residual = the two "
            "normal-CDF implementations' difference (QuantLib bachelierBlackFormula vs quantvolt "
            "bachelier). delta/vega/theta/rho rel 1e-6 (abs floor 1e-8/1e-9): 4th-order central "
            "finite difference of the reference premium (O(h^4) truncation). gamma rel 1e-5 (abs "
            "floor 1e-6): O(h^4) 5-point second-derivative stencil with a step scaled to the "
            "gamma-peak width sigma_N*sqrt(T) (worst rel ~6e-6 / worst abs ~8e-8 across the grid). "
            "implied_vol rel 1e-7: root-finder termination. Where a reference number is near zero "
            "(deep OTM), a relative bound is meaningless so an absolute floor is used instead."
        ),
        "notes": (
            "QuantLib arg order (verified live, QuantLib 1.43): bachelierBlackFormula(type, "
            "STRIKE, FORWARD, stdDev=sigma_N*sqrt(T), discount). Negative/zero F, K are valid "
            "Bachelier inputs. QuantVolt Greek conventions: delta=d(price)/dF, "
            "gamma=d2(price)/dF2, vega=d(price)/d(sigma_N) (no F factor), theta=-d(price)/dT "
            "(r,F fixed), rho=d(price)/dr=-T*price (F fixed)."
        ),
    }


def _degenerate_case(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float
) -> dict[str, Any]:
    """A sigma_N=0 or T=0 edge: bachelierBlackFormula at stdDev=0 == discounted intrinsic."""
    return degenerate_case(
        option_type=option_type,
        forward=forward,
        strike=strike,
        sigma=sigma,
        t=t,
        df=df,
        sigma_field="normal_sigma",
        ql_premium=_ql_premium,
        qv_premium=bachelier_price,
        tolerance_rationale=(
            "degenerate sigma_N*sqrt(T)=0 edge: reference is QuantLib bachelierBlackFormula at "
            "stdDev=0, which equals the discounted intrinsic; the comparison asserts QuantVolt's "
            "documented discounted-intrinsic identity to abs 1e-12 (exact arithmetic limit)."
        ),
    )


def _parity_self_check() -> None:
    """Self-check put-call parity C - P = DF*(F - K) for every (F, K, sigma, T, DF) quintuple."""
    for forward, strike, sigma, t, df in product(FORWARDS, STRIKES, SIGMAS, TENORS, DFS):
        call = _ql_premium("call", forward, strike, sigma * math.sqrt(t), df)
        put = _ql_premium("put", forward, strike, sigma * math.sqrt(t), df)
        expected = df * (forward - strike)
        if abs((call - put) - expected) > 1e-9 * max(abs(expected), 1.0):
            raise AssertionError(
                f"put-call parity failed at F={forward} K={strike} s={sigma} T={t} DF={df}: "
                f"C-P={call - put} != DF(F-K)={expected}"
            )


def build_cases() -> list[dict[str, Any]]:
    _parity_self_check()
    cases: list[dict[str, Any]] = []
    for option_type, forward, strike, sigma, t, df in product(
        TYPES, FORWARDS, STRIKES, SIGMAS, TENORS, DFS
    ):
        if abs(forward - strike) > _MAX_MEANINGFUL_GAP:
            continue
        cases.append(_grid_case(option_type, forward, strike, sigma, t, df))
    # Degenerate edges: sigma_N=0 (T from the grid) and T=0 (sigma from the grid), spanning signs.
    for option_type in TYPES:
        for df in DFS:
            for forward, strike in ((-25.0, -30.0), (5.0, 10.0), (100.0, 100.0), (0.0, 10.0)):
                cases.append(_degenerate_case(option_type, forward, strike, 0.0, 1.0, df))
                cases.append(_degenerate_case(option_type, forward, strike, 20.0, 0.0, df))
    return cases


def main() -> None:
    cases = build_cases()
    path = write_quantlib_fixture(
        "bachelier.json", "scripts/fixtures/gen_bachelier_fixtures.py", cases
    )
    n_iv = sum(1 for c in cases if "implied_vol" in c["reference"])
    n_deg = sum(1 for c in cases if c["inputs"].get("degenerate"))
    print(f"wrote {path} : {len(cases)} cases ({n_deg} degenerate, {n_iv} with implied_vol)")


if __name__ == "__main__":
    main()
