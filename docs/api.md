# quantvolt API reference

The top-level `quantvolt` namespace is a curated facade: the domain value objects, the curve
builder, the pricing entry points, and the risk/portfolio engines are importable directly
(`import quantvolt as qv`). Deeper or more specialised names stay on their sub-packages
(`quantvolt.numerics`, `quantvolt.stats`, `quantvolt.market`, `quantvolt.workflow`,
`quantvolt.testing`, `quantvolt.data`). Every example below is runnable as-is.

Conventions that hold across the whole library:

- All value objects are frozen (`@dataclass(frozen=True, slots=True)`); nothing mutates caller data.
- Validation is eager and loud: bad inputs raise a subclass of `quantvolt.exceptions.EnergyQuantError`
  (`ValidationError`, `InsufficientDataError`, `MissingTenorError`, `ArbitrageError`, …) before any
  computation runs.
- Anything random takes a `seed`; identical inputs give identical outputs.
- The package ships `py.typed` — all signatures below are visible to your type checker.

---

## `quantvolt.models` — domain value objects

The immutable domain vocabulary shared by every other module.

**Public names**: `BUILT_IN_COMMODITIES`, `CommodityConfig`, `Hub`, `merge_commodities`,
`resolve_commodity` · `DeliveryPeriod`, `DeliverySchedule`, `Granularity` · `CurveNode`,
`ForwardCurve` · `DiscountCurve` · `Moneyness`, `VolatilityTenor`, `VolatilitySurface` ·
`FuturesContract`, `ForwardContract`, `SwapContract`, `InstrumentPriceRecord`, `PlantConfig`,
`SettlementType`, `RiskType` · `Greeks`

```python
from datetime import date

from quantvolt.models import BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, ForwardCurve

power = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
curve = ForwardCurve(
    commodity=power,
    market_date=date(2026, 7, 15),
    nodes=(
        CurveNode(DeliveryPeriod(2026, 8), 78.50, "observed"),
        CurveNode(DeliveryPeriod(2026, 9), -4.25, "observed"),  # negative prices are accepted
    ),
)
print(curve.price_at(DeliveryPeriod(2026, 9)))            # -4.25
assert ForwardCurve.from_dict(curve.to_dict()) == curve   # JSON-friendly round trip
```

Serialisation lives on the model: `to_dict()`/`from_dict()` round-trip through plain built-ins,
which is also what `quantvolt.data.snapshot`/`restore` use for reproducible replays. The
commodity registry is extended, never edited — `merge_commodities({...})` merges caller entries
over `BUILT_IN_COMMODITIES` (caller wins on id collision).

## `quantvolt.numerics` — pure math kernels

Module-level functions on `float`/`np.ndarray` only — no domain types, no validation. Every
pricer orchestrates these; use them directly when you have raw numbers.

**Public names**: `black76_price`, `black76_greeks`, `black76_implied_vol` · `kirk`, `margrabe` ·
`turnbull_wakeman`, `kemna_vorst`, `barrier_analytic`, `lookback_fixed`, `lookback_floating` ·
`asian_monte_carlo` · `build_covariance`, `simulate_correlated_forwards` · `price_of_risk`,
`tradable_price_of_risk`, `risk_adjusted_drift`, `require_physical_drift`, `PriceOfRiskKind`,
`DriftKind` · `piecewise_flat`, `piecewise_linear`, `cubic_spline`, `INTERPOLATION_METHODS`,
`InterpolationMethod` · `brent_root`, `finite_difference_bump` · `actual_365`

```python
from quantvolt.numerics import asian_monte_carlo, black76_implied_vol, black76_price

premium = black76_price("call", forward=36.85, strike=38.0, sigma=0.55,
                        time_to_expiry=0.4, discount_factor=0.99)
sigma = black76_implied_vol("call", premium, forward=36.85, strike=38.0,
                            time_to_expiry=0.4, discount_factor=0.99)  # recovers 0.55

mc_premium, std_err = asian_monte_carlo(  # Rust kernel; same seed -> identical result
    forward=36.85, strike=38.0, sigma=0.55, time_to_expiry=0.4, discount_factor=0.99,
    averaging_points=12, option_type="call", geometric=False, seed=7, path_count=50_000,
)
```

`asian_monte_carlo` returns `(premium, standard_error)` and is the thin wrapper over the native
`quantvolt._core` extension — the only non-Python code in the library.
`simulate_correlated_forwards` (driving a `build_covariance` covariance) is the correlated-GBM
path engine the risk and asset models build on, and the `risk_adjustment` kernels — `price_of_risk`,
`risk_adjusted_drift`, `require_physical_drift`, plus the `PriceOfRiskKind` (market vs corporate)
and `DriftKind` (physical P vs risk-neutral Q) tags — carry the measure discipline documented in
[risk-and-assets.md](risk-and-assets.md).

## `quantvolt.curves` — forward curve construction

`CurveBuilder` turns observed instrument prices into a gap-filled monthly `ForwardCurve`;
`ArbitrageChecker` flags calendar spreads inconsistent with the cost of carry.

**Public names**: `CurveBuilder`, `CurveBuildResult`, `ArbitrageChecker`, `ArbitrageWarning`

```python
from datetime import date

from quantvolt import BUILT_IN_COMMODITIES, CurveBuilder, DeliveryPeriod, InstrumentPriceRecord

ttf = BUILT_IN_COMMODITIES["TTF"]
observed = [
    InstrumentPriceRecord("TTF-2026-10", ttf, DeliveryPeriod(2026, 10), 31.40),
    InstrumentPriceRecord("TTF-2027-01", ttf, DeliveryPeriod(2027, 1), 37.20),
]
result = CurveBuilder().build(
    ttf, date(2026, 7, 15), observed,
    interpolation="piecewise_linear",   # or "piecewise_flat" / "cubic_spline"
    storage_cost=0.5,                   # EUR/MWh per month of carry, for the arbitrage check
)
print([(n.period, round(n.price, 2), n.status) for n in result.curve.nodes])
# [(2026-10, 31.4, 'observed'), (2026-11, 33.33, 'interpolated'),
#  (2026-12, 35.27, 'interpolated'), (2027-01, 37.2, 'observed')]
print(result.arbitrage_warnings, result.reprice_residuals)
```

`CurveBuilder(extra_commodities={...})` accepts caller-defined commodities merged over the
built-ins. Each interpolation method enforces its minimum instrument count (flat 1, linear 2,
cubic spline 4) and raises `InsufficientDataError` below it. `CurveBuildResult` carries the
curve, the arbitrage warnings, and per-instrument reprice residuals.

## `quantvolt.pricing` — derivatives pricing and spreads

Orchestration layer: a request object (or typed arguments) in, a frozen result object out.

**Public names**: `price_futures`, `futures_delta`, `FuturesPricingResult` · `price_swap`,
`SwapPricingResult` · `price_vanilla_option`, `price_cap_floor`, `VanillaOptionRequest`,
`VanillaOptionResult`, `CapFloorRequest`, `CapFloorResult` · `price_asian`, `price_barrier`,
`price_lookback`, `AsianOptionRequest`, `BarrierOptionRequest`, `LookbackOptionRequest`,
`ExoticOptionResult` · `price_spread_option`, `price_spark_spread_option`,
`SpreadOptionRequest`, `SpreadOptionResult` · `price_tolling_agreement`, `TollingResult` ·
`spark_spread`, `dark_spread`, `clean_spread`, `forward_spread`, `implied_heat_rate`, `basis`,
`crack_spread`, `calendar_spread` (+ their result types) · `implied_vol`, `classify_moneyness`,
`cumulative_historical_vol`, `build_volatility_surface`, `OptionQuote`, `ImpliedVolResult` ·
`mark_to_market`, `MtMPosition`, `MtMPositionResult`, `MtMResult`

```python
from datetime import date

from quantvolt import (
    BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, ForwardCurve,
    VanillaOptionRequest, clean_spread, price_vanilla_option, spark_spread,
)

option = price_vanilla_option(VanillaOptionRequest(
    option_type="call", strike=38.0, notional=10_000.0,
    forward=36.85, sigma=0.55, time_to_expiry=0.4, discount_factor=0.99,
))
print(f"premium {option.premium:,.0f} EUR, vega {option.greeks.vega:,.0f}")

def curve(commodity_id: str, price: float) -> ForwardCurve:
    return ForwardCurve(
        BUILT_IN_COMMODITIES[commodity_id], date(2026, 7, 15),
        (CurveNode(DeliveryPeriod(2026, 12), price, "observed"),),
    )

spread = spark_spread(curve("EEX_PHELIX_DE", 92.0), curve("TTF", 36.85),
                      heat_rate=2.0, variable_cost=3.5, emissions_cost=0.0)
clean = clean_spread(spread, curve("EUA", 78.0), emissions_intensity=0.37)
print(spread.per_period)   # {2026-12: 14.80}  power - heat_rate*gas - variable_cost
print(clean.per_period)    # {2026-12: -14.06} after deducting 0.37 tCO2/MWh * 78 EUR/tCO2
```

Vanilla options and caps/floors are Black-76 with full Greeks; spread options use Kirk (Margrabe
when `strike == 0`); Asians select Turnbull-Wakeman / Kemna-Vorst / Monte Carlo by request.
`mark_to_market` marks positions against exchange settlement prices, falling back to a forward
curve with the result flagged `"estimated"`.

## `quantvolt.risk` — VaR, delta aggregation, stress scenarios

`RiskEngine` operates on the `PricedPosition` objects that `value_portfolio` produces.

**Public names**: `RiskEngine`, `RiskResult`, `ScenarioResult`, `ExcludedPosition` ·
`aggregate_delta`, `DeltaMatrix` · `ScenarioCatalogue`, `ScenarioShock`, `BUILT_IN_SCENARIOS`

```python
from datetime import date

import numpy as np

from quantvolt import (
    BUILT_IN_COMMODITIES, DeliveryPeriod, FuturesContract,
    Position, PricedPosition, RiskEngine,
)

future = FuturesContract(BUILT_IN_COMMODITIES["TTF"], DeliveryPeriod(2026, 12),
                         contract_price=35.0, notional=5_000.0)
priced = PricedPosition(
    position=Position(instrument=future),
    npv=9_133.0,
    delta={("TTF", DeliveryPeriod(2026, 12)): 4_900.0},  # EUR per EUR/MWh
)

engine = RiskEngine()
scenarios = np.random.default_rng(1).normal(0.0, 1.5, size=(500, 1))  # price moves
risk = engine.compute_risk([priced], scenarios)                # VaR 95/99, CVaR 97.5
stress = engine.apply_scenario([priced], "European Gas Crisis 2022")
print(f"VaR(95) {risk.var_95:,.0f}  CVaR(97.5) {risk.cvar_975:,.0f}  "
      f"stress P&L {stress.total_pnl:,.0f}")
```

`compute_risk` nets deltas into a commodity × delivery-period `DeltaMatrix`, requires one
scenario-matrix column per matrix cell, and always returns an exclusion report for unusable
positions. Built-in named scenarios ("European Gas Crisis 2022", "Cold Snap Winter", "Mild
Winter Demand Slump", "Carbon Price Shock") hold relative shocks keyed by
`(commodity_id, period)`, `period=None` meaning commodity-wide; `RiskEngine(ScenarioCatalogue({...}))`
merges your own scenarios over them.

Your own named scenarios are `ScenarioShock` value objects — a name plus a shock vector —
registered on the catalogue and resolved by name:

```python
from quantvolt import (
    BUILT_IN_COMMODITIES, DeliveryPeriod, FuturesContract, Position, PricedPosition,
    RiskEngine, ScenarioCatalogue, ScenarioShock,
)

period = DeliveryPeriod(2026, 12)
priced = PricedPosition(
    position=Position(FuturesContract(BUILT_IN_COMMODITIES["TTF"], period,
                                      contract_price=35.0, notional=5_000.0)),
    npv=9_133.0, delta={("TTF", period): 4_900.0})

engine = RiskEngine(ScenarioCatalogue({
    "Desk: TTF squeeze": ScenarioShock(
        name="Desk: TTF squeeze",
        shocks={("TTF", None): 0.5},   # +50% relative move, commodity-wide (period=None)
    ),
}))
stress = engine.apply_scenario([priced], "Desk: TTF squeeze")
print(f"{stress.scenario_name}: P&L {stress.total_pnl:,.0f}")   # Desk: TTF squeeze: P&L 2,450
```

A `ScenarioShock` is a single deterministic shock vector — it carries no probability
distribution, and the library has no probability-weighted scenario type. To stress with a
*distribution*, sample it into the rows of the `scenario_matrix` passed to `compute_risk`: every
row is treated as equally likely (the VaR/CVaR quantiles are plain percentiles over rows), so any
distribution is expressed by sampling frequency — e.g. `rng.normal(mu, sigma, size=(n, k))` for a
Gaussian factor model, or draws from a fitted `ewma_covariance`/`garch11_covariance` forecast. For
a parametric (GBM) distribution with full repricing use `monte_carlo_var`; for scenario sets with
operational factors use `cash_flow_at_risk`, whose scenario set is likewise exhaustive and
equally weighted.

## `quantvolt.risk` — parametric, Monte Carlo, CFaR and credit VaR

Alongside `RiskEngine`'s historical-simulation VaR (above), the package provides the rest of
the risk family. All four measures below are **physical-measure (P)** — real-world loss/earnings
distributions, not risk-neutral prices; see [risk-and-assets.md](risk-and-assets.md) for the
measure rule and the liquidity caveat.

**Public names**: `parametric_var`, `delta_gamma_var`, `ParametricVaRResult` · `monte_carlo_var`,
`FactorModel`, `TaggedDrift`, `McVaRResult` · `cash_flow_at_risk`, `CFaRResult` · `credit_var`,
`CreditVaRResult`, `CounterpartyCreditDetail` · `ewma_covariance`, `garch11_covariance`, `nearest_psd`

Parametric (variance-covariance) VaR is analytic — no revaluation — from a delta vector and a
covariance forecast (`ewma_covariance` / `garch11_covariance` both return a symmetric PSD matrix):

```python
import numpy as np
from quantvolt.risk import delta_gamma_var, ewma_covariance, parametric_var

rng = np.random.default_rng(0)
returns = rng.normal(0.0, 0.02, size=(500, 3))       # 500 daily obs, 3 factors, oldest first
cov = ewma_covariance(returns, lam=0.94)             # RiskMetrics covariance forecast
deltas = np.array([50_000.0, -20_000.0, 10_000.0])   # EUR per unit factor return

pv = parametric_var(deltas, cov)                     # delta VaR at 95% and 99% (z = 1.645 / 2.326)
gamma = np.diag([2.0e5, 1.0e5, 5.0e4])               # long-gamma book
dg = delta_gamma_var(deltas, gamma, cov)             # Cornish-Fisher delta-gamma VaR
print(f"delta VaR95 {pv.var_at(0.95):,.0f}  VaR99 {pv.var_at(0.99):,.0f}")       # 1,642  2,322
print(f"delta-gamma VaR95 {dg.var_at(0.95):,.0f}  skew {dg.pnl_skewness:+.3f}")  # 1,536  +0.179
```

Positive gamma reduces VaR below the delta figure (the quadratic term only adds to P&L), and with
`Γ = 0` `delta_gamma_var` collapses exactly to `parametric_var`. `Σ` is validated square, symmetric
and PSD (1e-8 tolerance) before any arithmetic; the canonical 95%/99% levels use the mandated
`z = 1.645 / 2.326`.

Monte Carlo VaR fully **revalues** the book on correlated forward-curve scenarios — the method for
materially non-linear books (options, tolling, storage). The drift is required and measure-tagged;
a risk-neutral drift is rejected before any simulation (`require_physical_drift`):

```python
from datetime import date

import numpy as np

from quantvolt import (
    BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, DiscountCurve, ForwardCurve,
    FuturesContract, MarketData, Position,
)
from quantvolt.numerics import DriftKind
from quantvolt.risk import FactorModel, TaggedDrift, monte_carlo_var

ttf = BUILT_IN_COMMODITIES["TTF"]
period = DeliveryPeriod(2026, 12)
curve = ForwardCurve(ttf, date(2026, 7, 15), (CurveNode(period, 36.85, "observed"),))
market = MarketData(
    {"TTF": curve},
    DiscountCurve(date(2026, 7, 15), (date(2026, 7, 16), date(2027, 6, 30)), (1.0, 0.97)),
    date(2026, 7, 15),
)
positions = [Position(FuturesContract(ttf, period, contract_price=35.0, notional=5_000.0))]
factor_model = FactorModel(market_data=market, factors=(("TTF", period),),
                           sigma=np.array([0.5]), corr=np.array([[1.0]]))
drift = TaggedDrift(np.array([0.0]), DriftKind.PHYSICAL)   # physical P required; a Q drift raises
risk = monte_carlo_var(positions, factor_model, drift, holding_period=1 / 52,
                       path_count=20_000, seed=7)
print(f"VaR95 {risk.var_95:,.0f} (se {risk.var_95_se:,.0f})  CVaR97.5 {risk.cvar_975:,.0f}")
# VaR95 19,432 (se 186)  CVaR97.5 27,406
```

Each quantile carries a nonparametric bootstrap standard error; `path_count < 1000` raises, and GBM
dynamics require every current forward strictly positive. `FactorModel.factors` must be strictly
ascending by `(commodity_id, period)` — the same row-major flattening `RiskEngine` uses.

Cash-Flow-at-Risk is a multi-period *earnings* shortfall measure driven by a caller-supplied pure
cash-flow model over an exhaustive factor scenario set (market **and** operational factors together):

```python
import numpy as np
from quantvolt.risk import cash_flow_at_risk

def monthly_cashflow(scenario):                        # pure: one scenario -> per-period vector
    spark = scenario["power"] - 2.0 * scenario["gas"]  # EUR/MWh spark spread
    return np.full(3, 5_000.0 * spark)                 # 3 delivery months

rng = np.random.default_rng(1)
scenarios = [{"power": p, "gas": g}
             for p, g in zip(rng.normal(90.0, 20.0, 400), rng.normal(35.0, 8.0, 400))]
cfar = cash_flow_at_risk(monthly_cashflow, scenarios, horizon=3, seed=1)
print(f"expected {cfar.expected:,.0f}  CFaR95 {cfar.cfar_95:,.0f}  p5 {cfar.p5:,.0f}")
# expected 288,458  CFaR95 582,996  p5 -294,538
```

`cfar_95 = max(0, expected - p5)` is the 95% shortfall of aggregated cash flow below its expected
level, in the model's currency units.

Credit VaR is the counterparty-default loss distribution, simulated jointly with a shared systematic
market factor via a one-factor Gaussian copula. Counterparties are read from each position's
instrument; a counterparty-less position is set aside as credit-risk-free, never dropped silently:

```python
from quantvolt import BUILT_IN_COMMODITIES, DeliveryPeriod, ForwardContract, Position, PricedPosition
from quantvolt.risk import credit_var

ttf = BUILT_IN_COMMODITIES["TTF"]
acme = PricedPosition(
    position=Position(ForwardContract(ttf, DeliveryPeriod(2026, 12), 30.0, 10_000.0, counterparty="ACME")),
    npv=120_000.0, delta={("TTF", DeliveryPeriod(2026, 12)): 10_000.0})
beta = PricedPosition(
    position=Position(ForwardContract(ttf, DeliveryPeriod(2027, 3), 28.0, 8_000.0, counterparty="BETA")),
    npv=80_000.0, delta={("TTF", DeliveryPeriod(2027, 3)): 8_000.0})
result = credit_var(
    [acme, beta],
    transition={"ACME": [0.95, 0.05], "BETA": [0.90, 0.10]},   # each row's last state = default
    recovery=0.4, seed=0, path_count=100_000, asset_correlation=0.3)
print(f"ECL {result.expected_credit_loss:,.0f}  VaR95 {result.credit_var_95:,.0f}  "
      f"VaR99 {result.credit_var_99:,.0f}")
# ECL 8,432  VaR95 49,200  VaR99 120,000
```

Exposure-at-default is netted per counterparty and floored at zero (`EAD = max(net exposure, 0)`);
loss-given-default is `1 - recovery`. Expected loss is invariant to `asset_correlation`; only the
tail quantiles respond to it.

## `quantvolt.hedging` — incomplete-market hedging

Hedge ratios for positions whose risk is only partially spanned by traded instruments (Chapter 10).
The unhedgeable component has no market price of risk, so where a risk adjustment is needed these
kernels require an **explicit corporate** one (`PriceOfRiskKind.CORPORATE`) rather than silently
assuming risk-neutrality.

**Public names** (top-level facade): `variance_min_hedge`, `linear_cross_hedge`. On the sub-package
(`quantvolt.hedging`): `variance_min_hedge`, `linear_cross_hedge`, `decomposed_delta` ·
`local_mean_variance`, `global_mean_variance` · `hybrid_deltas`, `residual_variance`

```python
import numpy as np
from quantvolt import linear_cross_hedge, variance_min_hedge
from quantvolt.hedging import global_mean_variance, local_mean_variance
from quantvolt.hedging.hybrid import hybrid_deltas

# One-instrument cross-commodity hedge: hedge power with gas, ratio rho*sigma_t/sigma_h (eq 10.22).
ratio = linear_cross_hedge(rho=0.7, sigma_target=0.60, sigma_hedge=0.45)

# Multi-instrument variance-minimizing hedge h* = Σ_hh⁻¹ Σ_ht (a singular Σ_hh raises, no pseudo-inverse).
sigma_hh = np.array([[0.040, 0.010], [0.010, 0.030]])
sigma_ht = np.array([0.018, 0.009])
h_star = variance_min_hedge(sigma_hh, sigma_ht)

# Local vs global mean-variance over 3 rebalancing periods; diagonal inputs -> the two agree.
cov_hedge = np.diag([0.03, 0.03, 0.03])            # C[s,t] = Cov(ΔH_s, ΔH_t)
cov_target_hedge = np.diag([0.012, 0.012, 0.012])  # M[s,t] = Cov(ΔV_s, ΔH_t)
g_local = local_mean_variance(cov_target_hedge, cov_hedge)
g_global = global_mean_variance(cov_target_hedge, cov_hedge)

# Hybrid structural model: chain-rule deltas of a deterministic bid stack to each tradable driver.
deltas = hybrid_deltas(lambda d: d["power_base"] + 2.0 * d["gas"],
                       {"power_base": 40.0, "gas": 25.0}, bump=1e-3)
print(round(ratio, 3), np.round(h_star, 3))          # 0.933 [0.409 0.164]
print(np.round(g_local, 3), np.round(g_global, 3))   # [0.4 0.4 0.4] [0.4 0.4 0.4]
print({k: round(v, 3) for k, v in deltas.items()})   # {'power_base': 1.0, 'gas': 2.0}
```

`local_mean_variance` reads only the per-period diagonals and always exists; `global_mean_variance`
minimises the whole-horizon variance and needs `cov_hedge` invertible. The two coincide when both
matrices are diagonal (uncorrelated increments) — in particular for a linear product, where both
reduce to `rho*sigma_target/sigma_hedge`. `residual_variance` scores a hybrid representation's
unhedgeable residual (smaller is a better hedge), and `decomposed_delta` computes the
incomplete-market delta with an explicit corporate basis expectation.

## `quantvolt.assets` — dispatch, storage and long-dated valuation

Physical-asset optimization: thermal-generation dispatch, gas storage, and long-dated valuation
governance. Perfect-foresight dispatch is the upper bound every non-anticipating policy is measured
against (`dispatch_value <= dispatch_deterministic`).

**Public names** (top-level facade): `PlantModel`, `dispatch_deterministic`, `dispatch_value`,
`StorageModel`, `storage_intrinsic`, `storage_value`, `valuation_benchmark`, `var_applicability_guard`.
On `quantvolt.assets` additionally: `StartCost`, `StartState`, `DispatchSchedule` · `bang_bang`,
`time_aggregate`, `horizon_divide`, `BangBangHedgeWarning` · `DispatchFactorModel`, `DispatchResult`,
`PeakKind` · `StorageFactorModel`, `IntrinsicResult`, `StorageValueResult` · `CorporatePremium`,
`BenchmarkResult`, `ValuationSource`, `furthest_forward_lower_bound`

Perfect-foresight dispatch (exact backward-induction DP over the commitment/output state machine):

```python
import warnings
from quantvolt.assets import PlantModel, StartCost, StartState, bang_bang, dispatch_deterministic

plant = PlantModel(
    heat_rate=lambda q, temp: 2.0,               # constant marginal heat rate (MWh_fuel/MWh_power)
    c_min=50.0, c_max=lambda temp: 150.0, variable_om_cost=3.0,
    start_costs={s: StartCost(fixed=0.0, fuel=0.0, power=0.0) for s in StartState},
    ramp_rate=100.0, d_min=1, d_shutdown=1, d_startup=0,
    outage_rate=0.0, hot_max_downtime=2, warm_max_downtime=6,
)
power = [90.0, 40.0, 120.0, 20.0]                # EUR/MWh (may be negative)
fuel = [30.0, 30.0, 30.0, 30.0]
temps = [10.0, 10.0, 10.0, 10.0]

sched = dispatch_deterministic(plant, power, fuel, temps)
print(sched.total_value, sched.online)           # 8750.0 (True, True, True, False)

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    bang_bang(plant, power, fuel, temps)          # {0, c_max} state aggregation
print([w.category.__name__ for w in caught])      # ['BangBangHedgeWarning']
```

The schedule stays online through the low-price hour so it is already ramped for the later price
spike — the kind of intertemporal trade-off the DP captures. `time_aggregate`, `horizon_divide`
and `bang_bang` are the three caller-selectable approximations of Req 21.3; `bang_bang` emits a
`BangBangHedgeWarning` because collapsing the output grid distorts hedge sensitivities far more than
the value itself.

Stochastic dispatch values the plant under simulated risk-adjusted prices (`method="lsm"` or
`"tree"`). The drift must be the **risk-neutral** pricing drift — a physical drift is rejected
(the mirror of the VaR guard):

```python
import numpy as np
from quantvolt.assets import PlantModel, StartCost, StartState, dispatch_value
from quantvolt.assets.dispatch_sdp import DispatchFactorModel, PeakKind
from quantvolt.numerics import DriftKind, build_covariance

plant = PlantModel(
    heat_rate=lambda q, temp: 2.0, c_min=50.0, c_max=lambda temp: 150.0, variable_om_cost=3.0,
    start_costs={s: StartCost(0.0, 0.0, 0.0) for s in StartState},
    ramp_rate=100.0, d_min=1, d_shutdown=1, d_startup=0,
    outage_rate=0.0, hot_max_downtime=2, warm_max_downtime=6,
)
sigma = np.array([0.5, 0.5, 0.3])                # power on-peak, power off-peak, gas
corr = np.array([[1.0, 0.8, 0.4], [0.8, 1.0, 0.4], [0.4, 0.4, 1.0]])
cov = build_covariance(sigma, corr, dt=1 / 365)
fm = DispatchFactorModel(
    log_forward0=np.log([90.0, 70.0, 30.0]),
    drift=-0.5 * np.diag(cov),                    # risk-neutral (martingale) drift
    covariance=cov, drift_kind=DriftKind.RISK_NEUTRAL,     # required; a PHYSICAL drift raises
    peak_kinds=(PeakKind.ON_PEAK, PeakKind.OFF_PEAK, PeakKind.ON_PEAK, PeakKind.OFF_PEAK),
    temperatures=(10.0, 10.0, 10.0, 10.0),
)
result = dispatch_value(plant, fm, method="lsm", seed=7, path_count=4096)
print(round(result.value))                        # 7501  (<= perfect-foresight 8750, Property 62)
```

The on-peak/off-peak split (two power coordinates plus a per-period peak label) restores the Markov
property an hourly power sequence lacks. `DispatchResult` also carries the four critical-exercise
spark-spread surfaces (start-up / shutdown / ramp-up / ramp-down); an optional per-period
`availability` multiplier derates capacity for forced outages — sourced, e.g., from
`OutageDataset.forced_outage_multiplier` (below).

Gas storage as injection/withdrawal optionality against the term structure — intrinsic
(forward-locked) plus extrinsic (re-optimisation) value via Least-Squares Monte Carlo:

```python
from datetime import date
from quantvolt import BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, ForwardCurve
from quantvolt.assets import StorageModel, storage_intrinsic, storage_value
from quantvolt.assets.storage import StorageFactorModel

ttf = BUILT_IN_COMMODITIES["TTF"]
curve = ForwardCurve(ttf, date(2026, 7, 15), tuple(
    CurveNode(DeliveryPeriod(2026, m), p, "observed")
    for m, p in zip(range(8, 13), [25.0, 27.0, 32.0, 37.0, 40.0])))   # summer-low, winter-high
store = StorageModel(
    min_inventory=0.0, max_inventory=100.0, initial_inventory=0.0, terminal_inventory=0.0,
    injection_rate=lambda inv: 40.0, withdrawal_rate=lambda inv: 40.0,   # ratchets (per period)
)
intrinsic = storage_intrinsic(store, curve, inventory_step=20.0)
factor = StorageFactorModel(volatility=0.5, dt=1 / 12, path_count=4000)
total = storage_value(store, curve, factor, seed=7, inventory_step=20.0)
print(f"intrinsic {intrinsic.value:.0f}  total {total.total:.0f}  "
      f"extrinsic {total.extrinsic:.1f} (se {total.standard_error:.2f})")
# intrinsic 1000  total 1000  extrinsic -0.0 (se 0.00)
```

The intrinsic value locks in the summer-buy / winter-sell calendar spread. The shipped
single-factor `StorageFactorModel` moves the whole curve together, so for a monotonic seasonal curve
the extrinsic (timing) value is ~0; it is reported honestly with its Monte-Carlo standard error
(Property 64: `extrinsic >= 0`, never clamped) and appears once spot can deviate from the forward
ordering. `total == intrinsic + extrinsic` by construction.

Long-dated valuation governance keeps forward-covered and projected-spot values strictly separated
so long-dated risk is never understated:

```python
from datetime import date
from quantvolt import (
    BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, ForwardCurve, FuturesContract,
    Position, PricedPosition,
)
from quantvolt.assets import valuation_benchmark, var_applicability_guard
from quantvolt.assets.long_dated import CorporatePremium
from quantvolt.numerics import PriceOfRiskKind

ttf = BUILT_IN_COMMODITIES["TTF"]
curve = ForwardCurve(ttf, date(2026, 7, 15), (CurveNode(DeliveryPeriod(2026, 12), 38.0, "observed"),))
premium = CorporatePremium(premium=4.0, kind=PriceOfRiskKind.CORPORATE)   # a market-tagged one raises

liquid = valuation_benchmark(DeliveryPeriod(2026, 12), curve, lambda p: 42.0, premium)   # forward
far = valuation_benchmark(DeliveryPeriod(2030, 12), curve, lambda p: 42.0, premium)       # projected
print(liquid.source, liquid.value, "|", far.source, far.value)   # forward 38.0 | projected 46.0

projected = PricedPosition(
    position=Position(FuturesContract(ttf, DeliveryPeriod(2030, 12), 40.0, 1_000.0), tags=(far.source,)),
    npv=42_000.0, delta={("TTF", DeliveryPeriod(2030, 12)): 1_000.0})
print(var_applicability_guard(projected).applicable)             # False (projected-spot -> use CFaR)
```

Where the liquid curve covers the period the forward price is the benchmark; beyond it the value is
projected from a spot model plus the (required, corporate) premium and tagged `PROJECTED`.
`var_applicability_guard` then flags short-horizon VaR as inapplicable for a projected-valued
position — VaR is meaningful only in liquid markets. `furthest_forward_lower_bound` offers the
cash-and-carry lower bound for storable commodities and refuses it for power.

## `quantvolt.curvemodels` — Schwartz-Smith and multifactor forward models

Stochastic forward-curve models. The two-factor Schwartz-Smith model splits log spot into a
short-term mean-reverting deviation and a long-term random walk; the multifactor model is the
risk-neutral lognormal `dF/F = Σ_k σ_k dW_k` whose integrated form matches the initial curve by
construction. Both are lognormal — **not** automatically appropriate for spiky/negative power.

**Public names** (top-level facade): `SchwartzSmithParams`, `MultifactorForwardModel`. On
`quantvolt.curvemodels`: `SchwartzSmithParams`, `forward_curve`, `log_forward_curve`, `simulate`,
`calibrate`, `CalibrationDiagnostics` · `MultifactorForwardModel`, `induced_covariance`,
`induced_correlation`, `cumulative_covariance`, `option_variance`, `risk_neutral_drift`, `mc_inputs`,
`simulate_forwards`, `warn_if_power_like`, `LognormalPowerWarning` (+ the matching-condition checks)

```python
import numpy as np
from quantvolt.curvemodels import SchwartzSmithParams, forward_curve

params = SchwartzSmithParams(kappa=1.2, sigma_chi=0.30, sigma_xi=0.15, mu_xi=0.0,
                             rho=-0.3, lambda_chi=0.0, lambda_xi=0.02)
tenors = np.array([0.25, 0.5, 1.0, 2.0, 5.0])          # maturities T (years)
fc = forward_curve(params, chi=0.10, xi=float(np.log(30.0)), t=0.0, tenors=tenors)
print(np.round(fc, 2), "mu_xi* =", params.mu_xi_star)
# [32.42 31.81 30.93 30.   28.94] mu_xi* = -0.02
```

`forward_curve` is the §31.2 closed form `F(t,T) = exp[e^(-kappa*tau)*chi + xi + A(tau)]`; as maturity
grows the short-factor loading decays and long-dated forwards depend only on `xi` and `A(tau)`.
`calibrate` fits the parameters by Kalman-filter maximum likelihood and reports the initial-curve
mismatch and identifiability diagnostics rather than hiding them.

The multifactor model's induced structure is fully determined by its factor loadings; the simulated
forwards are a martingale, so the Monte Carlo mean returns the initial curve:

```python
import numpy as np
from quantvolt import MultifactorForwardModel
from quantvolt.curvemodels import forward_matching_residual, induced_correlation, simulate_forwards

target_corr = np.array([[1.0, 0.7, 0.5], [0.7, 1.0, 0.6], [0.5, 0.6, 1.0]])
vols = np.array([0.40, 0.35, 0.30])
model = MultifactorForwardModel.from_target_correlation(target_corr, vols, n_steps=12, dt=1 / 12)
print(np.allclose(induced_correlation(model, 0), target_corr, atol=1e-9))   # True

f0 = np.array([90.0, 70.0, 55.0])
paths = simulate_forwards(model, f0, steps=12, path_count=20_000, seed=3)    # F = exp(Z), record 0 == f0
print(np.round(forward_matching_residual(f0, paths[:, -1, :].mean(axis=0)), 2))   # ~ [0.15 0.13 0.04]
```

Passing `commodity_ids=[...]` to `simulate_forwards` (or calling `warn_if_power_like`) raises a
`LognormalPowerWarning` for any power-like id — the model is not rejected, but the choice is made
deliberate.

## Transmission and pipeline rights

A transport right is the option to move a commodity from a liquid origin hub A to a destination hub B,
exercised period by period only when the locational spread covers the tariff. `TransmissionRight`
(power) and `PipelineRight` (gas) are distinct value objects priced by one engine,
`value_transport_right`.

**Public names** (top-level facade): `TransmissionRight`, `PipelineRight`, `TransportDirection`,
`value_transport_right`, `TransportRightResult`

```python
from datetime import date
from quantvolt import (
    BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, DeliverySchedule, DiscountCurve,
    ForwardCurve, TransmissionRight, TransportDirection, value_transport_right,
)

periods = tuple(DeliveryPeriod(2026, m) for m in (8, 9, 10))

def hub_curve(commodity_id, prices):
    return ForwardCurve(BUILT_IN_COMMODITIES[commodity_id], date(2026, 7, 15),
        tuple(CurveNode(p, v, "observed") for p, v in zip(periods, prices)))

curve_de = hub_curve("EPEX_DE", [80.0, 85.0, 90.0])    # origin hub A
curve_fr = hub_curve("EPEX_FR", [92.0, 88.0, 95.0])    # destination hub B
right = TransmissionRight(origin="EPEX_DE", destination="EPEX_FR", tariff=2.0, quantity=100.0,
                          schedule=DeliverySchedule(periods), direction=TransportDirection.A_TO_B)
disc = DiscountCurve(date(2026, 7, 15), (date(2026, 7, 16), date(2027, 6, 30)), (1.0, 0.97))

intrinsic = value_transport_right(right, curve_de, curve_fr, disc)          # payoff Q*max(P_B - P_A - T, 0)
option = value_transport_right(right, curve_de, curve_fr, disc, vols=(0.40, 0.45), correlation=0.6)
print(round(intrinsic.total, 1), round(option.extrinsic, 1))                # 1392.6 1309.2
```

Supplying `vols` and `correlation` (both or neither) adds each period's spread-option extrinsic value
via the Kirk/Margrabe engine — which requires strictly positive location forwards; the intrinsic path
handles negative prices. A `BIDIRECTIONAL` right commits each period to the best of A→B, B→A or
no-flow and is subadditive versus two one-way rights (Property 68). The holder is long the sink hub
and short the source hub, so `delta_origin` and `delta_destination` always carry opposite signs.

## `quantvolt.stats` — statistics for energy price series

Price-series diagnostics on Polars inputs, aware of the non-stationarity of futures sampling.

**Public names**: `descriptive_stats`, `moments`, `DescriptiveStats` · `test_normality`,
`NormalityTestType`, `NormalityTestResult` · `test_stationarity`, `StationarityResult` ·
`correlation_matrix`, `rolling_correlation` · `fit_ou`, `MeanReversionParams`

```python
from datetime import date, timedelta

import numpy as np
import polars as pl

from quantvolt.stats import descriptive_stats, fit_ou, test_normality, test_stationarity

rng = np.random.default_rng(0)
prices = pl.Series("ttf", 35 + np.cumsum(rng.normal(0, 0.8, 300)))

stats = descriptive_stats(prices)                        # mean, std, skew, kurtosis, t-stat
normality = test_normality(prices.diff().drop_nulls())   # Jarque-Bera by default
ou = fit_ou(prices)                                      # Ornstein-Uhlenbeck: speed, half-life
dates = [date(2025, 6, 2) + timedelta(days=i) for i in range(300)]
stationarity = test_stationarity(prices, contract_expiry=date(2026, 4, 1),
                                 observation_dates=dates)
print(normality.is_normal, round(ou.half_life, 1),
      stationarity.is_stationary, stationarity.samuelson_effect_detected)
```

`test_stationarity` combines ADF and KPSS (both must agree) and separately flags the Samuelson
effect — return volatility rising as the contract approaches expiry — from the observation
dates relative to expiry. `test_normality` offers Jarque-Bera, Shapiro-Wilk,
D'Agostino-Pearson, and Anderson-Darling via `NormalityTestType`.

## `quantvolt.market` — transmission, weather and outages

Supporting domain data: pipeline transmission cost, temperature/degree-day utilities, and
generation outage / reliability KPIs.

**Public names**: `Pipeline`, `transmission_cost` · `TemperatureData`, `degree_days` ·
`OutageDataset`, `OutageRecord`, `OutageType`, `OutageStatus`, `availability_factor`,
`equivalent_availability_factor`, `forced_outage_rate`, `efor`, `mttr`, `mtbf`,
`outage_frequency`, `unavailable_energy`

```python
from datetime import date

import polars as pl

from quantvolt.market import Pipeline, degree_days, transmission_cost

cost = transmission_cost(Pipeline(distance=120.0, tariff=0.02), volume=10_000.0)

temps = pl.DataFrame({
    "location": ["Amsterdam", "Amsterdam"],
    "date": [date(2026, 1, 5), date(2026, 1, 6)],
    "temp_celsius": [2.5, -1.0],
})
print(cost, degree_days(temps, base_celsius=18.0))  # adds hdd / cdd columns
```

The `[location, date, temp_celsius]` frame shape is exactly what
`quantvolt.data.OpenMeteoSource.temperatures` returns, so fetched and caller-supplied weather
data are interchangeable.

Reliability KPIs run over a caller-supplied `OutageDataset` of validated `OutageRecord`s. Outage
categories (`PLANNED`, `FORCED`, `UNPLANNED`, `MAINTENANCE`, `SERVICE`) stay distinct — a planned
outage never contributes to `forced_outage_rate`. The headline `AF`/`EAF`/`FOR` follow the polished
spec §22; `efor`/`mttr`/`mtbf`/`outage_frequency`/`unavailable_energy` follow IEEE Std 762:

```python
from datetime import datetime
from quantvolt.market import (
    OutageDataset, OutageRecord, OutageStatus, OutageType,
    availability_factor, forced_outage_rate, unavailable_energy,
)

record = OutageRecord(
    asset_id="A1", unit_id="U1", technology="ccgt", market_zone="DE", outage_id="O1",
    outage_type=OutageType.FORCED, status=OutageStatus.COMPLETED,
    announcement_time=datetime(2026, 1, 1), start_time=datetime(2026, 1, 10),
    expected_end_time=datetime(2026, 1, 12), actual_end_time=datetime(2026, 1, 12),
    installed_capacity_mw=400.0, unavailable_capacity_mw=400.0, available_capacity_mw=0.0,
    source="TSO", revision_number=0,
)
dataset = OutageDataset(records=(record,))
hours = 24 * 31
print(f"AF {availability_factor(dataset, hours):.4f}  FOR {forced_outage_rate(dataset):.2f}  "
      f"unavailable {unavailable_energy(dataset):,.0f} MWh")           # AF 0.9355  FOR 1.00  19,200 MWh
m = dataset.forced_outage_multiplier(period_hours=hours, installed_capacity_mw=400.0)
print(f"forced-outage multiplier M {m:.4f}")                          # 0.9355
```

`OutageDataset.forced_outage_multiplier` is the dispatch seam: its `M ∈ [0, 1]` feeds
`dispatch_value(..., availability=[M, ...])` (above) to derate `c_max` for forced outages, mapping to
the plant's stochastic forced-outage rate `λ`.

## `quantvolt.workflow` — 7-step model selection

A Template Method skeleton of the model-selection discipline for structured products:
qualitative analysis → static hedges → residual investigation → residual model → data check →
consistency check → price and hedge. The default steps are deterministic, pure functions;
inject your own via `WorkflowSteps` to plug in real fitting and pricing.

**Public names**: `ModelingWorkflow`, `WorkflowSteps`, `WorkflowResult`, `DEFAULT_STEPS`,
`ModelSelectionCriteria` · `StructuredProduct`, `QualitativeAnalysis`, `StaticHedge`,
`ResidualAnalysis`, `ResidualModel`, `DataSufficiencyReport`, `ConsistencyReport`

```python
from quantvolt.workflow import ModelingWorkflow, ModelSelectionCriteria, StructuredProduct

product = StructuredProduct(
    name="gas-fired PPA",
    payoff_description="monthly strip of spark-spread options",
    risk_factors=("price:power", "price:gas", "volatility:spark_spread"),
)
result = ModelingWorkflow().run(product, criteria=ModelSelectionCriteria(min_r_squared=0.6))
print(result.steps_executed, result.risk_factor_separation_achieved,
      [h.instrument_kind for h in result.hedges])
# (1, 2, 3, 4, 5, 6, 7) True ['power_forward', 'gas_forward']
```

Risk factors are `"category:detail"` strings; `price:`/`fx:`/`rate:` categories are
model-independent (statically hedgeable), everything else is modelled residual risk.

## `quantvolt.portfolio` — book assembly and valuation

Compose forwards, futures, and swaps into a `Portfolio` and value it as a whole; per-position
results feed `RiskEngine` and `mark_to_market` directly.

**Public names**: `Portfolio`, `Position`, `PricedPosition`, `Instrument` · `MarketData`,
`PortfolioValuation`, `value_portfolio`

```python
from datetime import date

from quantvolt import (
    BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, DiscountCurve, ForwardContract,
    ForwardCurve, FuturesContract, MarketData, Portfolio, Position, value_portfolio,
)

ttf = BUILT_IN_COMMODITIES["TTF"]
period = DeliveryPeriod(2026, 12)
curve = ForwardCurve(ttf, date(2026, 7, 15), (CurveNode(period, 36.85, "observed"),))
market = MarketData(
    forward_curves={"TTF": curve},
    discount_curve=DiscountCurve(date(2026, 7, 15), (date(2026, 7, 16), date(2027, 6, 30)), (1.0, 0.97)),
    valuation_date=date(2026, 7, 15),
)

book = Portfolio(
    name="ttf-winter-book",   # optional portfolio name
    positions=(
        Position(FuturesContract(ttf, period, contract_price=35.0, notional=5_000.0),
                 position_id="fut-1"),
        Position(ForwardContract(ttf, period, contract_price=39.0, notional=2_000.0),
                 tags=("hedge",)),
    ),
)
valuation = value_portfolio(book, market)
print(f"{book.name}: total NPV {valuation.total_npv:,.0f} EUR over {len(valuation.priced)} positions")
print(valuation.priced[0].delta)  # {(commodity_id, period): delta} — feeds RiskEngine
```

`Portfolio` carries an optional `name`, and each `Position` an optional `position_id` and
`tags` (the tags are also where long-dated valuation provenance travels — see
[risk-and-assets.md](risk-and-assets.md)). Valuation dispatches on instrument type
(futures/forwards via `price_futures`, swaps via `price_swap`, transmission/pipeline rights via
`value_transport_right`); pass a `pricers` mapping to override or extend the dispatch for your own
instrument types. Positions that cannot be priced are returned in `valuation.unpriced`, never
silently dropped.

Options are not a built-in portfolio instrument type; the `pricers` seam is the supported way to
hold a book of them — define your own frozen instrument type and register a pricer that wraps
`price_vanilla_option` (or any pricer returning a `PricedPosition`):

```python
from dataclasses import dataclass
from datetime import date

from quantvolt import (
    BUILT_IN_COMMODITIES, CurveNode, DeliveryPeriod, DiscountCurve, ForwardCurve,
    MarketData, Portfolio, Position, PricedPosition, VanillaOptionRequest,
    price_vanilla_option, value_portfolio,
)

@dataclass(frozen=True, slots=True)
class VanillaOptionPosition:            # caller-defined instrument type
    commodity_id: str
    period: DeliveryPeriod
    option_type: str                    # "call" or "put"
    strike: float
    notional: float
    sigma: float
    time_to_expiry: float

def price_option_position(position, market_data):
    opt = position.instrument
    forward = market_data.curve_for(opt.commodity_id).price_at(opt.period)
    df = market_data.discount_curve.discount_factor(opt.period.last_day)
    result = price_vanilla_option(VanillaOptionRequest(
        option_type=opt.option_type, strike=opt.strike, notional=opt.notional,
        forward=forward, sigma=opt.sigma, time_to_expiry=opt.time_to_expiry,
        discount_factor=df))
    return PricedPosition(position=position, npv=result.premium,
                          delta={(opt.commodity_id, opt.period): result.greeks.delta},
                          greeks=result.greeks)

ttf = BUILT_IN_COMMODITIES["TTF"]
period = DeliveryPeriod(2026, 12)
market = MarketData(
    {"TTF": ForwardCurve(ttf, date(2026, 7, 15), (CurveNode(period, 36.85, "observed"),))},
    DiscountCurve(date(2026, 7, 15), (date(2026, 7, 16), date(2027, 6, 30)), (1.0, 0.97)),
    date(2026, 7, 15),
)
book = Portfolio(name="ttf-vol-book", positions=(
    Position(VanillaOptionPosition("TTF", period, "call", 38.0, 10_000.0, 0.55, 0.4), position_id="opt-1"),
    Position(VanillaOptionPosition("TTF", period, "put", 33.0, 10_000.0, 0.55, 0.4), position_id="opt-2"),
))
valuation = value_portfolio(book, market, pricers={VanillaOptionPosition: price_option_position})
print(f"{book.name}: NPV {valuation.total_npv:,.0f} EUR over {len(valuation.priced)} options")
# ttf-vol-book: NPV 76,358 EUR over 2 options
```

The resulting `PricedPosition`s carry option deltas keyed by `(commodity_id, period)`, so the
options book flows into `RiskEngine.compute_risk`, `apply_scenario`, and `credit_var` exactly like
futures and swaps.

## `quantvolt.data` — optional provider adapters (`quantvolt[data]`)

The optional imperative shell and the only package that performs I/O; the analytics core never
imports it. Adapters implement the `DataSource` protocol and return the same value objects the
core consumes. Free adapters — `EntsoeSource` (day-ahead power prices, load, generation),
`EntsogSource` (gas flows), `OpenMeteoSource` (temperatures) — deliberately expose **no**
`forward_curve` method: forward/futures curves come only from commercial providers
(`EexSource`, `EpexSource`, `IceSource`, `NordPoolSource`, `LsegSource` — stubs that raise
until you configure a commercial licence) or from caller-supplied data.

**Public names**: `Credentials`, `DataSource`, `snapshot`, `restore` · `EntsoeSource`,
`EntsogSource`, `OpenMeteoSource` · `EexSource`, `EpexSource`, `IceSource`, `NordPoolSource`,
`LsegSource` · `DataSourceError`, `AuthenticationError`, `RateLimitError`, `DataUnavailableError`

Credentials are caller-owned: an explicit `Credentials(token=...)` wins, otherwise the
documented `QUANTVOLT_<PROVIDER>_TOKEN` environment variable is read (e.g.
`QUANTVOLT_ENTSOE_TOKEN`). They are never persisted or logged, and every string representation
redacts them. Adapters accept an `httpx` transport for testing — no live calls needed:

```python
from datetime import date

import httpx

from quantvolt import BUILT_IN_COMMODITIES
from quantvolt.data import Credentials, EntsoeSource

# Explicit credentials win; otherwise QUANTVOLT_ENTSOE_TOKEN is read from the environment.
credentials = Credentials(token="<your-entsoe-token>")   # placeholder, not a real token
print(credentials)                                       # Credentials(***) — always redacted

xml = b"""<Publication_MarketDocument>
  <TimeSeries><Period>
    <Point><position>1</position><price.amount>82.4</price.amount></Point>
    <Point><position>2</position><price.amount>-5.1</price.amount></Point>
  </Period></TimeSeries>
</Publication_MarketDocument>"""
transport = httpx.MockTransport(lambda request: httpx.Response(200, content=xml))

source = EntsoeSource(credentials=credentials, transport=transport)  # transport=None -> live HTTPS
prices = source.price_series(BUILT_IN_COMMODITIES["EPEX_DE"], date(2026, 7, 1), date(2026, 7, 2))
print(prices.to_list())  # [82.4, -5.1] — a pl.Series the core consumes directly
```

Provider HTTP failures map onto the library hierarchy (`AuthenticationError` for 401/403 —
naming the env var, never the credential — `RateLimitError` for 429, `DataUnavailableError`
when the provider has no data). `snapshot(obj)`/`restore(data)` serialise fetched value
objects so a live fetch can be replayed deterministically later.

## `quantvolt.testing` — shipped test utility

**Public names**: `assert_input_unchanged`

Wrap any library (or your own) function to prove it does not mutate its arguments, while still
receiving the return value. Handles NumPy arrays and Polars Series/DataFrames, not just
built-in containers.

```python
import polars as pl

from quantvolt.stats import descriptive_stats
from quantvolt.testing import assert_input_unchanged

prices = pl.Series("ttf", [30.1, 30.9, 29.8, 31.2])
stats = assert_input_unchanged(descriptive_stats, prices)  # AssertionError if `prices` mutated
print(stats.n)  # 4 — the wrapped function's result is passed through
```
