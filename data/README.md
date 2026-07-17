# Real gas-market experiment data

> **Optional-data policy:** Full snapshots are published as immutable assets in the
> [`data-2026.07` release](https://github.com/nimabahrami/quantvolt/releases/tag/data-2026.07).
> They are not part of the Python package and, after the history-cleanup cutover, will
> not be part of ordinary Git clones. Use `quantvolt data list` and
> `quantvolt data fetch <dataset-id>` to download one checksummed dataset explicitly.
> Tiny files under `data/samples/` remain in Git for tutorials and offline tests.

This directory contains unmodified public source files in `raw/` and normalized,
analysis-ready copies in `processed/`. Prices are nominal unless stated otherwise.

## Sources and limitations

### EIA — Henry Hub spot and NYMEX futures

- Source: <https://www.eia.gov/dnav/ng/ng_pri_fut_s1_d.htm>
- Raw file: `raw/eia/NG_PRI_FUT_S1_D.xls`
- Retrieved: 2026-07-15
- Units: USD/MMBtu
- Spot coverage: 1997-01-07 through 2026-07-13
- Futures coverage: 1993-12-20 through 2024-04-05
- Provenance: official daily NYMEX closing prices republished by the U.S. EIA

The four futures columns are rolling Contract 1 through Contract 4 series. They
are suitable for return calibration, rolling hedge tests, and near-curve spread
experiments. They are **not** point-in-time snapshots of every historical expiry,
so contract rolls must be handled explicitly and they cannot reconstruct a full
historical forward surface.

### World Bank Pink Sheet — monthly gas benchmarks

- Source: <https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet>
- Raw file: `raw/world_bank/CMO-Historical-Data-Monthly.xlsx`
- Workbook update: 2026-07-02
- Retrieved: 2026-07-15
- Units: USD/MMBtu

The European series represents TTF from April 2015 onward. Earlier observations
use changing European import/spot definitions documented in the workbook, so a
single model spanning that boundary needs a methodology-break indicator.

### European Commission JRC ENaGaD — daily physical demand

- Source: <https://data.jrc.ec.europa.eu/dataset/6b5ce3b7-6ca8-4dc9-b441-e14b76312335>
- Raw file: `raw/jrc/ENAGAD.csv`
- Dataset version: 202605
- Coverage: 2008-01-04 through 2026-04-30; most country series begin in 2015
- Units: GWh/day
- Licence: CC BY 4.0; credit the European Commission Joint Research Centre

`PROC`/`provenance_flag` primarily distinguishes original (`O`) from estimated
(`E`) observations. The source also contains a small number of null, `A`, `p`,
and `corrected` flags that its header does not define. Experiments should retain
the field, treat those values as source-quality annotations rather than silently
coercing them, and test sensitivity to using only `O` records.

## Rebuilding processed files

Install the project environment plus spreadsheet readers, then run:

```console
uv pip install --python .venv/bin/python xlrd openpyxl
.venv/bin/python scripts/prepare_gas_data.py
```

Checksums for the exact raw inputs are recorded in `SHA256SUMS`.

## Power prices

### Bundesnetzagentur SMARD — DE/LU day-ahead auction

- Source: <https://www.smard.de/en/downloadcenter/download-market-data>
- Attribution: `Bundesnetzagentur | SMARD.de`
- Licence: CC BY 4.0
- Bidding zone: Germany/Luxembourg (`DE-LU`)
- Units: EUR/MWh
- Raw files: `raw/smard/day_ahead_price_de_lu/`
- Processed files: `processed/smard_de_lu_day_ahead_native.{csv,parquet}`

The processed table preserves the product actually traded: one-hour delivery
intervals before 2025-10-01 00:00 Europe/Berlin, then 15-minute delivery
intervals from that boundary onward. The equivalent UTC boundary is
2025-09-30 22:00Z. SMARD's quarter-hour endpoint repeats each hourly price four
times before the transition; those repetitions are deliberately excluded.

Every interval carries UTC start/end timestamps, an ISO local-clock label with
its offset, local date, duration, bidding zone, unit-specific price column, and
source attribution. Raw weekly response hashes and URLs are in the adjacent
`manifest.json`.

Rebuild the snapshot with:

```console
.venv/bin/python scripts/fetch_smard_power_data.py
```

### Bundesnetzagentur SMARD — German physical fundamentals

- Raw files: `raw/smard/power_fundamentals_de/`
- Processed files: `processed/smard_de_power_fundamentals_quarter_hour.{csv,parquet}`
- Resolution: 15 minutes
- Units: MWh per delivery interval
- Series: total load, onshore wind, offshore wind, solar, and gas-fired generation

These are system-level German observations, not a specific plant's meter. They
can validate timestamp alignment, volume aggregation, PPA settlement identities,
and hedge behavior. A plant experiment must use an explicitly documented scaling
or a genuine plant meter; national generation must never be presented as if it
were a plant's production.

Rebuild with:

```console
.venv/bin/python scripts/fetch_smard_power_fundamentals.py
```

### Experiment-ready interval join

`processed/smard_de_power_experiment_intervals.{csv,parquet}` joins every
15-minute physical observation to the day-ahead product that settles it. Two
separate clocks are retained:

- `interval_*`: the physical 15-minute meter interval;
- `price_product_*`: the one-hour or 15-minute auction product.

This prevents a repeated pre-October-2025 hourly price from being mislabelled as
four independently observed quarter-hour prices. Rebuild with:

```console
.venv/bin/python scripts/prepare_power_experiment_data.py
```

### Netztransparenz reBAP — German imbalance settlement

`quantvolt.data.NetztransparenzSource` retrieves the official quality-assured
quarter-hour reBAP CSV through OAuth client credentials. Configure
`QUANTVOLT_NETZTRANSPARENZ_CLIENT_ID` and
`QUANTVOLT_NETZTRANSPARENZ_CLIENT_SECRET`; neither value is persisted or shown
in errors. `attach_rebap_prices()` performs an exact start-and-end timestamp
join onto any caller-owned interval frame and fails if a price is missing,
duplicated, or would overwrite existing imbalance columns.

The parser preserves separate under-covered and over-covered values because
they can be asymmetric. It also preserves negative prices and accepts only UTC,
EUR/MWh, and exact 15-minute intervals. A user-provided frame with the same
canonical columns can be used instead of the live adapter.

## PPA validation experiment

`scripts/run_power_ppa_backtest.py` uses 2019-2021 as a calibration-only
window, then evaluates 2022-2025 without changing the contract terms. Outputs
are stored under `data/experiments/`.

Alongside the original 25th-percentile baseload nomination, the experiment fits
an `optimized_baseload_ppa` using only the calibration window. It evaluates a
bounded nomination grid with the documented mean-minus-CFaR objective, records
the selected 15-minute MWh volume, and applies it only from the evaluation
cutoff onward. A separate `walk_forward_baseload_ppa` refits at each annual UTC
cutoff from 2022 through 2025 using an expanding historical window. Every
evaluation interval is tagged with its fit index; an interval crossing a cutoff
is rejected instead of being assigned partly in-sample and partly out-of-sample.

The experiment scales the national onshore-wind shape to a virtual 10 MW cap.
That makes it useful for checking interval settlement, PPA volume risk, negative
prices, and cash-flow risk, but it is **not** a real plant backtest. Results are
gross market cash flow: capex, fixed O&M, tax, financing, true imbalance prices,
and traded option premiums are not yet present and no output should be described
as investable profit.
