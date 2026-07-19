# quantvolt

An experimentation library for **energy risk management across financial positions and
physical assets** in European power, gas, and carbon markets. It is a pure-computation Python
library: you supply market assumptions and data as immutable Python objects, run reproducible
pricing, risk, hedging, curve-model, dispatch, and storage experiments, and receive computed
results.
There are no servers, databases, or ingestion pipelines, and the analytics core performs no
I/O. Monte Carlo path simulation runs on native Rust kernels (`quantvolt._core`); an optional
data-adapters layer (`quantvolt[data]`) can fetch spot prices, fundamentals, and weather with
your own provider credentials, but the core never depends on it.

Covered markets: EEX Phelix DE/AT power, EPEX SPOT power (DE, FR, NL, BE, GB), TTF and NBP
natural gas (ICE Endex), and EUA carbon allowances — extensible by the caller without editing
library source. See [docs/european-markets.md](docs/european-markets.md).

## Why QuantVolt?

A typical desk assembles a curve spreadsheet, a standalone options pricer, a storage/dispatch
optimizer and a bolted-on VaR tool, each with its own units, sign conventions and delivery-period
identity — hand-reconciling between them is slow and a recurring source of quiet errors. QuantVolt
instead moves the same immutable `ForwardCurve` / `DeliveryPeriod` / `MarketData` / `Greeks` value
objects through curve construction, pricing, portfolio valuation, risk, realized settlement and
physical-asset valuation, with determinism, eager validation and serializability enforced
structurally rather than left to convention. It is equally explicit about scope: a PPA stays
`unpriced` until you register a forward-looking pricer, storage/dispatch results are brought into
a portfolio explicitly, no market data ships with the package, and approximations (Kirk,
Turnbull-Wakeman, `bang_bang`) are labelled, never hidden. See
[the "Why QuantVolt?" page](https://nimabahrami.github.io/quantvolt/#/guide/why) and the
[external validation evidence](docs/validation.md) for the checkable version of these claims.

## Install

Requires Python 3.11+.

```bash
uv add quantvolt            # or: pip install quantvolt
uv add "quantvolt[data]"    # optional data adapters (pulls httpx); core alone has no network dependency
```

## Quick start

Build a forward curve from observed instrument prices, price an option on it, then value a
small book and compute its risk:

```python
from datetime import date

import numpy as np
import quantvolt as qv

# 1. Build an arbitrage-checked forward curve from observed instrument prices.
ttf = qv.BUILT_IN_COMMODITIES["TTF"]
observed = [
    qv.InstrumentPriceRecord("TTF-2026-10", ttf, qv.DeliveryPeriod(2026, 10), 31.40),
    qv.InstrumentPriceRecord("TTF-2026-12", ttf, qv.DeliveryPeriod(2026, 12), 36.85),
    qv.InstrumentPriceRecord("TTF-2027-03", ttf, qv.DeliveryPeriod(2027, 3), 34.10),
]
result = qv.CurveBuilder().build(ttf, date(2026, 7, 15), observed)
curve = result.curve  # gap months filled by interpolation, marked "interpolated"

# 2. Price a European call on the Dec-26 forward (Black-76).
option = qv.price_vanilla_option(qv.VanillaOptionRequest(
    option_type="call", strike=38.0, notional=10_000.0,
    forward=curve.price_at(qv.DeliveryPeriod(2026, 12)),
    sigma=0.55, time_to_expiry=0.4, discount_factor=0.99,
))

# 3. Value a small book and run portfolio risk on it.
future = qv.FuturesContract(ttf, qv.DeliveryPeriod(2026, 12), contract_price=35.0, notional=5_000.0)
portfolio = qv.Portfolio(positions=(qv.Position(instrument=future),))
discounting = qv.DiscountCurve(
    reference_date=date(2026, 7, 15),
    tenors=(date(2026, 7, 16), date(2027, 12, 31)),
    factors=(1.0, 0.96),
)
market = qv.MarketData({"TTF": curve}, discounting, date(2026, 7, 15))
valuation = qv.value_portfolio(portfolio, market)

scenarios = np.random.default_rng(42).normal(0.0, 1.5, size=(500, 1))  # EUR/MWh moves
risk = qv.RiskEngine().compute_risk(list(valuation.priced), scenarios)

print(f"Dec-26 TTF: {curve.price_at(qv.DeliveryPeriod(2026, 12)):.2f} EUR/MWh")
print(f"Call premium: {option.premium:,.0f} EUR (delta {option.greeks.delta:,.0f} EUR per EUR/MWh)")
print(f"Book NPV: {valuation.total_npv:,.0f} EUR, VaR(95): {risk.var_95:,.0f} EUR")
```

```
Dec-26 TTF: 36.85 EUR/MWh
Call premium: 45,663 EUR (delta 5,288 EUR per EUR/MWh)
Book NPV: 9,133 EUR, VaR(95): 11,715 EUR
```

Identical inputs give identical outputs: Monte Carlo honours a `seed`, inputs are validated
eagerly (no silent partial results), results round-trip through plain dicts / JSON, and the
library never mutates caller data — `quantvolt.testing.assert_input_unchanged` lets you verify
that last invariant in your own tests.

### Settle a PPA with your own interval data

QuantVolt does not require its optional data adapters. Map any caller-owned Polars columns
onto the canonical settlement inputs; the returned ledger uses stable canonical names:

```python
from datetime import UTC, datetime

import polars as pl
import quantvolt as qv

data = pl.DataFrame({
    "from": [datetime(2026, 1, 1, tzinfo=UTC)],
    "to": [datetime(2026, 1, 1, 1, tzinfo=UTC)],
    "nomination_mwh": [10.0],
    "meter_mwh": [8.0],
    "day_ahead_eur_mwh": [90.0],
    "short_buy_eur_mwh": [100.0],
    "excess_sell_eur_mwh": [40.0],
})
contract = qv.PpaContract(
    contract_id="plant-ppa",
    bidding_zone="DE-LU",
    fixed_price_per_mwh=70.0,
    start_utc=datetime(2026, 1, 1, tzinfo=UTC),
    end_utc=datetime(2026, 1, 2, tzinfo=UTC),
    volume_basis=qv.PpaVolumeBasis.BASELOAD,
)
columns = qv.PpaDataColumns(
    interval_start_utc="from",
    interval_end_utc="to",
    contracted_mwh="nomination_mwh",
    metered_generation_mwh="meter_mwh",
    spot_price_per_mwh="day_ahead_eur_mwh",
    shortfall_price_per_mwh="short_buy_eur_mwh",
    excess_price_per_mwh="excess_sell_eur_mwh",
)
ledger = qv.settle_ppa_frame(contract, data, columns=columns)
```

Physical settlement requires shortfall and excess prices by default. A spot-price imbalance
proxy is available only through the explicit
`imbalance_policy=qv.MissingImbalancePricePolicy.USE_SPOT` assumption. The batch boundary
rejects null/non-finite values, duplicate or unsorted intervals, gaps/overlaps, negative energy,
and intervals outside the contract before calculating cash flow.

For German quarter-hour settlement, the optional data layer can attach official quality-assured
reBAP prices. The same helper also accepts a reBAP-shaped frame loaded from your own database or
file; no network adapter is required:

```python
from quantvolt.data import NetztransparenzSource, attach_rebap_prices

# Reads QUANTVOLT_NETZTRANSPARENZ_CLIENT_ID and
# QUANTVOLT_NETZTRANSPARENZ_CLIENT_SECRET, unless credentials are passed explicitly.
rebap = NetztransparenzSource().rebap(start_utc, end_utc)
data = attach_rebap_prices(
    caller_data,
    rebap,
    interval_start_column="from",
    interval_end_column="to",
)
```

The join uses both interval endpoints and rejects missing or duplicate matches. It never replaces
existing imbalance columns, so accidental mixing of two price sources fails before settlement.

Typed realized hedges can be applied directly without precomputing an opaque cash-flow
column:

```python
floor = qv.PowerHedgeContract(
    hedge_id="revenue-floor",
    hedge_type=qv.PowerHedgeType.FLOOR,
    position=qv.PowerHedgePosition.LONG,
    start_utc=contract.start_utc,
    end_utc=contract.end_utc,
    volume_mwh=10.0,
    strike_per_mwh=60.0,
    allocated_premium_per_mwh=2.0,
)
ledger = qv.settle_ppa_frame(contract, data, columns=columns, hedges=[floor])
hedge_detail = qv.settle_power_hedges_frame(
    [floor], data,
    interval_start_column="from",
    interval_end_column="to",
    spot_price_column="day_ahead_eur_mwh",
)
```

The typed hedge and a caller-supplied `hedge_cashflow` column are mutually exclusive to
prevent double counting. `settle_power_hedges_frame()` provides contract-level attribution;
`settle_ppa_frame()` carries the aggregate into the reconciled producer ledger.

### Calibrate a nomination without look-ahead

For a physical baseload PPA, a constant interval nomination can be selected from a caller's
calibration sample and then applied only after the declared cutoff:

```python
nomination_columns = qv.PpaNominationColumns(
    interval_start_utc="from",
    interval_end_utc="to",
    metered_generation_mwh="meter_mwh",
    shortfall_price_per_mwh="short_buy_eur_mwh",
    excess_price_per_mwh="excess_sell_eur_mwh",
)
fit = qv.calibrate_ppa_nomination(
    contract,
    calibration_data,
    calibration_end_utc=datetime(2026, 1, 1, tzinfo=UTC),
    capacity_mwh_per_interval=2.5,
    columns=nomination_columns,
    objective=qv.PpaNominationObjective.MAX_MEAN_MINUS_CFAR,
    risk_aversion=1.0,
    confidence_level=0.95,
)
evaluation_data = qv.apply_ppa_nomination(
    fit,
    evaluation_data,
    interval_start_column="from",
    interval_end_column="to",
)
```

The candidate diagnostics expose mean cash flow, the lower percentile, CFaR, and objective
value for every tested volume. Calibration rows ending after the cutoff are rejected, and
the fitted result cannot be applied to observations before that cutoff. This makes the
calibration/evaluation split executable rather than a documentation-only convention. It also
rejects a resolution change between calibration and evaluation, preventing an hourly MWh
nomination from being silently applied as though it were a quarter-hour MWh nomination.

### PPAs and hedges inside a portfolio

`PpaContract` and `PowerHedgeContract` are valid `Position.instrument` values. Realized
interval settlement is aggregated at portfolio level using each position's explicit ID:

```python
portfolio = qv.Portfolio((
    qv.Position(contract, position_id="plant-ppa"),
    qv.Position(floor, position_id="revenue-floor"),
    qv.Position(power_future, position_id="exchange-hedge"),
))
realized = qv.settle_energy_portfolio(
    portfolio,
    {
        "plant-ppa": ppa_interval_data,
        "revenue-floor": power_price_data,
    },
)
```

The PPA and floor appear in `realized.settled`; the future remains in
`realized.unsettled` for its exchange-settlement engine. Conversely, generic
`value_portfolio()` reports PPAs and realized hedge contracts as `unpriced` unless the caller
registers an appropriate forward-looking valuation pricer. This separation prevents realized
cash flow from being mislabeled as NPV.

## Modules

The top-level `quantvolt` namespace is a curated facade (159 names) over these sub-packages;
specialised names stay on their sub-package. Full reference with a runnable example per module:
[docs/api.md](docs/api.md).

| Module | Contents |
|---|---|
| `quantvolt.models` | Frozen value objects: commodities/hubs, delivery periods and schedules, forward and discount curves, volatility surfaces, instruments, transmission/pipeline rights, Greeks |
| `quantvolt.numerics` | Pure math kernels on `float`/`ndarray`: Black-76, Kirk/Margrabe, Asian/barrier/lookback analytics, interpolation, root finding, correlated-forward Monte Carlo, price-of-risk / measure-adjustment identities, the Rust Monte Carlo wrapper |
| `quantvolt.curves` | `CurveBuilder` (gap-filling interpolation, commodity registry) and `ArbitrageChecker` (storage/cost-of-carry consistency) |
| `quantvolt.pricing` | Futures/forwards, swaps, vanilla options and caps/floors, exotics, spread options, tolling, spark/dark/clean spreads, implied vol and surfaces, mark-to-market |
| `quantvolt.risk` | `RiskEngine` (historical-simulation VaR/CVaR, delta aggregation into a commodity × period matrix, named stress scenarios) plus the Chapter-10 risk family — parametric & delta-gamma VaR, full-revaluation Monte Carlo VaR, Cash-Flow-at-Risk, Credit VaR, and EWMA / GARCH covariance forecasting |
| `quantvolt.hedging` | Incomplete-market hedging: variance-minimizing and cross-commodity hedge ratios, local/global mean-variance strategies, hybrid-model chain-rule deltas and residual-variance hedge-quality metric |
| `quantvolt.assets` | Physical-asset optimization: thermal-plant dispatch (perfect-foresight DP + stochastic LSM/lattice), dispatch approximations, gas-storage intrinsic/extrinsic valuation, long-dated valuation governance |
| `quantvolt.curvemodels` | Stochastic forward-curve models: two-factor Schwartz-Smith and the multifactor / multi-commodity lognormal forward model |
| `quantvolt.stats` | Descriptive statistics, normality tests, ADF/KPSS stationarity with Samuelson-effect detection, correlation, Ornstein-Uhlenbeck mean reversion |
| `quantvolt.market` | Transmission cost, temperature/degree-day utilities, generation outage / reliability KPIs |
| `quantvolt.workflow` | 7-step model-selection workflow for structured products |
| `quantvolt.portfolio` | `Portfolio`/`Position` book assembly; `value_portfolio` natively prices futures, forwards, swaps, transmission/pipeline rights, vanilla options, spread options and tolling agreements via the caller-extensible `DEFAULT_PRICERS` registry (PPAs and realized hedges are valued via a caller-registered pricer, e.g. `make_ppa_pricer` — deliberately not a default); realized interval `settle_energy_portfolio` aggregation is kept structurally separate from that forward-looking NPV |
| `quantvolt.data` | Optional (`quantvolt[data]`): provider adapters behind a `DataSource` protocol — the only package that performs I/O |
| `quantvolt.testing` | `assert_input_unchanged` — shipped test utility for the no-mutation invariant |
| `quantvolt.exceptions` | The `EnergyQuantError` hierarchy (`ValidationError`, `ArbitrageError`, `MissingTenorError`, …) |
| `quantvolt._core` | Native Rust extension (PyO3): Monte Carlo path simulation and the Asian MC pricer; wrapped by `numerics.monte_carlo`, typed via `_core.pyi` |

### Risk management and asset optimization

Beyond pricing, the library covers the risk-measurement and physical-asset workflow. On the
risk side it offers the full VaR family — historical-simulation VaR via `RiskEngine`, analytic
parametric and delta-gamma VaR, full-revaluation Monte Carlo VaR, Cash-Flow-at-Risk, and Credit
VaR — over EWMA / GARCH covariance forecasts, alongside incomplete-market hedging
(`quantvolt.hedging`). On the asset side `quantvolt.assets` values dispatchable thermal plant
(perfect-foresight and stochastic dispatch) and gas storage (intrinsic + extrinsic), and
`quantvolt.curvemodels` supplies Schwartz-Smith and multifactor forward-curve models. Two
disciplines are enforced structurally rather than left to convention: the probability measure
is explicit and checked (physical *P* for VaR/CFaR, risk-neutral *Q* for valuation — a
mis-tagged drift raises), and VaR is flagged inapplicable for illiquid, projected-spot
positions. See [docs/risk-and-assets.md](docs/risk-and-assets.md).

## Documentation

- [Why QuantVolt?](https://nimabahrami.github.io/quantvolt/#/guide/why) — the integration problem,
  the shared computational model, the extensible pricer registry, and an honest "what QuantVolt is
  not" section
- [docs/api.md](docs/api.md) — module-by-module API reference with runnable examples
- [docs/risk-and-assets.md](docs/risk-and-assets.md) — the VaR family, the physical-vs-risk-neutral
  drift rule, incomplete-market hedging, dispatch & storage, and the long-dated / liquidity caveats
- [docs/european-markets.md](docs/european-markets.md) — market coverage, power-vs-gas
  statistics, negative prices, Samuelson effect, carbon costs, data-source policy
- [docs/validation.md](docs/validation.md) — external validation evidence: QuantVolt's pricers
  checked against QuantLib 1.43 golden fixtures, with honest caveats and regeneration instructions
- Three complete, runnable end-to-end tutorials (site, each backed by a `site/examples/
  verify_tutorial_*.py` script): [spark spread to hedge](https://nimabahrami.github.io/quantvolt/#/guide/tutorial-spark),
  [renewable PPA to CFaR](https://nimabahrami.github.io/quantvolt/#/guide/tutorial-ppa), and
  [storage intrinsic to hedge](https://nimabahrami.github.io/quantvolt/#/guide/tutorial-storage)
- `.kiro/steering/` — product, tech, structure, and coding-style standards
- `.kiro/specs/power-energy-quant-analysis/` — requirements, design, and task breakdown
  (the library is spec-driven; the design document is the source of truth for the maths)

## Development

Contributors need a Rust toolchain ([rustup](https://rustup.rs)) to build the native extension
from source; wheel users need nothing beyond Python.

```bash
uv sync                     # create/refresh the environment from the lockfile
maturin develop             # build the Rust _core extension into the venv
uv run pytest               # Python test suite (unit + property)
uv run ruff check           # lint
uv run ruff format          # format
uv run mypy src/            # type-check (strict)
cargo test                  # Rust unit tests
```

`pyproject.toml` is the single configuration source (maturin build backend, ruff, mypy,
pytest); the Rust crate lives in `rust/` and compiles to `quantvolt._core`.

## Optional research datasets

Large market snapshots are deliberately excluded from package installations. Discover
and fetch only the versioned data you need:

```bash
quantvolt data list
quantvolt data info smard-de-power-experiment
quantvolt data fetch smard-de-power-experiment
quantvolt data verify smard-de-power-experiment
```

Downloads are cached outside the package, verified by byte size and SHA-256, and never
occur during import. Set `QUANTVOLT_DATA_DIR` to choose another cache or use the Python
API in `quantvolt.data.datasets`. Provenance and license notes are in
[`data/README.md`](data/README.md).
