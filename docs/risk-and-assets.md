# Risk management and asset optimization

How `quantvolt` measures risk and values physical assets, and the disciplines it enforces so
that risk is neither overstated nor understated. This is the conceptual companion to the API
reference: for runnable per-function examples see [api.md](api.md). Everything below is a
property of *this* codebase and names the module or function that implements it.

## The VaR family

The library ships three market-VaR methods plus two non-market risk measures. They differ in
what they assume, what they cost, and when to reach for them. All are **loss** measures with the
house sign convention `loss = -ΔP&L`, and VaR at confidence `c` is the `c`-quantile of the loss.

| Method | Function | Assumptions | Cost | When to use |
|---|---|---|---|---|
| Historical simulation | `RiskEngine.compute_risk` | Empirical scenario matrix; delta-linear P&L (`ΔP = δ·shock`) | Cheap: one matrix multiply | A liquid, roughly linear book with a usable scenario history |
| Parametric (delta / delta-gamma) | `parametric_var`, `delta_gamma_var` | `Δf ~ N(0, Σ)`; local delta (and gamma) sensitivities; no revaluation | Cheapest: analytic, scales to ~2000 factors inside 2 s | Large, mildly non-linear books where full revaluation is too slow |
| Monte Carlo (full revaluation) | `monte_carlo_var` | Correlated GBM forwards; **full** repricing on every path | Most expensive: revalues the book per path | Materially non-linear books (options, tolling, storage) whose tails a linear VaR misstates |
| Cash-Flow-at-Risk | `cash_flow_at_risk` | Exhaustive market **and** operational scenario set; caller's pure cash-flow model | Moderate | Multi-period *earnings / liquidity* shortfall, not mark-to-market |
| Credit VaR | `credit_var` | One-factor Gaussian copula; default-only loss (`EAD`/`LGD`) | Moderate (Monte Carlo over defaults) | Counterparty-default loss on the book |

Parametric VaR understates tail risk for fat-tailed energy factors (the normality assumption);
`delta_gamma_var` adds a Cornish-Fisher skewness correction from the gamma matrix but is reliable
only for moderate skew. Monte Carlo VaR reports a nonparametric **bootstrap standard error** per
quantile (`var_95_se`, …) that shrinks as `path_count` grows; it requires `path_count >= 1000` and
strictly positive current forwards (GBM). Covariance forecasts for the parametric path come from
`ewma_covariance` (RiskMetrics) or `garch11_covariance` (diagonal GARCH + constant conditional
correlation); both return a symmetric positive-semidefinite matrix, and `nearest_psd` repairs a
marginally indefinite one.

## Probability measure: physical *P* vs risk-neutral *Q*

The single most important discipline in this pillar is that the probability measure is explicit
and machine-checked, never inferred. `numerics.risk_adjustment.DriftKind` tags every drift as
`PHYSICAL` (real-world *P*) or `RISK_NEUTRAL` (arbitrage-free *Q*), and the two regimes use them in
opposite directions:

- **Valuation is under *Q*.** `dispatch_value` and the forward-curve models price under the
  risk-adjusted expectation. The caller forms the risk-adjusted drift `mu* = mu - lambda_S·sigma`
  (`risk_adjusted_drift`, eq 10.5) — for a fully tradable factor this collapses to the risk-neutral
  `r - y` — and tags it `RISK_NEUTRAL`. `dispatch_value` **rejects** a `PHYSICAL` drift: valuing a
  not-fully-hedgeable asset under the real-world measure would overstate its value.
- **Risk measurement is under *P*.** `monte_carlo_var` requires a `PHYSICAL`-tagged
  `TaggedDrift` and rejects a `RISK_NEUTRAL` one via `require_physical_drift` before any simulation;
  real-world loss must evolve under *P*. `parametric_var` / `delta_gamma_var` take a physical
  covariance forecast, and `cash_flow_at_risk` consumes already-realised physical scenarios.

```python
from quantvolt.exceptions import ValidationError
from quantvolt.numerics import DriftKind, require_physical_drift, risk_adjusted_drift

mu_star = risk_adjusted_drift(mu=0.08, lambda_s=0.5, sigma=0.2)   # Q-measure drift: 0.08 - 0.5*0.2
require_physical_drift(DriftKind.PHYSICAL)                        # VaR path: silent, accepted
try:
    require_physical_drift(DriftKind.RISK_NEUTRAL, "physical_drift")   # a Q drift for VaR
except ValidationError:
    print("risk-neutral drift rejected for VaR")
print("mu* =", round(mu_star, 3))                                # mu* = -0.02
```

## Price of risk: market vs corporate

`numerics.risk_adjustment.PriceOfRiskKind` tags where a price of risk `lambda` comes from —
`MARKET` (implied from liquidly traded derivatives) or `CORPORATE` (the firm's own risk policy).
The two produce identical adjustment arithmetic (`price_of_risk`, `tradable_price_of_risk`,
`risk_adjusted_drift`) but are not interchangeable: an unhedgeable exposure has no market price of
risk to imply, so anything that adjusts one requires an **explicit corporate** kind. This is
enforced, not documented-and-hoped: `hedging.decomposed_delta` and the long-dated
`CorporatePremium` both reject a `MARKET`-tagged (or untagged) input rather than silently assuming
risk-neutrality.

## VaR only in liquid markets

VaR is meaningful only where positions can actually be marked and liquidated. Long tenors run past
the liquid forward curve, and a value projected from a spot model plus a corporate premium carries
far more risk than a forward-covered one — so the library keeps the two regimes tagged apart.
`valuation_benchmark` returns a `ValuationSource.FORWARD` value where the curve is liquid and a
`ValuationSource.PROJECTED` value beyond it; the caller propagates that tag onto the `Position`, and
`var_applicability_guard` then flags short-horizon VaR as **inapplicable** for a projected-valued
position (returning `applicable=False`, or raising with `strict=True`), steering it to CFaR or
scenario analysis instead. (`ValuationSource` gained a third value, `SIMULATED`, for the DEFERRED-
roadmap `CachedAssetValuation` portfolio wrapper — see `docs/api.md`'s portfolio section; this
module still produces only `FORWARD`/`PROJECTED` itself.)

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
far = valuation_benchmark(DeliveryPeriod(2031, 12), curve, lambda p: 45.0,
                          CorporatePremium(premium=5.0, kind=PriceOfRiskKind.CORPORATE))
pos = PricedPosition(
    position=Position(FuturesContract(ttf, DeliveryPeriod(2031, 12), 40.0, 1_000.0), tags=(far.source,)),
    npv=50_000.0, delta={("TTF", DeliveryPeriod(2031, 12)): 1_000.0})
print(far.source, "->", var_applicability_guard(pos).applicable)   # projected -> False
```

`furthest_forward_lower_bound` applies the cash-and-carry "furthest liquid forward bounds later
tenors" argument only for a caller-declared **storable** commodity, and refuses it for non-storable
power — non-storability breaks the carry argument.

## Incomplete-market hedging

When a position's risk is only partly spanned by traded instruments (`quantvolt.hedging`), the
hedge is a statistical projection, not a replication. `variance_min_hedge` solves the
variance-minimizing normal equations `h* = Σ_hh⁻¹ Σ_ht`, raising on a singular `Σ_hh` rather than
returning a meaningless pseudo-inverse; `linear_cross_hedge` is its one-instrument special case
`rho·sigma_t/sigma_h` (eq 10.22). Dynamic hedging offers two objectives: `local_mean_variance`
(the default) minimises each rebalancing period's one-step variance and always exists, while
`global_mean_variance` minimises the whole-horizon variance and needs an invertible hedge
covariance. The two coincide exactly when increments are uncorrelated across periods — in
particular for a linear product, where both equal `rho·sigma_target/sigma_hedge`.

For a hybrid (structural) power model `p = s^bid(drivers) + epsilon`, `hybrid_deltas` returns the
chain-rule sensitivities of the deterministic bid stack to each tradable driver, and
`residual_variance` scores the unhedgeable residual `epsilon` — **smaller is a better hedge**. The
residual's expectation, where valuation needs it, again requires an explicit corporate risk
adjustment (`decomposed_delta`), never a silent risk-neutral one.

## Dispatch and storage

Physical-asset value is bounded and staged. `dispatch_deterministic` solves the perfect-foresight
optimum (Appendix B eq. B.1) by exact backward-induction DP over the commitment/output state
machine; because it optimises the fully known path it is the **upper bound** any non-anticipating
policy is tested against — `dispatch_value <= dispatch_deterministic`.
`dispatch_value` computes the risk-adjusted expected value by stochastic DP (`method="lsm"` or
`"tree"`), carrying the on-peak/off-peak Markov split (two power coordinates) that an hourly power
sequence needs, and returns the four critical-exercise spark-spread surfaces. Three caller-selectable
approximations wrap the deterministic solver — `time_aggregate` (coarser time blocks),
`horizon_divide` (independent sub-horizons), and `bang_bang` (`{0, c_max}` state aggregation).
`bang_bang` emits a `BangBangHedgeWarning`: collapsing the output grid distorts hedge sensitivities
far more than the value, so a hedge read off a bang-bang model can be badly wrong even where the
value is accurate.

Gas storage separates the two value components. `storage_intrinsic` is the forward-locked optimal
injection/withdrawal schedule (exact DP over an inventory grid, subject to bounds, ratchets and the
terminal condition); `storage_value` adds the extrinsic (re-optimisation / timing) value via
Least-Squares Monte Carlo, with `total == intrinsic + extrinsic`. The extrinsic value is
theoretically non-negative and is reported with its Monte-Carlo standard
error rather than clamped — under the shipped single-factor `StorageFactorModel`, which moves the
whole curve together, it is small for a monotonic seasonal curve and grows once spot can deviate
from the forward ordering.

## Forward-curve models: Schwartz-Smith and multifactor

`curvemodels.SchwartzSmithParams` / `forward_curve` implement the two-factor model (short-term
mean-reverting deviation plus long-term random walk) with the §31.2 closed-form curve;
`calibrate` fits it by Kalman-filter maximum likelihood and reports the initial-curve mismatch and
identifiability diagnostics rather than hiding them. `MultifactorForwardModel` implements the
risk-neutral lognormal `dF/F = Σ_k σ_k dW_k`, whose integrated form matches the initial curve by
construction and is a martingale (`E^Q[F(t,T)] = F(0,T)`), so its Monte Carlo mean recovers the
initial curve. Both are **lognormal**: they keep forwards strictly positive and cannot reproduce
the spikes, negative prices, and heavy tails of spot power. Neither is rejected for power, but
`warn_if_power_like` / the `LognormalPowerWarning` (and the Schwartz-Smith `lognormal_power_caveat`)
make the choice deliberate — assess suitability per commodity.

## Outage KPIs feeding dispatch

`market.OutageDataset` computes reliability KPIs over validated `OutageRecord`s, keeping outage
categories (`PLANNED`, `FORCED`, `UNPLANNED`, `MAINTENANCE`, `SERVICE`) strictly distinct — a
planned outage never contributes to `forced_outage_rate`. The headline availability factors follow
the polished spec §22; the rest (`efor`, `mttr`, `mtbf`, `outage_frequency`, `unavailable_energy`)
follow IEEE Std 762. The connection to valuation is `OutageDataset.forced_outage_multiplier`, which
returns the forced-outage available-capacity fraction `M ∈ [0, 1]` for a period; that value feeds
`dispatch_value(..., availability=[M, ...])` to derate `c_max`, mapping to the plant's stochastic
forced-outage rate `λ`. Only `FORCED` events enter `M`, so scheduled maintenance and other
categories never leak into the stochastic-outage seam.

## Financial-physical risk experiments

A single experiment can use the same forward curves and stochastic factors to value
derivatives, measure portfolio exposure, and value generation or storage decisions under their
actual operating constraints. The probability measure remains explicit: physical dynamics drive
exposure experiments, while risk-adjusted dynamics drive valuation.

For Appendix-A-style simulations whose volatility, correlation, drift, or live-tenor set changes
through time, use `CorrelatedSimulationRequest` with
`quantvolt.numerics.simulate_correlated_term_structure`. Each row supplies one step's drift and
covariance; `active_steps` freezes expired coordinates exactly. The time-homogeneous
`simulate_correlated_forwards` function remains the simpler API for stationary experiments.

Dispatch LSM fits its continuation policy on the requested training paths and evaluates that
fixed policy on a separate scenario set. `DispatchResult.diagnostics` reports the training value,
out-of-sample standard error and confidence interval, sample sizes, and the worst continuation
regression condition number. Pass `MonteCarloEvaluation` to control the independent sample.
`PhysicalFactorMapping` can map additional simulated coordinates into stochastic temperature or
availability, allowing physical conditions to co-evolve with power and fuel prices.
