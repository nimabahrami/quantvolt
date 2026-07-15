# European market specifics

What `quantvolt` models about European power, gas, and carbon markets, and where in the
library each specific lives.

## Hubs and commodities

`quantvolt.models.BUILT_IN_COMMODITIES` ships these entries:

| `commodity_id` | Market | Exchange | Price unit |
|---|---|---|---|
| `EEX_PHELIX_DE` | German power (Phelix) | EEX | EUR/MWh |
| `EEX_PHELIX_AT` | Austrian power (Phelix) | EEX | EUR/MWh |
| `EPEX_DE` | German spot power | EPEX SPOT | EUR/MWh |
| `EPEX_FR` | French spot power | EPEX SPOT | EUR/MWh |
| `EPEX_NL` | Dutch spot power | EPEX SPOT | EUR/MWh |
| `EPEX_BE` | Belgian spot power | EPEX SPOT | EUR/MWh |
| `EPEX_GB` | British spot power | EPEX SPOT | GBP/MWh |
| `TTF` | Dutch natural gas | ICE Endex | EUR/MBtu |
| `NBP` | British natural gas | ICE Endex | GBP/MBtu |
| `EUA` | EU carbon allowances | EEX | EUR/tCO2 |

The registry is extended, never edited: `merge_commodities({...})` (or
`CurveBuilder(extra_commodities={...})`) merges caller-defined `CommodityConfig` entries over
the built-ins, caller entries winning on id collision — so an unlisted hub needs no change to
library source.

## Negative power prices

European power prices go negative — renewables with priority dispatch plus inflexible thermal
plant can push day-ahead hours below zero. The library treats this as a normal market outcome,
not an error:

- `CurveNode`/`ForwardCurve` (`models/curve.py`) accept negative prices verbatim; validation
  constrains curve *structure* (ordered, duplicate-free periods), never the sign of a price.
- Instruments (`models/instruments.py`) leave `contract_price` and swap `fixed_rate`
  unconstrained; only physically meaningless quantities (non-positive notional or heat rate)
  are rejected.
- Spreads, futures/swap pricing, mark-to-market, and portfolio valuation all flow negative
  prices through arithmetically.

One deliberate exception: Black-76 vanilla option pricing (`pricing.price_vanilla_option`,
`numerics.black76_price`) validates `forward > 0`, because the model assumes a lognormal
forward. Optionality on spreads that may go negative belongs to `price_spread_option`
(Kirk/Margrabe), which prices the *difference* of two forwards.

## Power vs gas: non-storability and its statistical fingerprint

Gas is storable; power effectively is not. That single physical difference drives the
statistical split the library is built around:

- **Higher volatility and spikes in power.** Without storage there is no inventory buffer, so
  shocks hit prices directly. `stats.descriptive_stats` reports skewness, excess kurtosis, and
  a mean-vs-zero t-statistic per series, so power and gas get separate parameter estimates;
  `stats.test_normality` (Jarque-Bera, Shapiro-Wilk, D'Agostino-Pearson, Anderson-Darling)
  quantifies how fat-tailed the returns actually are before you assume normal VaR.
- **Stronger mean reversion in power.** `stats.fit_ou` fits an Ornstein-Uhlenbeck process and
  reports `reversion_speed` and `half_life`; power series typically fit with much shorter
  half-lives than gas.
- **A cost-of-carry band for gas, none for power.** `curves.ArbitrageChecker` (run inside every
  `CurveBuilder.build`) flags a consecutive pair where the far price sits below the near price
  by more than `storage_cost × months_between` — the decline storage carry can explain. For a
  storable commodity like TTF, pass the physical storage cost; for power, where no carry
  argument exists, backwardated (e.g. seasonal winter-over-summer) curves are economically
  normal, so treat the returned `ArbitrageWarning`s as diagnostics to interpret, not errors —
  they never block the build.
- **Both markets in one book.** Cross-commodity dependence is measured with
  `stats.correlation_matrix` / `rolling_correlation`, and spread pricing
  (`price_spread_option`) carries an explicit `correlation` input with a reported
  `correlation_sensitivity`.

## Sampling futures over time: the Samuelson effect

A futures price series sampled on different dates is generally non-stationary, and its return
volatility tends to *rise* as the contract approaches expiry (the Samuelson effect).
`stats.test_stationarity` addresses both at once: it runs ADF and KPSS (the series counts as
stationary only when the two tests agree) and separately sets `samuelson_effect_detected` by
ordering observations by distance from `contract_expiry` and comparing near-expiry against
far-from-expiry return volatility. Check this flag before treating a sampled history as one
homogeneous dataset for calibration or VaR.

## Seasonality in implied volatility

European energy volatility is seasonal — power volatility peaks with winter heating (and
increasingly summer cooling) demand, gas volatility with winter storage withdrawal. The
library captures this through the volatility term structure rather than a single sigma:

- `models.VolatilitySurface` holds one `VolatilityTenor` (a sigma) per `DeliveryPeriod`, so a
  January and a July delivery carry different vols; `sigma_at(period)` is the lookup.
- `pricing.build_volatility_surface` constructs the surface from market `OptionQuote`s,
  inverting each premium via `pricing.implied_vol` (Black-76 with no-arbitrage premium bounds
  checked before inversion, convergence reported on the result).
- `pricing.classify_moneyness` tags quotes ATM/ITM/OTM (ATM within a configurable band around
  the forward, default 2%), the axis along which smile/smirk shapes appear.
- `pricing.cumulative_historical_vol` gives rolling realised volatility for
  implied-vs-realised comparisons.
- Seasonal surfaces feed structured valuation directly: `price_tolling_agreement` takes a
  `VolatilitySurface` and values each delivery month with its own sigma.

## Carbon (EUA) in generation spreads

Fossil generators must surrender EU allowances, so carbon is part of the running cost of every
spark or dark spread:

- `pricing.spark_spread` / `dark_spread` compute the raw margin
  `power − heat_rate × fuel − variable_cost − emissions_cost` per delivery period.
- `pricing.clean_spread` then deducts the market carbon cost explicitly:
  `cleaned = spread − emissions_intensity × EUA_price`, taking the EUA forward curve (the
  built-in `"EUA"` commodity, EUR/tCO2) period by period and reporting the deducted
  `carbon_cost` alongside the cleaned spread. A spread that looks profitable pre-carbon can be
  negative clean — the worked example in [api.md](api.md#quantvoltpricing--derivatives-pricing-and-spreads)
  shows +14.80 EUR/MWh turning into −14.06 after 0.37 tCO2/MWh at 78 EUR/tCO2.
- `models.PlantConfig.emissions_intensity` carries the plant parameter, and
  `price_tolling_agreement` takes an `eua_curve` so tolling values are carbon-inclusive.
- The built-in stress catalogue (`risk.BUILT_IN_SCENARIOS`) includes a "Carbon Price Shock"
  (EUA doubling passing through to power) next to "European Gas Crisis 2022", "Cold Snap
  Winter", and "Mild Winter Demand Slump".

## Risk categories

`models.RiskType` enumerates the risk vocabulary used for European physical-plus-financial
books: `EXECUTION`, `BASIS` (hedge hub imperfectly correlated with the exposure hub — measure
it with `pricing.basis` between two curves), `LIQUIDITY`, `CREDIT` (forwards carry a
`counterparty` field for this), and the two physical categories, `STORAGE` and `TRANSMISSION`
(cost model in `market.transmission_cost`).

## Forward curves: free vs commercial data sources

There is no free source of European forward/futures curves, and the library does not pretend
otherwise (Requirement 12.8):

- **Free, token-authenticated adapters** (`quantvolt[data]`) cover spot and fundamentals only:
  `EntsoeSource` (ENTSO-E day-ahead prices, load, generation), `EntsogSource` (gas flows),
  `OpenMeteoSource` (temperatures, keyless). None of them exposes a `forward_curve` method —
  by design, not omission.
- **Commercial stubs** (`EexSource`, `EpexSource`, `IceSource`, `NordPoolSource`,
  `LsegSource`) define where forward curves, EUA, and settlement prices plug in once you hold
  a licence; until then every method raises a `DataSourceError` naming the credential to
  configure.
- **Caller-supplied data always works**: build curves yourself from broker or exchange quotes
  via `CurveBuilder`, or rehydrate a stored curve with `ForwardCurve.from_dict` /
  `quantvolt.data.restore`. Fetched and caller-supplied data are interchangeable everywhere in
  the core.
