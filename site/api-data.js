window.API_DATA = {
  "version": "0.1.0",
  "modules": [
    {
      "name": "quantvolt",
      "qualified": "quantvolt",
      "description": "Curated top-level facade for the most common QuantVolt workflows.",
      "symbols": [
        {
          "name": "ArbitrageChecker",
          "module": "quantvolt",
          "qualified": "quantvolt.curves.arbitrage.ArbitrageChecker",
          "kind": "class",
          "signature": "ArbitrageChecker()",
          "summary": "Thin class alias over :func:`check_arbitrage` (Task 18).",
          "doc": "Thin class alias over :func:`check_arbitrage` (Task 18).\n\n``ArbitrageChecker`` was originally the sole home of this logic; per\n``coding-style.md`` §0/§2 a stateless single-method class is realised as a\nmodule function instead (the \"lightest Python construct\"). The class is kept\n— delegating to :func:`check_arbitrage` — only because it is part of the\npublic facade and directly exercised by tests as ``ArbitrageChecker().check(...)``.",
          "methods": [
            {
              "name": "check",
              "signature": "check(self, curve: ForwardCurve, storage_cost: float=0.0, *, eps: float=_ARBITRAGE_EPS) -> list[ArbitrageWarning]",
              "summary": "See :func:`check_arbitrage`."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curves/arbitrage.py",
          "line": 147
        },
        {
          "name": "ArbitrageError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.ArbitrageError",
          "kind": "class",
          "signature": "ArbitrageError()",
          "summary": "Curve contains arbitrage violations that cannot be identified.",
          "doc": "Curve contains arbitrage violations that cannot be identified.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 34
        },
        {
          "name": "ArbitrageWarning",
          "module": "quantvolt",
          "qualified": "quantvolt.curves.arbitrage.ArbitrageWarning",
          "kind": "class",
          "signature": "ArbitrageWarning(periods: tuple[DeliveryPeriod, ...], message: str)",
          "summary": "A localised storage-arbitrage violation between identifiable curve nodes.",
          "doc": "A localised storage-arbitrage violation between identifiable curve nodes.\n\n``periods`` holds the offending consecutive pair ``(p_early, p_late)``; ``message``\ndescribes the negative time spread and the cost of carry it exceeds.",
          "methods": [],
          "fields": [
            {
              "name": "periods",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            },
            {
              "name": "message",
              "type": "str",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curves/arbitrage.py",
          "line": 59
        },
        {
          "name": "AsianOptionRequest",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.AsianOptionRequest",
          "kind": "class",
          "signature": "AsianOptionRequest(option_type: Literal['call', 'put'], averaging: Literal['arithmetic', 'geometric'], strike: float, forward: float, sigma: float, time_to_expiry: float, discount_factor: float, method: Literal['turnbull_wakeman', 'kemna_vorst', 'monte_carlo'] | None = None, seed: int | None = None, path_count: int = 10000)",
          "summary": "Inputs for an Asian option calculation.",
          "doc": "Inputs for an Asian option calculation. Select arithmetic or geometric averaging and the requested analytic or seeded Monte Carlo method; all price, volatility, expiry, discounting, averaging and notional assumptions are explicit fields.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "averaging",
              "type": "Literal['arithmetic', 'geometric']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "method",
              "type": "Literal['turnbull_wakeman', 'kemna_vorst', 'monte_carlo'] | None",
              "default": "None"
            },
            {
              "name": "seed",
              "type": "int | None",
              "default": "None"
            },
            {
              "name": "path_count",
              "type": "int",
              "default": "10000"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 60
        },
        {
          "name": "AuthenticationError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.AuthenticationError",
          "kind": "class",
          "signature": "AuthenticationError()",
          "summary": "Provider credential is missing or rejected (the value is never included).",
          "doc": "Provider credential is missing or rejected (the value is never included).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 59
        },
        {
          "name": "BangBangHedgeWarning",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_approx.BangBangHedgeWarning",
          "kind": "class",
          "signature": "BangBangHedgeWarning()",
          "summary": "Advisory that bang-bang state aggregation biases hedges far more than values (Req 21.3).",
          "doc": "Advisory that bang-bang state aggregation biases hedges far more than values (Req 21.3).\n\nCollapsing the output grid to {0, c_max} pins the operating point to full load,\nso the plant value loses only the (often small) part-load optionality. The\n*sensitivities* — the deltas and critical-dispatch surfaces used to hedge — are\na different matter: they read the slope of value against price, and the\napproximation replaces the true, curved heat-rate response with a single kink\nat the on/off boundary. A hedge derived from a bang-bang model can therefore be\nbadly wrong even when the headline value looks reasonable. The approximation is\nnot rejected — for a sufficiently steep heat curve the value error is genuinely\nnegligible — but the caller is warned so the choice is deliberate.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 72
        },
        {
          "name": "BarrierOptionRequest",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.BarrierOptionRequest",
          "kind": "class",
          "signature": "BarrierOptionRequest(option_type: Literal['call', 'put'], barrier_type: Literal['up_in', 'up_out', 'down_in', 'down_out'], strike: float, barrier: float, forward: float, sigma: float, time_to_expiry: float, discount_factor: float)",
          "summary": "Inputs for an analytic barrier option.",
          "doc": "Inputs for an analytic barrier option. The barrier direction and knock behavior are encoded by the option/barrier type together with spot/forward, strike, barrier, volatility, expiry and discounting assumptions.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "barrier_type",
              "type": "Literal['up_in', 'up_out', 'down_in', 'down_out']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "barrier",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 74
        },
        {
          "name": "CapFloorRequest",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.vanilla.CapFloorRequest",
          "kind": "class",
          "signature": "CapFloorRequest(option_type: Literal['cap', 'floor'], strike: float, notional: float, caplets: tuple[VanillaOptionRequest, ...])",
          "summary": "Inputs for a cap or floor strip over aligned forward, strike, volatility, expiry and discount-factor sequences..",
          "doc": "Inputs for a cap or floor strip over aligned forward, strike, volatility, expiry and discount-factor sequences.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['cap', 'floor']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "caplets",
              "type": "tuple[VanillaOptionRequest, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 45
        },
        {
          "name": "CapFloorResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.vanilla.CapFloorResult",
          "kind": "class",
          "signature": "CapFloorResult(premium: float, greeks: Greeks, per_period: tuple[VanillaOptionResult, ...])",
          "summary": "Aggregate cap/floor premium together with the individual caplet or floorlet contributions used to reconcile it..",
          "doc": "Aggregate cap/floor premium together with the individual caplet or floorlet contributions used to reconcile it.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "greeks",
              "type": "Greeks",
              "default": null
            },
            {
              "name": "per_period",
              "type": "tuple[VanillaOptionResult, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 53
        },
        {
          "name": "CashflowStrategyComparison",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.cashflow_metrics.CashflowStrategyComparison",
          "kind": "class",
          "signature": "CashflowStrategyComparison(benchmark: str, confidence_level: float, metrics: tuple[CashflowStrategyMetrics, ...])",
          "summary": "Metrics in caller strategy order with an explicit benchmark identity.",
          "doc": "Metrics in caller strategy order with an explicit benchmark identity.",
          "methods": [
            {
              "name": "for_strategy",
              "signature": "for_strategy(self, strategy: str) -> CashflowStrategyMetrics",
              "summary": "Return one named result or fail loudly with available names."
            }
          ],
          "fields": [
            {
              "name": "benchmark",
              "type": "str",
              "default": null
            },
            {
              "name": "confidence_level",
              "type": "float",
              "default": null
            },
            {
              "name": "metrics",
              "type": "tuple[CashflowStrategyMetrics, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/cashflow_metrics.py",
          "line": 35
        },
        {
          "name": "CashflowStrategyMetrics",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.cashflow_metrics.CashflowStrategyMetrics",
          "kind": "class",
          "signature": "CashflowStrategyMetrics(strategy: str, observations: int, total_cashflow: float, mean_cashflow: float, sample_std_cashflow: float, lower_percentile_cashflow: float, minimum_cashflow: float, maximum_cashflow: float, cfar: float, negative_observations: int, total_difference_vs_benchmark: float, cfar_reduction_vs_benchmark: float, volatility_reduction_vs_benchmark: float)",
          "summary": "One strategy's realized cash-flow distribution and benchmark differences.",
          "doc": "One strategy's realized cash-flow distribution and benchmark differences.",
          "methods": [],
          "fields": [
            {
              "name": "strategy",
              "type": "str",
              "default": null
            },
            {
              "name": "observations",
              "type": "int",
              "default": null
            },
            {
              "name": "total_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "mean_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "sample_std_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "lower_percentile_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "minimum_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "maximum_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "cfar",
              "type": "float",
              "default": null
            },
            {
              "name": "negative_observations",
              "type": "int",
              "default": null
            },
            {
              "name": "total_difference_vs_benchmark",
              "type": "float",
              "default": null
            },
            {
              "name": "cfar_reduction_vs_benchmark",
              "type": "float",
              "default": null
            },
            {
              "name": "volatility_reduction_vs_benchmark",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/cashflow_metrics.py",
          "line": 16
        },
        {
          "name": "CommodityConfig",
          "module": "quantvolt",
          "qualified": "quantvolt.models.commodity.CommodityConfig",
          "kind": "class",
          "signature": "CommodityConfig(commodity_id: str, price_unit: str, hub: Hub)",
          "summary": "Immutable commodity definition containing the stable commodity ID, human-readable name and delivery hub..",
          "doc": "Immutable commodity definition containing the stable commodity ID, human-readable name and delivery hub.",
          "methods": [],
          "fields": [
            {
              "name": "commodity_id",
              "type": "str",
              "default": null
            },
            {
              "name": "price_unit",
              "type": "str",
              "default": null
            },
            {
              "name": "hub",
              "type": "Hub",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 23
        },
        {
          "name": "CurveBuilder",
          "module": "quantvolt",
          "qualified": "quantvolt.curves.builder.CurveBuilder",
          "kind": "class",
          "signature": "CurveBuilder(extra_commodities: dict[str, CommodityConfig] | None=None)",
          "summary": "Config-holding class: merges BUILT_IN_COMMODITIES with caller extensions.",
          "doc": "Config-holding class: merges BUILT_IN_COMMODITIES with caller extensions.",
          "methods": [
            {
              "name": "build",
              "signature": "build(self, commodity: CommodityConfig, market_date: date, instruments: list[InstrumentPriceRecord], interpolation: Literal['piecewise_flat', 'piecewise_linear', 'cubic_spline']='piecewise_linear', tolerance: float=0.01, storage_cost: float=0.0) -> CurveBuildResult",
              "summary": "Build a gap-filled forward curve from observed instrument prices."
            },
            {
              "name": "from_dict",
              "signature": "from_dict(data: dict[str, Any]) -> ForwardCurve",
              "summary": ""
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curves/builder.py",
          "line": 56
        },
        {
          "name": "CurveBuildResult",
          "module": "quantvolt",
          "qualified": "quantvolt.curves.builder.CurveBuildResult",
          "kind": "class",
          "signature": "CurveBuildResult(curve: ForwardCurve, arbitrage_warnings: list[ArbitrageWarning], reprice_residuals: dict[str, float])",
          "summary": "Outcome of a curve build: the curve, any arbitrage warnings, reprice residuals.",
          "doc": "Outcome of a curve build: the curve, any arbitrage warnings, reprice residuals.",
          "methods": [],
          "fields": [
            {
              "name": "curve",
              "type": "ForwardCurve",
              "default": null
            },
            {
              "name": "arbitrage_warnings",
              "type": "list[ArbitrageWarning]",
              "default": null
            },
            {
              "name": "reprice_residuals",
              "type": "dict[str, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curves/builder.py",
          "line": 38
        },
        {
          "name": "CurveNode",
          "module": "quantvolt",
          "qualified": "quantvolt.models.curve.CurveNode",
          "kind": "class",
          "signature": "CurveNode(period: DeliveryPeriod, price: float, status: Literal['observed', 'interpolated'])",
          "summary": "A single ``(period, price)`` point on a forward curve.",
          "doc": "A single ``(period, price)`` point on a forward curve.\n\n``status`` records whether the price was ``\"observed\"`` in the market or\n``\"interpolated\"`` between observations. Prices may be negative — negative\npower prices are real in European power markets — so they are never rejected.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "price",
              "type": "float",
              "default": null
            },
            {
              "name": "status",
              "type": "Literal['observed', 'interpolated']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/curve.py",
          "line": 29
        },
        {
          "name": "DataSourceError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.DataSourceError",
          "kind": "class",
          "signature": "DataSourceError()",
          "summary": "A quantvolt[data] provider fetch failed.",
          "doc": "A quantvolt[data] provider fetch failed.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 55
        },
        {
          "name": "DataUnavailableError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.DataUnavailableError",
          "kind": "class",
          "signature": "DataUnavailableError()",
          "summary": "Provider returned no data for the requested query.",
          "doc": "Provider returned no data for the requested query.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 67
        },
        {
          "name": "DeliveryPeriod",
          "module": "quantvolt",
          "qualified": "quantvolt.models.schedule.DeliveryPeriod",
          "kind": "class",
          "signature": "DeliveryPeriod(year: int, month: int)",
          "summary": "A single calendar month of delivery, identified by ``(year, month)``.",
          "doc": "A single calendar month of delivery, identified by ``(year, month)``.\n\n``order=True`` gives periods a natural chronological ordering: comparisons and\n``sorted(...)`` fall back to the ``(year, month)`` tuple in field order, so a\nperiod knows how to rank itself (Tell-Don't-Ask) and callers never compare raw\nints. Years are constrained to the range :class:`datetime.date` can represent,\nwhich also guarantees :attr:`last_day` never fails.",
          "methods": [
            {
              "name": "last_day",
              "signature": "last_day(self) -> date",
              "summary": "The calendar last day of this month (e.g. 2024-02 -> 2024-02-29)."
            }
          ],
          "fields": [
            {
              "name": "year",
              "type": "int",
              "default": null
            },
            {
              "name": "month",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/schedule.py",
          "line": 31
        },
        {
          "name": "DeliverySchedule",
          "module": "quantvolt",
          "qualified": "quantvolt.models.schedule.DeliverySchedule",
          "kind": "class",
          "signature": "DeliverySchedule(periods: tuple[DeliveryPeriod, ...])",
          "summary": "An ordered, non-empty run of delivery periods.",
          "doc": "An ordered, non-empty run of delivery periods.\n\nConsistency invariant: periods are strictly increasing by ``(year, month)``,\nso there are no duplicate or overlapping months. The schedule validates this\nfor itself at construction rather than trusting callers (Tell-Don't-Ask).",
          "methods": [],
          "fields": [
            {
              "name": "periods",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/schedule.py",
          "line": 56
        },
        {
          "name": "DeltaMatrix",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.aggregation.DeltaMatrix",
          "kind": "class",
          "signature": "DeltaMatrix(commodities: tuple[str, ...], periods: tuple[DeliveryPeriod, ...], values: tuple[tuple[float, ...], ...])",
          "summary": "Net delta exposure over the union grid of commodities x delivery periods.",
          "doc": "Net delta exposure over the union grid of commodities x delivery periods.\n\nRows (``commodities``) are sorted lexicographically; columns (``periods``) are\nsorted chronologically. The matrix is *dense* over that grid: every\n``(commodity, period)`` combination inside the grid has a cell (0.0 where no\nposition carries that exposure). Combinations outside the grid were never seen in\nany position, so :meth:`delta_at` answers 0.0 for them too — \"not held\" and \"held\nwith zero net delta\" are the same exposure. The shape invariant (one row per\ncommodity, one column per period) is validated at construction, mirroring how\n``DeliverySchedule`` validates its own consistency.",
          "methods": [
            {
              "name": "delta_at",
              "signature": "delta_at(self, commodity_id: str, period: DeliveryPeriod) -> float",
              "summary": "Net delta for one cell; 0.0 for a combination absent from the grid."
            }
          ],
          "fields": [
            {
              "name": "commodities",
              "type": "tuple[str, ...]",
              "default": null
            },
            {
              "name": "periods",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            },
            {
              "name": "values",
              "type": "tuple[tuple[float, ...], ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/aggregation.py",
          "line": 19
        },
        {
          "name": "DiscountCurve",
          "module": "quantvolt",
          "qualified": "quantvolt.models.discount_curve.DiscountCurve",
          "kind": "class",
          "signature": "DiscountCurve(reference_date: date, tenors: tuple[date, ...], factors: tuple[float, ...])",
          "summary": "A term structure of discount factors keyed by tenor date.",
          "doc": "A term structure of discount factors keyed by tenor date.\n\n``tenors`` and ``factors`` are parallel, so ``factors[i]`` is the discount\nfactor observed for ``tenors[i]``.\n\nConventions (validated eagerly in ``__post_init__``):\n\n- ``tenors`` is non-empty and strictly increasing.\n- Every tenor lies strictly *after* ``reference_date`` (``tenor > reference_date``);\n  a discount curve prices future cash flows, so ``reference_date`` itself is not a tenor.\n- Every factor lies in ``(0, 1]`` (see :func:`require_discount_factor`).",
          "methods": [
            {
              "name": "discount_factor",
              "signature": "discount_factor(self, target_date: date) -> float",
              "summary": "Discount factor for ``target_date`` by linear interpolation."
            }
          ],
          "fields": [
            {
              "name": "reference_date",
              "type": "date",
              "default": null
            },
            {
              "name": "tenors",
              "type": "tuple[date, ...]",
              "default": null
            },
            {
              "name": "factors",
              "type": "tuple[float, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/discount_curve.py",
          "line": 14
        },
        {
          "name": "DispatchDiagnostics",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.DispatchDiagnostics",
          "kind": "class",
          "signature": "DispatchDiagnostics(training_value: float, evaluation_standard_error: float, confidence_interval: tuple[float, float], training_path_count: int, evaluation_path_count: int, max_regression_condition: float)",
          "summary": "Sampling and regression evidence for an LSM dispatch value.",
          "doc": "Sampling and regression evidence for an LSM dispatch value.\n\nAttributes:\n    training_value: Mean realised value on the training paths (before the\n        independent policy-evaluation re-simulation).\n    evaluation_standard_error: Monte Carlo standard error of ``value`` (the\n        evaluation-path mean). Computed by :func:`_standard_error`, which accounts\n        for antithetic pairing when the evaluation paths use it (the default):\n        the estimator is ``std(pair_means, ddof=1) / sqrt(n_pairs)`` over the\n        antithetic pair means, not the naive iid formula over every path (which\n        would overstate the SE by ignoring the pairs' negative within-pair\n        correlation).\n    confidence_interval: Normal-approximation interval around ``value`` at\n        ``evaluation.confidence_level``, built from ``evaluation_standard_error``.\n    training_path_count: Number of training paths.\n    evaluation_path_count: Number of independent policy-evaluation paths.\n    max_regression_condition: Worst LSM regression design-matrix condition number\n        across periods (and, when a state's regression is masked to its finite\n        paths, across states within a period too).",
          "methods": [],
          "fields": [
            {
              "name": "training_value",
              "type": "float",
              "default": null
            },
            {
              "name": "evaluation_standard_error",
              "type": "float",
              "default": null
            },
            {
              "name": "confidence_interval",
              "type": "tuple[float, float]",
              "default": null
            },
            {
              "name": "training_path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "evaluation_path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "max_regression_condition",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 203
        },
        {
          "name": "DispatchFactorModel",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.DispatchFactorModel",
          "kind": "class",
          "signature": "DispatchFactorModel(log_forward0: Vector, drift: Vector, covariance: Vector, drift_kind: DriftKind, peak_kinds: tuple[PeakKind, ...], temperatures: tuple[float, ...], power_on_index: int = 0, power_off_index: int = 1, gas_index: int = 2, temperature_factor: PhysicalFactorMapping | None = None, availability_factor: PhysicalFactorMapping | None = None)",
          "summary": "Risk-adjusted factor dynamics driving stochastic dispatch (eqs. B.2-B.4).",
          "doc": "Risk-adjusted factor dynamics driving stochastic dispatch (eqs. B.2-B.4).\n\nThe stochastic factors are correlated log-forwards evolved by the Task-62\nengine ``ΔZ = mu + L·ε`` (GBM). At least a power and a gas coordinate are\nrequired; the on-peak / off-peak Markov split (eq. B.4) is expressed by naming\ntwo power coordinates (which may coincide) and a per-period peak label.\nTemperature is supplied deterministically (``temperatures``) -- it drives\n``HR`` and ``c_max`` but is not simulated here; a stochastic temperature factor\nwould simply be another simulated coordinate added to the basis.\n\nAttributes:\n    log_forward0: Initial log-forward vector ``z0 = log F(0, ·)`` over the\n        flattened factor state, dimension ``D`` (``>= 2``).\n    drift: Per-step drift ``mu`` (length ``D``). Must be the **risk-adjusted**\n        (pricing-measure) drift and is tagged by ``drift_kind``.\n    covariance: Per-step covariance ``C`` (``D x D``), assembled by\n        :func:`~quantvolt.numerics.monte_carlo.build_covariance`.\n    drift_kind: Measure tag on ``drift``; ``dispatch_value`` requires\n        :attr:`DriftKind.RISK_NEUTRAL` (Req 21.5).\n    peak_kinds: Per-period :class:`PeakKind` selecting the active power\n        coordinate; its length is the dispatch horizon ``H`` (``>= 1``).\n    temperatures: Per-period ambient temperature ``S_t`` (length ``H``).\n    power_on_index: Coordinate of ``z0`` used as the on-peak power spot.\n    power_off_index: Coordinate used as the off-peak power spot (may equal\n        ``power_on_index`` when the horizon is single-regime).\n    gas_index: Coordinate used as the gas / fuel price.",
          "methods": [
            {
              "name": "horizon",
              "signature": "horizon(self) -> int",
              "summary": "Number of dispatch periods ``H``."
            },
            {
              "name": "active_power_index",
              "signature": "active_power_index(self, period: int) -> int",
              "summary": "Power coordinate active in ``period`` (on-peak vs off-peak, eq. B.4)."
            },
            {
              "name": "simulate",
              "signature": "simulate(self, seed: int, path_count: int, *, antithetic: bool=True) -> Vector",
              "summary": "Simulate ``(n_paths, H + 1, D)`` log-forward paths (Task-62 engine)."
            }
          ],
          "fields": [
            {
              "name": "log_forward0",
              "type": "Vector",
              "default": null
            },
            {
              "name": "drift",
              "type": "Vector",
              "default": null
            },
            {
              "name": "covariance",
              "type": "Vector",
              "default": null
            },
            {
              "name": "drift_kind",
              "type": "DriftKind",
              "default": null
            },
            {
              "name": "peak_kinds",
              "type": "tuple[PeakKind, ...]",
              "default": null
            },
            {
              "name": "temperatures",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "power_on_index",
              "type": "int",
              "default": "0"
            },
            {
              "name": "power_off_index",
              "type": "int",
              "default": "1"
            },
            {
              "name": "gas_index",
              "type": "int",
              "default": "2"
            },
            {
              "name": "temperature_factor",
              "type": "PhysicalFactorMapping | None",
              "default": "None"
            },
            {
              "name": "availability_factor",
              "type": "PhysicalFactorMapping | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 234
        },
        {
          "name": "DispatchResult",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.DispatchResult",
          "kind": "class",
          "signature": "DispatchResult(value: float, start_surface: tuple[float, ...], shutdown_surface: tuple[float, ...], rampup_surface: tuple[float, ...], rampdown_surface: tuple[float, ...], diagnostics: DispatchDiagnostics | None = None)",
          "summary": "Stochastic dispatch value and the eq. B.5 critical exercise surfaces.",
          "doc": "Stochastic dispatch value and the eq. B.5 critical exercise surfaces.\n\nAttributes:\n    value: Risk-adjusted expected plant value (eq. B.3), a to-today NPV.\n    start_surface: Per-period critical spark spread above which starting up is\n        optimal (from a cold, restart-ready unit).\n    shutdown_surface: Per-period critical spark spread above which continuing\n        to run beats shutting down (a running unit shuts down below it).\n    rampup_surface: Per-period critical spark spread above which ramping up\n        from ``c_min`` beats holding.\n    rampdown_surface: Per-period critical spark spread above which holding the\n        top feasible level beats ramping down.\n\nEach surface is a length-``H`` tuple of EUR/MWh_power thresholds (measured at\n``c_min``); ``float('nan')`` marks a decision that does not arise in the period.",
          "methods": [],
          "fields": [
            {
              "name": "value",
              "type": "float",
              "default": null
            },
            {
              "name": "start_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "shutdown_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "rampup_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "rampdown_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "diagnostics",
              "type": "DispatchDiagnostics | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 371
        },
        {
          "name": "EnergyQuantError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.EnergyQuantError",
          "kind": "class",
          "signature": "EnergyQuantError()",
          "summary": "Base class for all library-raised exceptions.",
          "doc": "Base class for all library-raised exceptions.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 7
        },
        {
          "name": "ExcludedPosition",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.engine.ExcludedPosition",
          "kind": "class",
          "signature": "ExcludedPosition(index: int, reason: Literal['missing_delta', 'missing_npv', 'unresolvable_instrument'])",
          "summary": "A portfolio position omitted from a risk calculation together with the actionable reason for exclusion..",
          "doc": "A portfolio position omitted from a risk calculation together with the actionable reason for exclusion.",
          "methods": [],
          "fields": [
            {
              "name": "index",
              "type": "int",
              "default": null
            },
            {
              "name": "reason",
              "type": "Literal['missing_delta', 'missing_npv', 'unresolvable_instrument']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 79
        },
        {
          "name": "ExoticOptionResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.ExoticOptionResult",
          "kind": "class",
          "signature": "ExoticOptionResult(premium: float, greeks: Greeks, standard_error: float | None = None)",
          "summary": "Typed exotic-option output containing premium, method attribution and optional Monte Carlo standard error..",
          "doc": "Typed exotic-option output containing premium, method attribution and optional Monte Carlo standard error.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "greeks",
              "type": "Greeks",
              "default": null
            },
            {
              "name": "standard_error",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 97
        },
        {
          "name": "ExpiredContractError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.ExpiredContractError",
          "kind": "class",
          "signature": "ExpiredContractError()",
          "summary": "Contract delivery period is entirely in the past.",
          "doc": "Contract delivery period is entirely in the past.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 42
        },
        {
          "name": "FactorTransform",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.FactorTransform",
          "kind": "class",
          "signature": "FactorTransform()",
          "summary": "Transform a simulated state coordinate into a physical observable.",
          "doc": "Transform a simulated state coordinate into a physical observable.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "IDENTITY",
              "value": "'identity'"
            },
            {
              "name": "EXP",
              "value": "'exp'"
            },
            {
              "name": "LOGISTIC",
              "value": "'logistic'"
            }
          ],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 139
        },
        {
          "name": "ForwardContract",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.ForwardContract",
          "kind": "class",
          "signature": "ForwardContract(commodity: CommodityConfig, delivery_period: DeliveryPeriod, contract_price: float, notional: float, granularity: Granularity = Granularity.MONTHLY, settlement_type: SettlementType = SettlementType.PHYSICAL, counterparty: str | None = None)",
          "summary": "Bilateral forward — customisable, OTC, physical or financial settlement.",
          "doc": "Bilateral forward — customisable, OTC, physical or financial settlement.\n\n``counterparty`` is retained for credit-risk tracking.",
          "methods": [],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "contract_price",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "granularity",
              "type": "Granularity",
              "default": "Granularity.MONTHLY"
            },
            {
              "name": "settlement_type",
              "type": "SettlementType",
              "default": "SettlementType.PHYSICAL"
            },
            {
              "name": "counterparty",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 83
        },
        {
          "name": "ForwardCurve",
          "module": "quantvolt",
          "qualified": "quantvolt.models.curve.ForwardCurve",
          "kind": "class",
          "signature": "ForwardCurve(commodity: CommodityConfig, market_date: date, nodes: tuple[CurveNode, ...])",
          "summary": "A discrete forward curve: one node per delivery period, ordered by period.",
          "doc": "A discrete forward curve: one node per delivery period, ordered by period.\n\nConsistency invariants, validated eagerly in :meth:`__post_init__`:\n\n- ``nodes`` is non-empty.\n- Nodes are strictly increasing by :class:`DeliveryPeriod` (reusing the period's\n  own ordering), so there are no duplicate periods.\n- Every node's ``status`` is one of ``{\"observed\", \"interpolated\"}``.\n\nPrices are *not* constrained: negative forward prices occur in European power\nmarkets and are accepted verbatim.\n\nEquality is tolerance-based (see :meth:`__eq__`), so ``eq=False`` disables the\ndataclass-generated comparison and this class supplies its own ``__eq__`` /\n``__hash__`` pair.",
          "methods": [
            {
              "name": "price_at",
              "signature": "price_at(self, period: DeliveryPeriod) -> float",
              "summary": "Return the price of the node whose period equals ``period``."
            },
            {
              "name": "to_dict",
              "signature": "to_dict(self) -> dict[str, Any]",
              "summary": "Serialise the whole object graph to JSON-friendly built-ins."
            },
            {
              "name": "from_dict",
              "signature": "from_dict(cls, data: dict[str, Any]) -> ForwardCurve",
              "summary": "Reconstruct a :class:`ForwardCurve` from :meth:`to_dict` output."
            }
          ],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "market_date",
              "type": "date",
              "default": null
            },
            {
              "name": "nodes",
              "type": "tuple[CurveNode, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/curve.py",
          "line": 43
        },
        {
          "name": "FuturesContract",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.FuturesContract",
          "kind": "class",
          "signature": "FuturesContract(commodity: CommodityConfig, delivery_period: DeliveryPeriod, contract_price: float, notional: float, granularity: Granularity = Granularity.MONTHLY, settlement_type: SettlementType = SettlementType.FINANCIAL)",
          "summary": "Exchange-traded futures — standardised, margined, typically financial settlement.",
          "doc": "Exchange-traded futures — standardised, margined, typically financial settlement.",
          "methods": [],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "contract_price",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "granularity",
              "type": "Granularity",
              "default": "Granularity.MONTHLY"
            },
            {
              "name": "settlement_type",
              "type": "SettlementType",
              "default": "SettlementType.FINANCIAL"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 68
        },
        {
          "name": "FuturesPricingResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.futures.FuturesPricingResult",
          "kind": "class",
          "signature": "FuturesPricingResult(npv: float, delta: float)",
          "summary": "NPV and forward-price delta of a futures/forward contract.",
          "doc": "NPV and forward-price delta of a futures/forward contract.",
          "methods": [],
          "fields": [
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "delta",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/futures.py",
          "line": 27
        },
        {
          "name": "Granularity",
          "module": "quantvolt",
          "qualified": "quantvolt.models.schedule.Granularity",
          "kind": "class",
          "signature": "Granularity()",
          "summary": "Single source of delivery granularity, reused by instruments (Task 3).",
          "doc": "Single source of delivery granularity, reused by instruments (Task 3).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "HOURLY",
              "value": "'hourly'"
            },
            {
              "name": "DAILY",
              "value": "'daily'"
            },
            {
              "name": "MONTHLY",
              "value": "'monthly'"
            },
            {
              "name": "QUARTERLY",
              "value": "'quarterly'"
            },
            {
              "name": "YEARLY",
              "value": "'yearly'"
            }
          ],
          "source": "src/quantvolt/models/schedule.py",
          "line": 20
        },
        {
          "name": "Greeks",
          "module": "quantvolt",
          "qualified": "quantvolt.models.greeks.Greeks",
          "kind": "class",
          "signature": "Greeks(delta: float, gamma: float, vega: float, theta: float, rho: float)",
          "summary": "First-order (and gamma) option sensitivities.",
          "doc": "First-order (and gamma) option sensitivities.\n\nAll fields are per-unit-of-underlying sensitivities. Instances are immutable\nvalue objects; the arithmetic helpers return new ``Greeks`` rather than\nmutating in place.",
          "methods": [
            {
              "name": "scale",
              "signature": "scale(self, factor: float) -> Greeks",
              "summary": "Elementwise multiply by ``factor`` (e.g. a position size or weight)."
            },
            {
              "name": "zero",
              "signature": "zero(cls) -> Greeks",
              "summary": "Additive identity — the natural start value when summing Greeks."
            }
          ],
          "fields": [
            {
              "name": "delta",
              "type": "float",
              "default": null
            },
            {
              "name": "gamma",
              "type": "float",
              "default": null
            },
            {
              "name": "vega",
              "type": "float",
              "default": null
            },
            {
              "name": "theta",
              "type": "float",
              "default": null
            },
            {
              "name": "rho",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/greeks.py",
          "line": 25
        },
        {
          "name": "Hub",
          "module": "quantvolt",
          "qualified": "quantvolt.models.commodity.Hub",
          "kind": "class",
          "signature": "Hub(hub_id: str, exchange: str, price_unit: str)",
          "summary": "Immutable market hub definition with stable ID, display name and country or market area..",
          "doc": "Immutable market hub definition with stable ID, display name and country or market area.",
          "methods": [],
          "fields": [
            {
              "name": "hub_id",
              "type": "str",
              "default": null
            },
            {
              "name": "exchange",
              "type": "str",
              "default": null
            },
            {
              "name": "price_unit",
              "type": "str",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 16
        },
        {
          "name": "ImpliedVolResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.implied_vol.ImpliedVolResult",
          "kind": "class",
          "signature": "ImpliedVolResult(implied_vol: float, moneyness: Moneyness, iteration_count: int, converged: bool)",
          "summary": "Outcome of a premium inversion (design \"Implied Volatility Calculator\").",
          "doc": "Outcome of a premium inversion (design \"Implied Volatility Calculator\").\n\n``iteration_count`` is the number of objective (Black-76 repricing) evaluations\nBrent performed, including the two bracket-endpoint evaluations — the closest\nobservable proxy for the solver's iteration count. This matches\n:func:`scipy.optimize.brentq`'s own evaluation count exactly (verified by\n``test_implied_vol.py::test_iteration_count_matches_scipy_brentq_call_count_exactly``):\n:func:`~quantvolt.numerics.rootfind.brent_root` no longer pre-evaluates the\nendpoints itself before delegating to ``brentq`` (which evaluates them again\ninternally), a redundant pre-check that previously double-counted them and\ninflated this value by exactly 2. ``converged`` is ``True`` whenever a result is\nreturned; non-convergence raises instead of returning a partial result (fail\nloudly, ``coding-style.md`` §7).",
          "methods": [],
          "fields": [
            {
              "name": "implied_vol",
              "type": "float",
              "default": null
            },
            {
              "name": "moneyness",
              "type": "Moneyness",
              "default": null
            },
            {
              "name": "iteration_count",
              "type": "int",
              "default": null
            },
            {
              "name": "converged",
              "type": "bool",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 61
        },
        {
          "name": "InstrumentPriceRecord",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.InstrumentPriceRecord",
          "kind": "class",
          "signature": "InstrumentPriceRecord(instrument_id: str, commodity: CommodityConfig, delivery_period: DeliveryPeriod, price: float)",
          "summary": "An observed price for a commodity over a delivery period.",
          "doc": "An observed price for a commodity over a delivery period.",
          "methods": [],
          "fields": [
            {
              "name": "instrument_id",
              "type": "str",
              "default": null
            },
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "price",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 58
        },
        {
          "name": "InsufficientDataError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.InsufficientDataError",
          "kind": "class",
          "signature": "InsufficientDataError()",
          "summary": "Input data does not satisfy minimum requirements for an operation.",
          "doc": "Input data does not satisfy minimum requirements for an operation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 30
        },
        {
          "name": "LookbackOptionRequest",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.LookbackOptionRequest",
          "kind": "class",
          "signature": "LookbackOptionRequest(option_type: Literal['call', 'put'], strike_type: Literal['floating', 'fixed'], forward: float, sigma: float, time_to_expiry: float, discount_factor: float, strike: float | None = None)",
          "summary": "Inputs for a fixed- or floating-strike lookback option, including observed extrema, volatility, expiry, discounting and notional..",
          "doc": "Inputs for a fixed- or floating-strike lookback option, including observed extrema, volatility, expiry, discounting and notional.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "strike_type",
              "type": "Literal['floating', 'fixed']",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "strike",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 86
        },
        {
          "name": "MarketData",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.valuation.MarketData",
          "kind": "class",
          "signature": "MarketData(forward_curves: dict[str, ForwardCurve], discount_curve: DiscountCurve, valuation_date: date)",
          "summary": "The market inputs needed to value a portfolio (Req 13.2).",
          "doc": "The market inputs needed to value a portfolio (Req 13.2).\n\n``forward_curves`` is defensively copied into a fresh ``dict`` at construction\n(the ``object.__setattr__`` pattern used by ``PricedPosition``), so later mutation\nof the caller's mapping cannot reach into this frozen value object. The stored copy\nis treated as immutable by convention from then on — nothing in the library writes\nto it.",
          "methods": [
            {
              "name": "curve_for",
              "signature": "curve_for(self, commodity_id: str) -> ForwardCurve",
              "summary": "Return the forward curve for ``commodity_id``; raise if absent (Task 61)."
            }
          ],
          "fields": [
            {
              "name": "forward_curves",
              "type": "dict[str, ForwardCurve]",
              "default": null
            },
            {
              "name": "discount_curve",
              "type": "DiscountCurve",
              "default": null
            },
            {
              "name": "valuation_date",
              "type": "date",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/valuation.py",
          "line": 45
        },
        {
          "name": "MissingImbalancePricePolicy",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.MissingImbalancePricePolicy",
          "kind": "class",
          "signature": "MissingImbalancePricePolicy()",
          "summary": "How batch settlement handles absent physical imbalance-price columns.",
          "doc": "How batch settlement handles absent physical imbalance-price columns.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "ERROR",
              "value": "'error'"
            },
            {
              "name": "USE_SPOT",
              "value": "'use_spot'"
            }
          ],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 82
        },
        {
          "name": "MissingTenorError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.MissingTenorError",
          "kind": "class",
          "signature": "MissingTenorError()",
          "summary": "Discount curve or volatility surface does not cover a required date.",
          "doc": "Discount curve or volatility surface does not cover a required date.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 46
        },
        {
          "name": "Moneyness",
          "module": "quantvolt",
          "qualified": "quantvolt.models.vol_surface.Moneyness",
          "kind": "class",
          "signature": "Moneyness()",
          "summary": "Option moneyness relative to the forward (design §3.1).",
          "doc": "Option moneyness relative to the forward (design §3.1).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "ATM",
              "value": "'atm'"
            },
            {
              "name": "OTM",
              "value": "'otm'"
            },
            {
              "name": "ITM",
              "value": "'itm'"
            }
          ],
          "source": "src/quantvolt/models/vol_surface.py",
          "line": 19
        },
        {
          "name": "MonteCarloEvaluation",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.MonteCarloEvaluation",
          "kind": "class",
          "signature": "MonteCarloEvaluation(seed: int, path_count: int, confidence_level: float = 0.95)",
          "summary": "Independent policy-evaluation controls for dispatch LSM.",
          "doc": "Independent policy-evaluation controls for dispatch LSM.",
          "methods": [],
          "fields": [
            {
              "name": "seed",
              "type": "int",
              "default": null
            },
            {
              "name": "path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "confidence_level",
              "type": "float",
              "default": "0.95"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 194
        },
        {
          "name": "MtMPosition",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.mark_to_market.MtMPosition",
          "kind": "class",
          "signature": "MtMPosition(commodity_id: str, delivery_period: DeliveryPeriod, notional: float, trade_price: float, prior_mark_price: float)",
          "summary": "An open position to be marked to market (Req 10.1).",
          "doc": "An open position to be marked to market (Req 10.1).\n\n``prior_mark_price`` is the mark from the previous valuation date and\n``trade_price`` the original contract price. Both may be negative — negative\nenergy prices are real in European markets — but ``notional`` must be\nstrictly positive (validated eagerly at construction).",
          "methods": [],
          "fields": [
            {
              "name": "commodity_id",
              "type": "str",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "trade_price",
              "type": "float",
              "default": null
            },
            {
              "name": "prior_mark_price",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 24
        },
        {
          "name": "MtMPositionResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.mark_to_market.MtMPositionResult",
          "kind": "class",
          "signature": "MtMPositionResult(daily_pnl: float, cumulative_pnl: float, current_mark: float, status: Literal['settled', 'estimated'])",
          "summary": "Per-position mark, P&L pair, and how the mark was sourced (Req 10.1, 10.2).",
          "doc": "Per-position mark, P&L pair, and how the mark was sourced (Req 10.1, 10.2).",
          "methods": [],
          "fields": [
            {
              "name": "daily_pnl",
              "type": "float",
              "default": null
            },
            {
              "name": "cumulative_pnl",
              "type": "float",
              "default": null
            },
            {
              "name": "current_mark",
              "type": "float",
              "default": null
            },
            {
              "name": "status",
              "type": "Literal['settled', 'estimated']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 44
        },
        {
          "name": "MtMResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.mark_to_market.MtMResult",
          "kind": "class",
          "signature": "MtMResult(positions: tuple[MtMPositionResult, ...], estimated_count: int)",
          "summary": "Per-position results in input order plus the count of estimated marks.",
          "doc": "Per-position results in input order plus the count of estimated marks.",
          "methods": [],
          "fields": [
            {
              "name": "positions",
              "type": "tuple[MtMPositionResult, ...]",
              "default": null
            },
            {
              "name": "estimated_count",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 54
        },
        {
          "name": "MultifactorForwardModel",
          "module": "quantvolt",
          "qualified": "quantvolt.curvemodels.multifactor.MultifactorForwardModel",
          "kind": "class",
          "signature": "MultifactorForwardModel(loadings: npt.NDArray[np.float64], dt: float = 1.0 / 12.0)",
          "summary": "Frozen config over factor loadings ``sigma_k(t, T)`` for the §32-33 forward model.",
          "doc": "Frozen config over factor loadings ``sigma_k(t, T)`` for the §32-33 forward model.\n\nAttributes:\n    loadings: ``(n_steps, n_factors, n_tenors)`` ``float64`` array; ``loadings[b, k, j]``\n        is ``sigma_k(t_b, T_j)``, the instantaneous loading of factor ``k`` on tenor\n        (or ``(commodity, month)``) ``j`` over time bucket ``b`` of width ``dt``. Copied\n        and made read-only at construction so the config is genuinely immutable.\n    dt: Uniform time-step ``Delta t`` in years over which each bucket's loadings hold.\n        Defaults to ``1/12`` (monthly, §33). Must be ``> 0``.\n\nThe initial curve ``F(0, T)`` is *not* stored: it is supplied to :func:`simulate_forwards`\nand matched by construction (the dynamics are a driftless-in-``F`` martingale from any\npositive ``F(0, T)``; Property 71). Validation is eager (Req 11.5): 3-D shape with every\naxis non-empty, all-finite loadings, and ``dt > 0``.",
          "methods": [
            {
              "name": "n_steps",
              "signature": "n_steps(self) -> int",
              "summary": "Number of discrete time buckets on the loading grid."
            },
            {
              "name": "n_factors",
              "signature": "n_factors(self) -> int",
              "summary": "Number of common Brownian factors ``K`` (``M`` in §33)."
            },
            {
              "name": "n_tenors",
              "signature": "n_tenors(self) -> int",
              "summary": "Size of the flattened forward state ``D`` (tenors, or ``(commodity, month)``)."
            },
            {
              "name": "from_target_correlation",
              "signature": "from_target_correlation(cls, target_corr: npt.ArrayLike, instantaneous_vols: npt.ArrayLike, *, n_steps: int=1, dt: float=1.0 / 12.0, symmetry_tol: float=_SYMMETRY_TOL, psd_eig_tol: float=_PSD_EIG_TOL, unit_diagonal_tol: float=_UNIT_DIAGONAL_TOL) -> MultifactorForwardModel",
              "summary": "Build loadings whose induced structure reproduces a target correlation (§33.4)."
            }
          ],
          "fields": [
            {
              "name": "loadings",
              "type": "npt.NDArray[np.float64]",
              "default": null
            },
            {
              "name": "dt",
              "type": "float",
              "default": "1.0 / 12.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 105
        },
        {
          "name": "NativeExtensionError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.NativeExtensionError",
          "kind": "class",
          "signature": "NativeExtensionError()",
          "summary": "A requested native Monte Carlo kernel is unavailable in this installation.",
          "doc": "A requested native Monte Carlo kernel is unavailable in this installation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 26
        },
        {
          "name": "NoPricingDataError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.NoPricingDataError",
          "kind": "class",
          "signature": "NoPricingDataError()",
          "summary": "Neither settlement price nor forward curve price is available.",
          "doc": "Neither settlement price nor forward curve price is available.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 38
        },
        {
          "name": "NumericalError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.NumericalError",
          "kind": "class",
          "signature": "NumericalError()",
          "summary": "A numerical kernel's mathematical precondition or convergence condition failed.",
          "doc": "A numerical kernel's mathematical precondition or convergence condition failed.\n\n``ValueError`` is retained as a secondary base for compatibility with callers that use\nthe low-level :mod:`quantvolt.numerics` API directly.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 18
        },
        {
          "name": "PhysicalFactorMapping",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.PhysicalFactorMapping",
          "kind": "class",
          "signature": "PhysicalFactorMapping(index: int, transform: FactorTransform = FactorTransform.IDENTITY, scale: float = 1.0, offset: float = 0.0)",
          "summary": "Map one simulated coordinate to temperature or availability.",
          "doc": "Map one simulated coordinate to temperature or availability.",
          "methods": [
            {
              "name": "values",
              "signature": "values(self, state: Vector) -> Vector",
              "summary": ""
            }
          ],
          "fields": [
            {
              "name": "index",
              "type": "int",
              "default": null
            },
            {
              "name": "transform",
              "type": "FactorTransform",
              "default": "FactorTransform.IDENTITY"
            },
            {
              "name": "scale",
              "type": "float",
              "default": "1.0"
            },
            {
              "name": "offset",
              "type": "float",
              "default": "0.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 167
        },
        {
          "name": "PipelineRight",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.PipelineRight",
          "kind": "class",
          "signature": "PipelineRight(origin: str, destination: str, tariff: float, quantity: float, schedule: DeliverySchedule, direction: TransportDirection = TransportDirection.A_TO_B, loss: float = 0.0, capacity: float | None = None, reverse_tariff: float | None = None)",
          "summary": "A right to move **gas** from origin hub A to destination hub B (Req 24).",
          "doc": "A right to move **gas** from origin hub A to destination hub B (Req 24).\n\nEconomically identical to :class:`TransmissionRight` — same payoff\n``Q_delivered * max(P_B - P_A - T_AB, 0)`` and the same field set — differing\nonly in intent (gas pipeline capacity rather than power transmission). Kept a\ndistinct type so a book never silently conflates power transmission with gas\ntransport; both are priced by the one ``value_transport_right`` engine.\n\nSee :class:`TransmissionRight` for the field semantics.",
          "methods": [],
          "fields": [
            {
              "name": "origin",
              "type": "str",
              "default": null
            },
            {
              "name": "destination",
              "type": "str",
              "default": null
            },
            {
              "name": "tariff",
              "type": "float",
              "default": null
            },
            {
              "name": "quantity",
              "type": "float",
              "default": null
            },
            {
              "name": "schedule",
              "type": "DeliverySchedule",
              "default": null
            },
            {
              "name": "direction",
              "type": "TransportDirection",
              "default": "TransportDirection.A_TO_B"
            },
            {
              "name": "loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "capacity",
              "type": "float | None",
              "default": "None"
            },
            {
              "name": "reverse_tariff",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 196
        },
        {
          "name": "PlantConfig",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.PlantConfig",
          "kind": "class",
          "signature": "PlantConfig(heat_rate: float, variable_om_cost: float, emissions_intensity: float, fuel_type: Literal['gas', 'coal'])",
          "summary": "Thermal-plant conversion parameters.",
          "doc": "Thermal-plant conversion parameters.",
          "methods": [],
          "fields": [
            {
              "name": "heat_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "variable_om_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "emissions_intensity",
              "type": "float",
              "default": null
            },
            {
              "name": "fuel_type",
              "type": "Literal['gas', 'coal']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 117
        },
        {
          "name": "PlantModel",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.plant.PlantModel",
          "kind": "class",
          "signature": "PlantModel(heat_rate: HeatRateCurve, c_min: float, c_max: MaxCapacityCurve, variable_om_cost: float, start_costs: Mapping[StartState, StartCost], ramp_rate: float, d_min: int, d_shutdown: int, d_startup: int, outage_rate: float, hot_max_downtime: int, warm_max_downtime: int, representative_temperatures: tuple[float, ...] = ())",
          "summary": "Operating model of a dispatchable thermal unit (eq. B.1 parameters).",
          "doc": "Operating model of a dispatchable thermal unit (eq. B.1 parameters).\n\nDurations (``d_min``, ``d_shutdown``, ``d_startup``, the ``*_max_downtime``\nthresholds) are counted in dispatch periods — whatever resolution the\ncaller's price/temperature series use.\n\nAttributes:\n    heat_rate: Marginal heat-rate curve ``HR(q, temp)`` (MWh_fuel/MWh_power).\n    c_min: Minimum stable generation while online (MW), ``≥ 0``.\n    c_max: Temperature-dependent maximum capacity ``c_max(temp)`` (MW).\n    variable_om_cost: Variable O&M ``VOM`` per MWh, ``≥ 0``.\n    start_costs: One :class:`StartCost` per :class:`StartState`; all three\n        buckets required.\n    ramp_rate: Ramp rate ``RR`` (MW per period), ``> 0``.\n    d_min: Minimum-run duration (periods) once producing, ``≥ 0``.\n    d_shutdown: Minimum-down duration (periods) before a restart, ``≥ 0``.\n    d_startup: Start-up lag (periods) from the start decision to first\n        production, ``≥ 0``.\n    outage_rate: Forced-outage rate ``λ`` in ``[0, 1)`` (used by the\n        stochastic model; deterministic dispatch assumes full availability).\n    hot_max_downtime: Downtime ``≤`` this keys a ``HOT`` start.\n    warm_max_downtime: Downtime ``≤`` this (but ``>`` hot) keys a ``WARM``\n        start; anything longer keys a ``COLD`` start. Must be ``≥\n        hot_max_downtime``.\n    representative_temperatures: Optional smoke-test temperatures at which\n        ``c_max(temp) ≥ c_min`` and ``HR(c_min, temp) > 0`` are checked\n        eagerly. Empty by default (curve feasibility is then verified only\n        at dispatch time, against the temperatures actually supplied).",
          "methods": [
            {
              "name": "start_state_for_downtime",
              "signature": "start_state_for_downtime(self, downtime: int) -> StartState",
              "summary": "Classify a stopped unit's start-up state from elapsed downtime (periods)."
            },
            {
              "name": "start_cost",
              "signature": "start_cost(self, state: StartState, power_price: float, fuel_price: float) -> float",
              "summary": "Cash cost of one start in ``state``: ``SC + FSC·fuel + PSC·power`` (eq. B.1)."
            },
            {
              "name": "marginal_heat_rate",
              "signature": "marginal_heat_rate(self, output: float, temperature: float) -> float",
              "summary": "``HR(q, temp)`` — the plant's own curve, evaluated for the caller."
            },
            {
              "name": "max_capacity",
              "signature": "max_capacity(self, temperature: float) -> float",
              "summary": "``c_max(temp)`` — the plant's own temperature-dependent ceiling."
            }
          ],
          "fields": [
            {
              "name": "heat_rate",
              "type": "HeatRateCurve",
              "default": null
            },
            {
              "name": "c_min",
              "type": "float",
              "default": null
            },
            {
              "name": "c_max",
              "type": "MaxCapacityCurve",
              "default": null
            },
            {
              "name": "variable_om_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "start_costs",
              "type": "Mapping[StartState, StartCost]",
              "default": null
            },
            {
              "name": "ramp_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "d_min",
              "type": "int",
              "default": null
            },
            {
              "name": "d_shutdown",
              "type": "int",
              "default": null
            },
            {
              "name": "d_startup",
              "type": "int",
              "default": null
            },
            {
              "name": "outage_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "hot_max_downtime",
              "type": "int",
              "default": null
            },
            {
              "name": "warm_max_downtime",
              "type": "int",
              "default": null
            },
            {
              "name": "representative_temperatures",
              "type": "tuple[float, ...]",
              "default": "()"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/plant.py",
          "line": 86
        },
        {
          "name": "Portfolio",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.model.Portfolio",
          "kind": "class",
          "signature": "Portfolio(positions: tuple[Position, ...], name: str | None = None)",
          "summary": "An immutable, iterable Composite of positions — one and many handled uniformly.",
          "doc": "An immutable, iterable Composite of positions — one and many handled uniformly.\n\nSatisfies Req 13.1: an ordered, immutable collection whose positions can be iterated\nand counted without mutation — ``__iter__`` delegates to the underlying tuple in\nconstruction order and ``__len__`` counts without side effects.",
          "methods": [],
          "fields": [
            {
              "name": "positions",
              "type": "tuple[Position, ...]",
              "default": null
            },
            {
              "name": "name",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 77
        },
        {
          "name": "PortfolioSettlement",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.settlement.PortfolioSettlement",
          "kind": "class",
          "signature": "PortfolioSettlement(total_cashflow: float, settled: tuple[SettledPortfolioPosition, ...], unsettled: tuple[Position, ...])",
          "summary": "Realized PPA/hedge cash flow plus positions not handled by this engine.",
          "doc": "Realized PPA/hedge cash flow plus positions not handled by this engine.",
          "methods": [],
          "fields": [
            {
              "name": "total_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "settled",
              "type": "tuple[SettledPortfolioPosition, ...]",
              "default": null
            },
            {
              "name": "unsettled",
              "type": "tuple[Position, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/settlement.py",
          "line": 35
        },
        {
          "name": "PortfolioValuation",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.valuation.PortfolioValuation",
          "kind": "class",
          "signature": "PortfolioValuation(total_npv: float, priced: tuple[PricedPosition, ...], unpriced: tuple[Position, ...])",
          "summary": "Aggregate NPV plus per-position results, in portfolio order (Req 13.2, 13.3).",
          "doc": "Aggregate NPV plus per-position results, in portfolio order (Req 13.2, 13.3).",
          "methods": [],
          "fields": [
            {
              "name": "total_npv",
              "type": "float",
              "default": null
            },
            {
              "name": "priced",
              "type": "tuple[PricedPosition, ...]",
              "default": null
            },
            {
              "name": "unpriced",
              "type": "tuple[Position, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/valuation.py",
          "line": 83
        },
        {
          "name": "Position",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.model.Position",
          "kind": "class",
          "signature": "Position(instrument: Instrument, position_id: str | None = None, tags: tuple[str, ...] = ())",
          "summary": "A single held instrument, plus optional identity/tags. Notional lives on the instrument.",
          "doc": "A single held instrument, plus optional identity/tags. Notional lives on the instrument.",
          "methods": [],
          "fields": [
            {
              "name": "instrument",
              "type": "Instrument",
              "default": null
            },
            {
              "name": "position_id",
              "type": "str | None",
              "default": "None"
            },
            {
              "name": "tags",
              "type": "tuple[str, ...]",
              "default": "()"
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 28
        },
        {
          "name": "PowerDeliveryInterval",
          "module": "quantvolt",
          "qualified": "quantvolt.models.interval.PowerDeliveryInterval",
          "kind": "class",
          "signature": "PowerDeliveryInterval(start_utc: datetime, end_utc: datetime)",
          "summary": "One unambiguous half-open power-delivery interval ``[start_utc, end_utc)``.",
          "doc": "One unambiguous half-open power-delivery interval ``[start_utc, end_utc)``.",
          "methods": [
            {
              "name": "duration_minutes",
              "signature": "duration_minutes(self) -> int",
              "summary": "Exact delivery duration in whole minutes."
            },
            {
              "name": "duration_hours",
              "signature": "duration_hours(self) -> float",
              "summary": "Exact delivery duration in hours, used for MW-to-MWh cash-flow conversion."
            }
          ],
          "fields": [
            {
              "name": "start_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "end_utc",
              "type": "datetime",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/interval.py",
          "line": 26
        },
        {
          "name": "PowerHedgeContract",
          "module": "quantvolt",
          "qualified": "quantvolt.models.power_hedge.PowerHedgeContract",
          "kind": "class",
          "signature": "PowerHedgeContract(hedge_id: str, hedge_type: PowerHedgeType, position: PowerHedgePosition, start_utc: datetime, end_utc: datetime, volume_mwh: float, strike_per_mwh: float, upper_strike_per_mwh: float | None = None, allocated_premium_per_mwh: float = 0.0)",
          "summary": "Terms for one realized, financially settled power hedge.",
          "doc": "Terms for one realized, financially settled power hedge.\n\n``allocated_premium_per_mwh`` is an explicit allocation to each delivery\ninterval, not an option valuation. Long positions pay it and short positions\nreceive it. A long collar owns the floor and writes the cap.",
          "methods": [
            {
              "name": "covers",
              "signature": "covers(self, interval: PowerDeliveryInterval) -> bool",
              "summary": "Whether the complete delivery interval is inside the hedge term."
            }
          ],
          "fields": [
            {
              "name": "hedge_id",
              "type": "str",
              "default": null
            },
            {
              "name": "hedge_type",
              "type": "PowerHedgeType",
              "default": null
            },
            {
              "name": "position",
              "type": "PowerHedgePosition",
              "default": null
            },
            {
              "name": "start_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "end_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "volume_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "strike_per_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "upper_strike_per_mwh",
              "type": "float | None",
              "default": "None"
            },
            {
              "name": "allocated_premium_per_mwh",
              "type": "float",
              "default": "0.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/power_hedge.py",
          "line": 36
        },
        {
          "name": "PowerHedgeDataColumns",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.power_hedge.PowerHedgeDataColumns",
          "kind": "class",
          "signature": "PowerHedgeDataColumns(interval_start_utc: str = 'interval_start_utc', interval_end_utc: str = 'interval_end_utc', spot_price_per_mwh: str = 'spot_price_per_mwh')",
          "summary": "Map caller-owned frame columns to realized hedge inputs.",
          "doc": "Map caller-owned frame columns to realized hedge inputs.",
          "methods": [],
          "fields": [
            {
              "name": "interval_start_utc",
              "type": "str",
              "default": "'interval_start_utc'"
            },
            {
              "name": "interval_end_utc",
              "type": "str",
              "default": "'interval_end_utc'"
            },
            {
              "name": "spot_price_per_mwh",
              "type": "str",
              "default": "'spot_price_per_mwh'"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 30
        },
        {
          "name": "PowerHedgePosition",
          "module": "quantvolt",
          "qualified": "quantvolt.models.power_hedge.PowerHedgePosition",
          "kind": "class",
          "signature": "PowerHedgePosition()",
          "summary": "Payoff ownership; long swap means receive fixed and pay floating.",
          "doc": "Payoff ownership; long swap means receive fixed and pay floating.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "LONG",
              "value": "'long'"
            },
            {
              "name": "SHORT",
              "value": "'short'"
            }
          ],
          "source": "src/quantvolt/models/power_hedge.py",
          "line": 28
        },
        {
          "name": "PowerHedgeSettlement",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.power_hedge.PowerHedgeSettlement",
          "kind": "class",
          "signature": "PowerHedgeSettlement(hedge_id: str, interval: PowerDeliveryInterval, spot_price_per_mwh: float, volume_mwh: float, gross_payoff: float, premium_cashflow: float, net_cashflow: float)",
          "summary": "Auditable realized cash flow for one hedge and delivery interval.",
          "doc": "Auditable realized cash flow for one hedge and delivery interval.",
          "methods": [],
          "fields": [
            {
              "name": "hedge_id",
              "type": "str",
              "default": null
            },
            {
              "name": "interval",
              "type": "PowerDeliveryInterval",
              "default": null
            },
            {
              "name": "spot_price_per_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "volume_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "gross_payoff",
              "type": "float",
              "default": null
            },
            {
              "name": "premium_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "net_cashflow",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 17
        },
        {
          "name": "PowerHedgeType",
          "module": "quantvolt",
          "qualified": "quantvolt.models.power_hedge.PowerHedgeType",
          "kind": "class",
          "signature": "PowerHedgeType()",
          "summary": "Supported realized payoff shapes.",
          "doc": "Supported realized payoff shapes.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "FIXED_PRICE_SWAP",
              "value": "'fixed_price_swap'"
            },
            {
              "name": "CAP",
              "value": "'cap'"
            },
            {
              "name": "FLOOR",
              "value": "'floor'"
            },
            {
              "name": "COLLAR",
              "value": "'collar'"
            }
          ],
          "source": "src/quantvolt/models/power_hedge.py",
          "line": 19
        },
        {
          "name": "PpaContract",
          "module": "quantvolt",
          "qualified": "quantvolt.models.ppa.PpaContract",
          "kind": "class",
          "signature": "PpaContract(contract_id: str, bidding_zone: str, fixed_price_per_mwh: float, start_utc: datetime, end_utc: datetime, volume_basis: PpaVolumeBasis, settlement_type: PpaSettlementType = PpaSettlementType.PHYSICAL, counterparty: str | None = None)",
          "summary": "Producer-side PPA commercial terms.",
          "doc": "Producer-side PPA commercial terms.\n\nThe interval volume is deliberately supplied to settlement rather than\nembedded here: a shaped profile can contain tens of thousands of intervals,\nwhile a pay-as-produced profile is known only after metering.",
          "methods": [
            {
              "name": "covers",
              "signature": "covers(self, interval: PowerDeliveryInterval) -> bool",
              "summary": "Whether the complete interval falls inside the PPA delivery term."
            }
          ],
          "fields": [
            {
              "name": "contract_id",
              "type": "str",
              "default": null
            },
            {
              "name": "bidding_zone",
              "type": "str",
              "default": null
            },
            {
              "name": "fixed_price_per_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "start_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "end_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "volume_basis",
              "type": "PpaVolumeBasis",
              "default": null
            },
            {
              "name": "settlement_type",
              "type": "PpaSettlementType",
              "default": "PpaSettlementType.PHYSICAL"
            },
            {
              "name": "counterparty",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/ppa.py",
          "line": 29
        },
        {
          "name": "PpaDataColumns",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.PpaDataColumns",
          "kind": "class",
          "signature": "PpaDataColumns(interval_start_utc: str = 'interval_start_utc', interval_end_utc: str = 'interval_end_utc', contracted_mwh: str = 'contracted_mwh', metered_generation_mwh: str = 'metered_generation_mwh', spot_price_per_mwh: str = 'spot_price_per_mwh', shortfall_price_per_mwh: str = 'shortfall_price_per_mwh', excess_price_per_mwh: str = 'excess_price_per_mwh', hedge_cashflow: str = 'hedge_cashflow', option_payoff: str = 'option_payoff', option_premium: str = 'option_premium', variable_cost: str = 'variable_cost', transaction_cost: str = 'transaction_cost')",
          "summary": "Map caller-owned column names onto QuantVolt's PPA settlement inputs.",
          "doc": "Map caller-owned column names onto QuantVolt's PPA settlement inputs.",
          "methods": [],
          "fields": [
            {
              "name": "interval_start_utc",
              "type": "str",
              "default": "'interval_start_utc'"
            },
            {
              "name": "interval_end_utc",
              "type": "str",
              "default": "'interval_end_utc'"
            },
            {
              "name": "contracted_mwh",
              "type": "str",
              "default": "'contracted_mwh'"
            },
            {
              "name": "metered_generation_mwh",
              "type": "str",
              "default": "'metered_generation_mwh'"
            },
            {
              "name": "spot_price_per_mwh",
              "type": "str",
              "default": "'spot_price_per_mwh'"
            },
            {
              "name": "shortfall_price_per_mwh",
              "type": "str",
              "default": "'shortfall_price_per_mwh'"
            },
            {
              "name": "excess_price_per_mwh",
              "type": "str",
              "default": "'excess_price_per_mwh'"
            },
            {
              "name": "hedge_cashflow",
              "type": "str",
              "default": "'hedge_cashflow'"
            },
            {
              "name": "option_payoff",
              "type": "str",
              "default": "'option_payoff'"
            },
            {
              "name": "option_premium",
              "type": "str",
              "default": "'option_premium'"
            },
            {
              "name": "variable_cost",
              "type": "str",
              "default": "'variable_cost'"
            },
            {
              "name": "transaction_cost",
              "type": "str",
              "default": "'transaction_cost'"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 90
        },
        {
          "name": "PpaIntervalSettlement",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.PpaIntervalSettlement",
          "kind": "class",
          "signature": "PpaIntervalSettlement(interval: PowerDeliveryInterval, contracted_mwh: float, metered_generation_mwh: float, own_generation_delivered_mwh: float, shortfall_mwh: float, excess_mwh: float, ppa_cashflow: float, spot_cashflow: float, imbalance_cashflow: float, hedge_cashflow: float, option_payoff: float, option_premium: float, variable_cost: float, transaction_cost: float, net_cashflow: float)",
          "summary": "An auditable producer cash-flow ledger for one delivery interval.",
          "doc": "An auditable producer cash-flow ledger for one delivery interval.",
          "methods": [
            {
              "name": "component_sum",
              "signature": "component_sum(self) -> float",
              "summary": "Reconstruct net cash flow from its signed ledger components."
            }
          ],
          "fields": [
            {
              "name": "interval",
              "type": "PowerDeliveryInterval",
              "default": null
            },
            {
              "name": "contracted_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "metered_generation_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "own_generation_delivered_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "shortfall_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "excess_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "ppa_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "spot_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "imbalance_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "hedge_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "option_payoff",
              "type": "float",
              "default": null
            },
            {
              "name": "option_premium",
              "type": "float",
              "default": null
            },
            {
              "name": "variable_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "transaction_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "net_cashflow",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 48
        },
        {
          "name": "PpaNominationCandidate",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationCandidate",
          "kind": "class",
          "signature": "PpaNominationCandidate(contracted_mwh: float, mean_cashflow: float, lower_percentile_cashflow: float, cfar: float, objective_value: float)",
          "summary": "Diagnostics for one candidate constant interval nomination.",
          "doc": "Diagnostics for one candidate constant interval nomination.",
          "methods": [],
          "fields": [
            {
              "name": "contracted_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "mean_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "lower_percentile_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "cfar",
              "type": "float",
              "default": null
            },
            {
              "name": "objective_value",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 50
        },
        {
          "name": "PpaNominationColumns",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationColumns",
          "kind": "class",
          "signature": "PpaNominationColumns(interval_start_utc: str = 'interval_start_utc', interval_end_utc: str = 'interval_end_utc', metered_generation_mwh: str = 'metered_generation_mwh', shortfall_price_per_mwh: str = 'shortfall_price_per_mwh', excess_price_per_mwh: str = 'excess_price_per_mwh')",
          "summary": "Map caller-owned calibration columns to nomination inputs.",
          "doc": "Map caller-owned calibration columns to nomination inputs.",
          "methods": [],
          "fields": [
            {
              "name": "interval_start_utc",
              "type": "str",
              "default": "'interval_start_utc'"
            },
            {
              "name": "interval_end_utc",
              "type": "str",
              "default": "'interval_end_utc'"
            },
            {
              "name": "metered_generation_mwh",
              "type": "str",
              "default": "'metered_generation_mwh'"
            },
            {
              "name": "shortfall_price_per_mwh",
              "type": "str",
              "default": "'shortfall_price_per_mwh'"
            },
            {
              "name": "excess_price_per_mwh",
              "type": "str",
              "default": "'excess_price_per_mwh'"
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 32
        },
        {
          "name": "PpaNominationFit",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationFit",
          "kind": "class",
          "signature": "PpaNominationFit(contract_id: str, calibration_end_utc: datetime, calibration_rows: int, delivery_interval_minutes: int, capacity_mwh_per_interval: float, selected_mwh_per_interval: float, objective: PpaNominationObjective, risk_aversion: float, confidence_level: float, candidates: tuple[PpaNominationCandidate, ...])",
          "summary": "Fitted nomination plus its immutable calibration audit trail.",
          "doc": "Fitted nomination plus its immutable calibration audit trail.",
          "methods": [],
          "fields": [
            {
              "name": "contract_id",
              "type": "str",
              "default": null
            },
            {
              "name": "calibration_end_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "calibration_rows",
              "type": "int",
              "default": null
            },
            {
              "name": "delivery_interval_minutes",
              "type": "int",
              "default": null
            },
            {
              "name": "capacity_mwh_per_interval",
              "type": "float",
              "default": null
            },
            {
              "name": "selected_mwh_per_interval",
              "type": "float",
              "default": null
            },
            {
              "name": "objective",
              "type": "PpaNominationObjective",
              "default": null
            },
            {
              "name": "risk_aversion",
              "type": "float",
              "default": null
            },
            {
              "name": "confidence_level",
              "type": "float",
              "default": null
            },
            {
              "name": "candidates",
              "type": "tuple[PpaNominationCandidate, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 61
        },
        {
          "name": "PpaNominationObjective",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationObjective",
          "kind": "class",
          "signature": "PpaNominationObjective()",
          "summary": "Transparent in-sample criterion used to select the nomination.",
          "doc": "Transparent in-sample criterion used to select the nomination.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "MAX_MEAN_CASHFLOW",
              "value": "'max_mean_cashflow'"
            },
            {
              "name": "MAX_MEAN_MINUS_CFAR",
              "value": "'max_mean_minus_cfar'"
            }
          ],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 24
        },
        {
          "name": "PpaSettlementType",
          "module": "quantvolt",
          "qualified": "quantvolt.models.ppa.PpaSettlementType",
          "kind": "class",
          "signature": "PpaSettlementType()",
          "summary": "Whether the PPA delivers energy or settles only its fixed-for-floating difference.",
          "doc": "Whether the PPA delivers energy or settles only its fixed-for-floating difference.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "PHYSICAL",
              "value": "'physical'"
            },
            {
              "name": "FINANCIAL_CFD",
              "value": "'financial_cfd'"
            }
          ],
          "source": "src/quantvolt/models/ppa.py",
          "line": 21
        },
        {
          "name": "PpaVolumeBasis",
          "module": "quantvolt",
          "qualified": "quantvolt.models.ppa.PpaVolumeBasis",
          "kind": "class",
          "signature": "PpaVolumeBasis()",
          "summary": "How the contracted energy volume is determined for each interval.",
          "doc": "How the contracted energy volume is determined for each interval.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "BASELOAD",
              "value": "'baseload'"
            },
            {
              "name": "SHAPED",
              "value": "'shaped'"
            },
            {
              "name": "PAY_AS_PRODUCED",
              "value": "'pay_as_produced'"
            }
          ],
          "source": "src/quantvolt/models/ppa.py",
          "line": 13
        },
        {
          "name": "PpaWalkForwardResult",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_walk_forward.PpaWalkForwardResult",
          "kind": "class",
          "signature": "PpaWalkForwardResult(fits: tuple[PpaNominationFit, ...], evaluation: pl.DataFrame)",
          "summary": "All fitted windows and the row-level out-of-sample nomination trace.",
          "doc": "All fitted windows and the row-level out-of-sample nomination trace.",
          "methods": [],
          "fields": [
            {
              "name": "fits",
              "type": "tuple[PpaNominationFit, ...]",
              "default": null
            },
            {
              "name": "evaluation",
              "type": "pl.DataFrame",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_walk_forward.py",
          "line": 24
        },
        {
          "name": "PricedPosition",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.model.PricedPosition",
          "kind": "class",
          "signature": "PricedPosition(position: Position, npv: float, delta: dict[tuple[str, DeliveryPeriod], float] = field(default_factory=dict), greeks: Greeks | None = None, reference_prices: dict[tuple[str, DeliveryPeriod], float] = field(default_factory=dict))",
          "summary": "A position after valuation — exactly what RiskEngine and mark_to_market consume.",
          "doc": "A position after valuation — exactly what RiskEngine and mark_to_market consume.\n\nInvariants enforced at construction (eager boundary validation, ``coding-style.md`` §7):\n\n- ``npv`` must be finite. A NaN or ±inf NPV would silently poison every downstream\n  aggregate (portfolio NPV, VaR loss quantiles), so it is rejected here with a\n  :class:`~quantvolt.exceptions.ValidationError` naming ``npv``.\n- ``delta`` is defensively copied: the mapping is snapshot into a fresh ``dict`` at\n  construction, so later mutation of the caller's dict cannot reach into this frozen\n  value object. The stored copy is treated as immutable by convention from then on —\n  nothing in the library writes to it. (``object.__setattr__`` is the sanctioned way\n  to assign inside ``__post_init__`` of a frozen dataclass and works with ``slots``.)\n- ``reference_prices`` is defensively copied the same way. It optionally records the\n  forward price level ``value_portfolio`` observed for each ``delta`` entry's\n  ``(commodity_id, delivery period)`` key, in the same units as that commodity's\n  forward curve. ``RiskEngine.apply_scenario`` needs this to correctly scale a\n  *relative* (fractional) scenario shock into currency P&L\n  (``delta x reference_price x shock`` — see :mod:`quantvolt.risk.scenarios`); a key\n  absent from ``reference_prices`` (including an entirely empty mapping, the default)\n  falls back to a reference price of ``1.0``, preserving the legacy\n  ``delta x shock`` behaviour for hand-built positions that never populate it.",
          "methods": [],
          "fields": [
            {
              "name": "position",
              "type": "Position",
              "default": null
            },
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "delta",
              "type": "dict[tuple[str, DeliveryPeriod], float]",
              "default": "field(default_factory=dict)"
            },
            {
              "name": "greeks",
              "type": "Greeks | None",
              "default": "None"
            },
            {
              "name": "reference_prices",
              "type": "dict[tuple[str, DeliveryPeriod], float]",
              "default": "field(default_factory=dict)"
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 37
        },
        {
          "name": "RateLimitError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.RateLimitError",
          "kind": "class",
          "signature": "RateLimitError()",
          "summary": "Provider rate limit exceeded.",
          "doc": "Provider rate limit exceeded.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 63
        },
        {
          "name": "RiskEngine",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.engine.RiskEngine",
          "kind": "class",
          "signature": "RiskEngine(catalogue: ScenarioCatalogue | None=None)",
          "summary": "Portfolio risk metrics: VaR / CVaR, delta aggregation, stress scenarios (Req 9).",
          "doc": "Portfolio risk metrics: VaR / CVaR, delta aggregation, stress scenarios (Req 9).\n\nA configured service, not a Singleton: it holds the scenario catalogue used to\nresolve named scenarios and nothing else. All methods are pure with respect to\ntheir inputs.",
          "methods": [
            {
              "name": "compute_risk",
              "signature": "compute_risk(self, positions: list[PricedPosition], scenario_matrix: npt.NDArray[np.float64], timeout_seconds: float=60.0, *, confidences: Sequence[float]=DEFAULT_VAR_CONFIDENCES, cvar_confidence: float=DEFAULT_CVAR_CONFIDENCE) -> RiskResult",
              "summary": "Historical-simulation VaR (95/99 by default) and CVaR (97.5 by default)."
            },
            {
              "name": "aggregate_delta",
              "signature": "aggregate_delta(self, positions: list[PricedPosition]) -> DeltaMatrix",
              "summary": "Net delta by commodity x delivery period (Req 9.3)."
            },
            {
              "name": "apply_scenario",
              "signature": "apply_scenario(self, positions: list[PricedPosition], scenario: str | ScenarioShock) -> ScenarioResult",
              "summary": "Apply a named or user-defined stress scenario to the book (Req 9.4)."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 176
        },
        {
          "name": "RiskResult",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.engine.RiskResult",
          "kind": "class",
          "signature": "RiskResult(var_95: float, var_99: float, cvar_975: float, delta_matrix: DeltaMatrix, exclusion_report: list[ExcludedPosition], partial: bool, unprocessed_indices: list[int])",
          "summary": "Portfolio tail-risk output containing VaR and CVaR levels, scenario P&L observations, factor ordering and excluded-position diagnostics..",
          "doc": "Portfolio tail-risk output containing VaR and CVaR levels, scenario P&L observations, factor ordering and excluded-position diagnostics.",
          "methods": [],
          "fields": [
            {
              "name": "var_95",
              "type": "float",
              "default": null
            },
            {
              "name": "var_99",
              "type": "float",
              "default": null
            },
            {
              "name": "cvar_975",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_matrix",
              "type": "DeltaMatrix",
              "default": null
            },
            {
              "name": "exclusion_report",
              "type": "list[ExcludedPosition]",
              "default": null
            },
            {
              "name": "partial",
              "type": "bool",
              "default": null
            },
            {
              "name": "unprocessed_indices",
              "type": "list[int]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 85
        },
        {
          "name": "RiskType",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.RiskType",
          "kind": "class",
          "signature": "RiskType()",
          "summary": "Risk categories for derivatives and physical positions.",
          "doc": "Risk categories for derivatives and physical positions.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "EXECUTION",
              "value": "'execution'"
            },
            {
              "name": "BASIS",
              "value": "'basis'"
            },
            {
              "name": "LIQUIDITY",
              "value": "'liquidity'"
            },
            {
              "name": "CREDIT",
              "value": "'credit'"
            },
            {
              "name": "STORAGE",
              "value": "'storage'"
            },
            {
              "name": "TRANSMISSION",
              "value": "'transmission'"
            }
          ],
          "source": "src/quantvolt/models/instruments.py",
          "line": 46
        },
        {
          "name": "ScenarioCatalogue",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.scenarios.ScenarioCatalogue",
          "kind": "class",
          "signature": "ScenarioCatalogue(extra_scenarios: dict[str, ScenarioShock] | None=None)",
          "summary": "Resolves scenario names to :class:`ScenarioShock` vectors (Req 9.4, 9.7).",
          "doc": "Resolves scenario names to :class:`ScenarioShock` vectors (Req 9.4, 9.7).\n\nA config-holding service over :data:`BUILT_IN_SCENARIOS` — not a Singleton.\nCaller-supplied ``extra_scenarios`` are merged OVER the built-ins (caller\nwins on name collision); neither input dict is mutated, and later mutation\nof ``extra_scenarios`` by the caller does not affect the catalogue.",
          "methods": [
            {
              "name": "get",
              "signature": "get(self, name: str) -> ScenarioShock",
              "summary": "Return the scenario registered under ``name``."
            },
            {
              "name": "names",
              "signature": "names(self) -> list[str]",
              "summary": "All available scenario names, sorted."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/scenarios.py",
          "line": 183
        },
        {
          "name": "ScenarioNotFoundError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.ScenarioNotFoundError",
          "kind": "class",
          "signature": "ScenarioNotFoundError()",
          "summary": "Named scenario is not in the built-in scenario catalogue.",
          "doc": "Named scenario is not in the built-in scenario catalogue.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 50
        },
        {
          "name": "ScenarioResult",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.engine.ScenarioResult",
          "kind": "class",
          "signature": "ScenarioResult(scenario_name: str, total_pnl: float, per_position_pnl: tuple[float, ...])",
          "summary": "Outcome of applying one stress scenario to a book (Req 9.4).",
          "doc": "Outcome of applying one stress scenario to a book (Req 9.4).\n\n``per_position_pnl`` is ordered exactly like the input position list, and\n``total_pnl`` is the plain left-to-right sum of those contributions, so\n``total_pnl == sum(per_position_pnl)`` holds exactly (Property 23).",
          "methods": [],
          "fields": [
            {
              "name": "scenario_name",
              "type": "str",
              "default": null
            },
            {
              "name": "total_pnl",
              "type": "float",
              "default": null
            },
            {
              "name": "per_position_pnl",
              "type": "tuple[float, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 96
        },
        {
          "name": "ScenarioShock",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.scenarios.ScenarioShock",
          "kind": "class",
          "signature": "ScenarioShock(name: str, shocks: dict[ShockKey, float])",
          "summary": "A named vector of relative price shocks.",
          "doc": "A named vector of relative price shocks.\n\n``shocks`` maps ``(commodity_id, period)`` to a relative fractional shock\n(see the module docstring for both conventions). ``period=None`` applies\nthe shock commodity-wide across all delivery periods.",
          "methods": [],
          "fields": [
            {
              "name": "name",
              "type": "str",
              "default": null
            },
            {
              "name": "shocks",
              "type": "dict[ShockKey, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/scenarios.py",
          "line": 46
        },
        {
          "name": "SchwartzSmithParams",
          "module": "quantvolt",
          "qualified": "quantvolt.curvemodels.schwartz_smith.SchwartzSmithParams",
          "kind": "class",
          "signature": "SchwartzSmithParams(kappa: float, sigma_chi: float, sigma_xi: float, mu_xi: float, rho: float, lambda_chi: float, lambda_xi: float)",
          "summary": "Risk-neutral parameters of the two-factor Schwartz-Smith model (§31.1).",
          "doc": "Risk-neutral parameters of the two-factor Schwartz-Smith model (§31.1).\n\nFields match Req 25.1 / design ``SchwartzSmithParams``:\n\n* ``kappa`` — short-factor mean-reversion speed (``> 0``).\n* ``sigma_chi`` — short-factor volatility (``> 0``).\n* ``sigma_xi`` — long-factor volatility (``> 0``).\n* ``mu_xi`` — physical long-term drift of ``xi`` (unconstrained).\n* ``rho`` — instantaneous correlation of the two Brownian factors, ``in (-1, 1)``.\n* ``lambda_chi`` — short-factor risk premium (unconstrained).\n* ``lambda_xi`` — long-factor risk premium (unconstrained).\n\n:attr:`mu_xi_star` = ``mu_xi - lambda_xi`` is the risk-neutral long-term drift that\nenters the forward curve (§31.2).",
          "methods": [
            {
              "name": "mu_xi_star",
              "signature": "mu_xi_star(self) -> float",
              "summary": "Risk-neutral long-term drift ``mu_xi - lambda_xi`` (the drift entering ``A(tau)``)."
            }
          ],
          "fields": [
            {
              "name": "kappa",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma_chi",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma_xi",
              "type": "float",
              "default": null
            },
            {
              "name": "mu_xi",
              "type": "float",
              "default": null
            },
            {
              "name": "rho",
              "type": "float",
              "default": null
            },
            {
              "name": "lambda_chi",
              "type": "float",
              "default": null
            },
            {
              "name": "lambda_xi",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 86
        },
        {
          "name": "SettledPortfolioPosition",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.settlement.SettledPortfolioPosition",
          "kind": "class",
          "signature": "SettledPortfolioPosition(position: Position, ledger: pl.DataFrame, total_cashflow: float)",
          "summary": "One interval-settled position and its immutable aggregate result.",
          "doc": "One interval-settled position and its immutable aggregate result.",
          "methods": [],
          "fields": [
            {
              "name": "position",
              "type": "Position",
              "default": null
            },
            {
              "name": "ledger",
              "type": "pl.DataFrame",
              "default": null
            },
            {
              "name": "total_cashflow",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/settlement.py",
          "line": 23
        },
        {
          "name": "SettlementType",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.SettlementType",
          "kind": "class",
          "signature": "SettlementType()",
          "summary": "How a contract settles at delivery.",
          "doc": "How a contract settles at delivery.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "PHYSICAL",
              "value": "'physical'"
            },
            {
              "name": "FINANCIAL",
              "value": "'financial'"
            }
          ],
          "source": "src/quantvolt/models/instruments.py",
          "line": 24
        },
        {
          "name": "SpreadOptionRequest",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spread_option.SpreadOptionRequest",
          "kind": "class",
          "signature": "SpreadOptionRequest(forward1: float, forward2: float, strike: float, sigma1: float, sigma2: float, correlation: float, time_to_expiry: float, discount_factor: float, notional: float = 1.0)",
          "summary": "Inputs for a call on ``forward1 - forward2 - strike`` (Req 7.1).",
          "doc": "Inputs for a call on ``forward1 - forward2 - strike`` (Req 7.1).",
          "methods": [],
          "fields": [
            {
              "name": "forward1",
              "type": "float",
              "default": null
            },
            {
              "name": "forward2",
              "type": "float",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma1",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma2",
              "type": "float",
              "default": null
            },
            {
              "name": "correlation",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": "1.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 47
        },
        {
          "name": "SpreadOptionResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spread_option.SpreadOptionResult",
          "kind": "class",
          "signature": "SpreadOptionResult(premium: float, delta1: float, delta2: float, vega1: float, vega2: float, correlation_sensitivity: float)",
          "summary": "Premium plus finite-difference sensitivities, all scaled by notional (Req 7.2).",
          "doc": "Premium plus finite-difference sensitivities, all scaled by notional (Req 7.2).\n\n``delta1``/``delta2`` are sensitivities to ``forward1``/``forward2`` exactly as\npassed to :func:`price_spread_option`. :func:`price_spark_spread_option` is the\none exception: it chain-rules ``delta2`` back onto the RAW gas forward it was\ngiven (``request.forward2``, before the internal ``heat_rate`` scaling), so that\n``delta2`` always means \"sensitivity to the underlying commodity forward the\ncaller supplied\" — the same convention :mod:`quantvolt.pricing.tolling` uses when\nit chain-rules a spread option's ``delta2`` onto the raw fuel/EUA forwards.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "delta1",
              "type": "float",
              "default": null
            },
            {
              "name": "delta2",
              "type": "float",
              "default": null
            },
            {
              "name": "vega1",
              "type": "float",
              "default": null
            },
            {
              "name": "vega2",
              "type": "float",
              "default": null
            },
            {
              "name": "correlation_sensitivity",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 62
        },
        {
          "name": "StorageModel",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.storage.StorageModel",
          "kind": "class",
          "signature": "StorageModel(min_inventory: float, max_inventory: float, initial_inventory: float, terminal_inventory: float, injection_rate: RateCurve, withdrawal_rate: RateCurve, injection_cost: float = 0.0, withdrawal_cost: float = 0.0, injection_loss: float = 0.0, withdrawal_loss: float = 0.0, carry_cost: float = 0.0, terminal_penalty: float | None = None)",
          "summary": "Physical + commercial parameters of a gas store (Req 22.1, 22.3).",
          "doc": "Physical + commercial parameters of a gas store (Req 22.1, 22.3).\n\nInventory bounds are time-invariant scalars — the lightest faithful representation;\ntime-varying bounds would be a strictly heavier model with no bearing on the Task-75\nproperties and are deferred until a requirement needs them. Ratchets carry the only\nstate-dependence that matters here, as callables of the current fill level.\n\nAll consistency constraints are validated eagerly in :meth:`__post_init__` (rate-curve\nnon-negativity, which cannot be checked over all inventories for an opaque callable, is\nchecked at every grid level when a valuation runs). Inconsistent bounds raise a\n:class:`~quantvolt.exceptions.ValidationError` naming the offending fields (Req 22.3).\n\nAttributes:\n    min_inventory: Minimum working-gas inventory (volume).\n    max_inventory: Maximum working-gas inventory (volume); must be ``>= min_inventory``.\n    initial_inventory: Inventory entering the horizon; must lie in the bounds and on the\n        grid.\n    terminal_inventory: Target inventory at the horizon end; must lie in the bounds and\n        on the grid.\n    injection_rate: Ratchet ``injection_rate(inventory) -> max working-gas injected this\n        period`` (``>= 0``).\n    withdrawal_rate: Ratchet ``withdrawal_rate(inventory) -> max working-gas withdrawn\n        this period`` (``>= 0``).\n    injection_cost: Variable cost per unit working gas injected (``>= 0``).\n    withdrawal_cost: Variable cost per unit working gas withdrawn (``>= 0``).\n    injection_loss: Fuel-in-kind fraction burned on injection, in ``[0, 1)``.\n    withdrawal_loss: Fuel-in-kind fraction burned on withdrawal, in ``[0, 1)``.\n    carry_cost: Carry/financing cost per unit inventory held per period (``>= 0``).\n    terminal_penalty: If ``None`` the terminal inventory is a hard constraint; otherwise a\n        per-unit penalty (``>= 0``) on the terminal deviation from ``terminal_inventory``.",
          "methods": [
            {
              "name": "working_capacity",
              "signature": "working_capacity(self) -> float",
              "summary": "The full working-gas volume ``max_inventory - min_inventory``."
            }
          ],
          "fields": [
            {
              "name": "min_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "max_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "initial_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "terminal_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "injection_rate",
              "type": "RateCurve",
              "default": null
            },
            {
              "name": "withdrawal_rate",
              "type": "RateCurve",
              "default": null
            },
            {
              "name": "injection_cost",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "withdrawal_cost",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "injection_loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "withdrawal_loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "carry_cost",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "terminal_penalty",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 88
        },
        {
          "name": "SwapContract",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.SwapContract",
          "kind": "class",
          "signature": "SwapContract(commodity: CommodityConfig, fixed_rate: float, floating_index: str, notional: float, schedule: DeliverySchedule, granularity: Granularity = Granularity.MONTHLY)",
          "summary": "Fixed-for-floating swap — OTC, customisable, financial settlement.",
          "doc": "Fixed-for-floating swap — OTC, customisable, financial settlement.",
          "methods": [],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "fixed_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "floating_index",
              "type": "str",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "schedule",
              "type": "DeliverySchedule",
              "default": null
            },
            {
              "name": "granularity",
              "type": "Granularity",
              "default": "Granularity.MONTHLY"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 102
        },
        {
          "name": "SwapPricingResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.swap.SwapPricingResult",
          "kind": "class",
          "signature": "SwapPricingResult(npv: float, delta: tuple[float, ...], rho: float)",
          "summary": "Swap valuation output containing total NPV, one forward delta per schedule period and rho for the documented parallel rate bump..",
          "doc": "Swap valuation output containing total NPV, one forward delta per schedule period and rho for the documented parallel rate bump.",
          "methods": [],
          "fields": [
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "delta",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "rho",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/swap.py",
          "line": 48
        },
        {
          "name": "TollingResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.tolling.TollingResult",
          "kind": "class",
          "signature": "TollingResult(npv: float, intrinsic_value: float, time_value: float, per_period_values: tuple[float, ...], per_period_deltas: dict[str, tuple[float, ...]], aggregate_deltas: dict[str, float])",
          "summary": "Strip-level tolling valuation: NPV decomposition plus per-period detail.",
          "doc": "Strip-level tolling valuation: NPV decomposition plus per-period detail.\n\n``per_period_values`` are the discounted per-period spread-option values in\nschedule order; ``npv`` is their sum. ``per_period_deltas`` and\n``aggregate_deltas`` are keyed ``\"power\"``/``\"fuel\"``/``\"eua\"``, and each\naggregate equals the sum of its per-period tuple exactly (Property 20).",
          "methods": [],
          "fields": [
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "intrinsic_value",
              "type": "float",
              "default": null
            },
            {
              "name": "time_value",
              "type": "float",
              "default": null
            },
            {
              "name": "per_period_values",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "per_period_deltas",
              "type": "dict[str, tuple[float, ...]]",
              "default": null
            },
            {
              "name": "aggregate_deltas",
              "type": "dict[str, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/tolling.py",
          "line": 90
        },
        {
          "name": "TransmissionRight",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.TransmissionRight",
          "kind": "class",
          "signature": "TransmissionRight(origin: str, destination: str, tariff: float, quantity: float, schedule: DeliverySchedule, direction: TransportDirection = TransportDirection.A_TO_B, loss: float = 0.0, capacity: float | None = None, reverse_tariff: float | None = None)",
          "summary": "A right to move **power** from origin hub A to destination hub B (Req 24).",
          "doc": "A right to move **power** from origin hub A to destination hub B (Req 24).\n\nThe per-period payoff to the holder is ``Q_delivered * max(P_B - P_A - T_AB, 0)``\n(§12): buy at the origin ``P_A``, pay the transport tariff ``T_AB``, sell at the\ndestination ``P_B`` — an option exercised only when the locational spread covers\nthe tariff. ``delivered = quantity * (1 - loss)``, further capped by ``capacity``.\n\nFields:\n    origin: commodity_id of hub A (the origin forward curve). Matched against\n        the origin curve's commodity when priced.\n    destination: commodity_id of hub B (the destination forward curve).\n    tariff: per-period transport cost T_AB (>= 0), in the price unit.\n    quantity: per-period available quantity Q (>= 0).\n    schedule: the delivery periods the right covers.\n    direction: A_TO_B (default), B_TO_A, or BIDIRECTIONAL.\n    loss: transmission loss fraction in [0, 1); delivered = Q * (1 - loss).\n    capacity: optional physical cap; effective quantity = min(Q, capacity).\n    reverse_tariff: T_BA (>= 0) for the B->A leg of a BIDIRECTIONAL right;\n        when omitted a bidirectional right reuses ``tariff`` symmetrically.",
          "methods": [],
          "fields": [
            {
              "name": "origin",
              "type": "str",
              "default": null
            },
            {
              "name": "destination",
              "type": "str",
              "default": null
            },
            {
              "name": "tariff",
              "type": "float",
              "default": null
            },
            {
              "name": "quantity",
              "type": "float",
              "default": null
            },
            {
              "name": "schedule",
              "type": "DeliverySchedule",
              "default": null
            },
            {
              "name": "direction",
              "type": "TransportDirection",
              "default": "TransportDirection.A_TO_B"
            },
            {
              "name": "loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "capacity",
              "type": "float | None",
              "default": "None"
            },
            {
              "name": "reverse_tariff",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 157
        },
        {
          "name": "TransportDirection",
          "module": "quantvolt",
          "qualified": "quantvolt.models.instruments.TransportDirection",
          "kind": "class",
          "signature": "TransportDirection()",
          "summary": "Permitted flow direction of a transmission (power) or pipeline (gas) right.",
          "doc": "Permitted flow direction of a transmission (power) or pipeline (gas) right.\n\n``A_TO_B`` / ``B_TO_A`` are one-way rights (origin A -> destination B, or the\nreverse). ``BIDIRECTIONAL`` is a single capacity unit usable in *either*\ndirection per period — the holder commits it to the economically best flow, so\na bidirectional right is worth no more than owning both one-way rights (Property\n68 subadditivity).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "A_TO_B",
              "value": "'a_to_b'"
            },
            {
              "name": "B_TO_A",
              "value": "'b_to_a'"
            },
            {
              "name": "BIDIRECTIONAL",
              "value": "'bidirectional'"
            }
          ],
          "source": "src/quantvolt/models/instruments.py",
          "line": 31
        },
        {
          "name": "TransportRightResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.transmission_right.TransportRightResult",
          "kind": "class",
          "signature": "TransportRightResult(origin: str, destination: str, intrinsic: float, extrinsic: float, total: float, delta_origin: float, delta_destination: float, per_period: tuple[TransportPeriodValue, ...])",
          "summary": "Aggregate transport-right value plus per-period detail (Req 24.1-24.3).",
          "doc": "Aggregate transport-right value plus per-period detail (Req 24.1-24.3).\n\n``intrinsic``/``extrinsic``/``total`` are the sums over ``per_period`` with\n``total == intrinsic + extrinsic``. ``delta_origin``/``delta_destination`` are the\naggregate per-hub deltas (opposite-signed nets), keyed for the portfolio adapter\nby ``origin``/``destination`` commodity ids.",
          "methods": [],
          "fields": [
            {
              "name": "origin",
              "type": "str",
              "default": null
            },
            {
              "name": "destination",
              "type": "str",
              "default": null
            },
            {
              "name": "intrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "extrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "total",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_origin",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_destination",
              "type": "float",
              "default": null
            },
            {
              "name": "per_period",
              "type": "tuple[TransportPeriodValue, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/transmission_right.py",
          "line": 88
        },
        {
          "name": "ValidationError",
          "module": "quantvolt",
          "qualified": "quantvolt.exceptions.ValidationError",
          "kind": "class",
          "signature": "ValidationError()",
          "summary": "Input parameter violates a documented constraint.",
          "doc": "Input parameter violates a documented constraint.\n\n``ValueError`` is retained as a secondary base for conventional Python compatibility.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 11
        },
        {
          "name": "VanillaOptionRequest",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.vanilla.VanillaOptionRequest",
          "kind": "class",
          "signature": "VanillaOptionRequest(option_type: Literal['call', 'put', 'cap', 'floor'], strike: float, notional: float, forward: float, sigma: float, time_to_expiry: float, discount_factor: float)",
          "summary": "Complete Black–76 call or put inputs: type, strike, notional, forward, volatility, time to expiry and discount factor..",
          "doc": "Complete Black–76 call or put inputs: type, strike, notional, forward, volatility, time to expiry and discount factor.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put', 'cap', 'floor']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 28
        },
        {
          "name": "VanillaOptionResult",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.vanilla.VanillaOptionResult",
          "kind": "class",
          "signature": "VanillaOptionResult(premium: float, greeks: Greeks)",
          "summary": "Vanilla option output containing discounted premium and the complete analytical Greeks object..",
          "doc": "Vanilla option output containing discounted premium and the complete analytical Greeks object.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "greeks",
              "type": "Greeks",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 39
        },
        {
          "name": "VolatilitySurface",
          "module": "quantvolt",
          "qualified": "quantvolt.models.vol_surface.VolatilitySurface",
          "kind": "class",
          "signature": "VolatilitySurface(commodity: CommodityConfig, tenors: tuple[VolatilityTenor, ...])",
          "summary": "A commodity's implied-vol term structure, one :class:`VolatilityTenor` per period.",
          "doc": "A commodity's implied-vol term structure, one :class:`VolatilityTenor` per period.\n\nConsistency invariants (validated eagerly in :meth:`__post_init__`):\n\n- ``tenors`` is non-empty.\n- ``tenors`` is strictly increasing by :attr:`VolatilityTenor.period`, so there\n  are no duplicate periods; the surface validates this for itself rather than\n  trusting callers (Tell-Don't-Ask).",
          "methods": [
            {
              "name": "sigma_at",
              "signature": "sigma_at(self, period: DeliveryPeriod) -> float",
              "summary": "Annualised implied vol for an exact ``period`` match."
            }
          ],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "tenors",
              "type": "tuple[VolatilityTenor, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/vol_surface.py",
          "line": 43
        },
        {
          "name": "VolatilityTenor",
          "module": "quantvolt",
          "qualified": "quantvolt.models.vol_surface.VolatilityTenor",
          "kind": "class",
          "signature": "VolatilityTenor(period: DeliveryPeriod, sigma: float)",
          "summary": "A single point on the vol term structure: an implied vol for one delivery period.",
          "doc": "A single point on the vol term structure: an implied vol for one delivery period.\n\n``sigma`` is an annualised implied volatility and is validated eagerly to be\nstrictly positive in :meth:`__post_init__`.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/vol_surface.py",
          "line": 28
        },
        {
          "name": "aggregate_delta",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.aggregation.aggregate_delta",
          "kind": "function",
          "signature": "aggregate_delta(positions: list[PricedPosition]) -> DeltaMatrix",
          "summary": "Net position-level delta by commodity (rows) x delivery period (cols) — Property 22.",
          "doc": "Net position-level delta by commodity (rows) x delivery period (cols) — Property 22.\n\nEach cell is the sum of that ``(commodity, period)`` delta across all positions.\nThe grid is the sorted union of the key sets of every position's ``delta`` mapping:\npositions with an empty ``delta`` contribute nothing, and an empty ``positions``\nlist yields the empty matrix (no rows, no columns). Inputs are never mutated —\ntotals accumulate in a fresh dict and the result is built from new tuples.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/aggregation.py",
          "line": 59
        },
        {
          "name": "apply_ppa_nomination",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_nomination.apply_ppa_nomination",
          "kind": "function",
          "signature": "apply_ppa_nomination(fit: PpaNominationFit, evaluation_data: pl.DataFrame, *, interval_start_column: str='interval_start_utc', interval_end_column: str='interval_end_utc', output_column: str='contracted_mwh') -> pl.DataFrame",
          "summary": "Add the fitted volume to strictly out-of-sample caller observations.",
          "doc": "Add the fitted volume to strictly out-of-sample caller observations.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 204
        },
        {
          "name": "bang_bang",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_approx.bang_bang",
          "kind": "function",
          "signature": "bang_bang(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Bang-bang state aggregation: run at full load or off, {0, c_max} (Req 21.3).",
          "doc": "Bang-bang state aggregation: run at full load or off, {0, c_max} (Req 21.3).\n\nCollapses the online output grid to a single full-load level so the unit is\neither off or running at ``c_max`` — the state aggregation Appendix B recommends\nfor a *sufficiently steep* heat-rate curve, where the optimal load is (almost)\nalways a corner. Implemented by solving the deterministic DP on a derived plant\nwhose ``c_min`` and ``c_max`` are both pinned to that full-load level; every\nother operating characteristic (heat-rate curve, start costs, ramp, durations)\nis unchanged. The input plant is **not** mutated — a new :class:`PlantModel` is\nderived.\n\nFull-load level. With a constant capacity the pinned level *is* ``c_max``. With a\ntemperature-dependent ``c_max(temp)`` the level is the horizon-minimum ``c_max``\n(the largest constant full-output level feasible in every period); a period\nwhose capacity falls below the plant's own ``c_min`` makes the plant infeasible\nthere and is rejected, mirroring the deterministic solver's curve check.\n\nExactness and bias. For a **linear** (constant-marginal) heat rate the per-MWh\nmargin is output-independent, so the exact optimum is a corner and bang-bang is\nexact. For a **steep** (rising-marginal) curve the exact optimum may run at an\nefficient part load that bang-bang cannot represent, so the value is a\n**downward-biased lower bound**: whenever the full-load level is reachable in one\nstep (ramp rate >= operating range) the bang-bang on/off policy set is a strict\nsubset of the exact one, and restricting the load choice can only lose value.\n\nWarning (Req 21.3). Emits :class:`BangBangHedgeWarning`: hedges (sensitivities\nand critical-dispatch surfaces) are far more sensitive than the value itself to\nthe heat-rate-curve approximation, because they read the *slope* of value\nagainst price, which the single on/off kink distorts even where the value error\nis negligible.\n\nArgs:\n    plant: The operating model; a full-load-pinned copy is derived from it.\n    power_prices: Power price ``P_t`` per period.\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period.\n    initial_online: Whether the unit is producing entering the horizon; an\n        online unit is treated as running at the full-load level.\n    initial_output: Ignored when ``initial_online`` (the unit is pinned to full\n        load); retained for signature parity with the deterministic solver.\n    initial_uptime: Producing periods already accrued (min-run).\n    initial_downtime: Offline periods already accrued (start bucket / min-down).\n    output_step: Output-grid spacing (MW); immaterial here (single online level)\n        but validated ``> 0`` by the solver; defaults to the ramp rate.\n    discount_factors: Per-period to-today discount factors (default all 1.0).\n\nReturns:\n    The bang-bang :class:`DispatchSchedule` (outputs are 0 or the full-load\n    level).\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a discount\n        factor or ``output_step`` is non-positive; if ``c_max`` falls below\n        ``c_min`` at some temperature; or if the initial condition admits no\n        feasible schedule (delegated to the deterministic solver).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 325
        },
        {
          "name": "basis",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.basis",
          "kind": "function",
          "signature": "basis(curve_a: ForwardCurve, curve_b: ForwardCurve, start: date, end: date, *, lower_percentile: float=5.0, upper_percentile: float=95.0, ddof: int=0) -> BasisResult",
          "summary": "Locational basis ``price(A) - price(B)`` per period in ``[start, end]`` (Req 2.4).",
          "doc": "Locational basis ``price(A) - price(B)`` per period in ``[start, end]`` (Req 2.4).\n\nThe computation covers the shared delivery periods whose last calendar day\nfalls within the inclusive ``[start, end]`` range; no such period raises\n:class:`InsufficientDataError` naming both commodities and the range rather\nthan returning empty statistics (Property 9). Summary statistics: mean,\nstandard deviation (``ddof=0`` by default — the periods are the whole\npopulation of interest, not a sample), and the ``lower_percentile``/\n``upper_percentile`` (default 5th/95th) via :func:`numpy.percentile`\n(linear interpolation).\n\nArgs:\n    curve_a: First curve of the basis (``A`` in ``A - B``).\n    curve_b: Second curve of the basis.\n    start: Inclusive lower bound on each period's last calendar day.\n    end: Inclusive upper bound; must be ``>= start``.\n    lower_percentile: Percentile reported as ``p5``, in ``[0, 100]``\n        (default 5.0) and strictly below ``upper_percentile``.\n    upper_percentile: Percentile reported as ``p95``, in ``[0, 100]``\n        (default 95.0).\n    ddof: Delta degrees of freedom for :func:`numpy.std`, non-negative\n        (default 0, population standard deviation).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 318
        },
        {
          "name": "build_volatility_surface",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.implied_vol.build_volatility_surface",
          "kind": "function",
          "signature": "build_volatility_surface(option_quotes: list[OptionQuote], interpolation: Literal['linear', 'cubic_spline']='linear', extrapolate: bool=False, *, commodity: CommodityConfig) -> VolatilitySurface",
          "summary": "Build an implied-volatility surface from option quotes (Task 36).",
          "doc": "Build an implied-volatility surface from option quotes (Task 36).\n\nEvery quote is inverted through :func:`implied_vol` (so every quote is fully\nvalidated — a bad quote fails loudly rather than being dropped). Because\n:class:`~quantvolt.models.vol_surface.VolatilitySurface` holds **one sigma per\nperiod tenor** (a term structure), multiple strikes quoted for the same period\nare aggregated to the *ATM-nearest* quote's vol: the quote whose strike is\nclosest to its forward (relative distance; first quote wins a tie). This\nanchors each tenor at the most liquid, smile-neutral point; the smile across\nstrikes is thereby collapsed by nearest-ATM selection.\n\nCalendar months missing between the first and last quoted period are filled by\ninterpolating the vol term structure on a monotone month axis with the selected\nmethod; quoted periods keep their exactly inverted vols. With\n``extrapolate=False`` the surface covers only ``[first, last]`` quoted period.\n\n``commodity`` is required and keyword-only: the stub signature carried no\ncommodity, but :class:`VolatilitySurface` requires one, and guessing a default\nwould silently mislabel the surface — an additive keyword parameter completes\nthe stub without breaking positional callers.\n\nArgs:\n    option_quotes: Non-empty list of :class:`OptionQuote` observations.\n    interpolation: ``\"linear\"`` (piecewise linear) or ``\"cubic_spline\"``\n        (natural cubic spline), selected via a dispatch dict.\n    extrapolate: Must be ``False``; extrapolation beyond the quoted period\n        range is not supported (there is no principled extension target).\n    commodity: The commodity the surface belongs to (keyword-only, required).\n\nReturns:\n    A :class:`VolatilitySurface` with one tenor per calendar month from the\n    first to the last quoted period, inclusive. Inputs are never mutated.\n\nRaises:\n    ValidationError: If ``option_quotes`` is empty, ``interpolation`` is\n        unknown, ``extrapolate`` is ``True``, or any quote fails the\n        :func:`implied_vol` domain / no-arbitrage checks.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 309
        },
        {
          "name": "calendar_spread",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.calendar_spread",
          "kind": "function",
          "signature": "calendar_spread(curve: ForwardCurve, period_early: DeliveryPeriod, period_late: DeliveryPeriod, storage_cost: float=0.0) -> CalendarSpreadResult",
          "summary": "Storage-related calendar spread on one curve (Task 34, Property 44).",
          "doc": "Storage-related calendar spread on one curve (Task 34, Property 44).\n\n``spread = price(period_late) - price(period_early) - storage_cost * months``\nwhere ``months`` is the whole-month distance between the two delivery periods\nand ``storage_cost`` is the cost of carry per month. This is the spread a\nstorage operator captures by injecting in ``period_early`` and withdrawing in\n``period_late``; positive means contango net of carry, negative means\nbackwardation.\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless\n``period_early < period_late`` and ``storage_cost >= 0``; a period absent from\nthe curve raises :class:`~quantvolt.exceptions.MissingTenorError` (via\n:meth:`ForwardCurve.price_at`).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 456
        },
        {
          "name": "calibrate_ppa_nomination",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_nomination.calibrate_ppa_nomination",
          "kind": "function",
          "signature": "calibrate_ppa_nomination(contract: PpaContract, calibration_data: pl.DataFrame, *, calibration_end_utc: datetime, capacity_mwh_per_interval: float, columns: PpaNominationColumns | None=None, objective: PpaNominationObjective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR, risk_aversion: float=1.0, confidence_level: float=0.95, grid_steps: int=100) -> PpaNominationFit",
          "summary": "Fit a constant baseload nomination using calibration observations only.",
          "doc": "Fit a constant baseload nomination using calibration observations only.\n\nCandidate physical cash flow is\n``q*fixed + max(g-q,0)*excess - max(q-g,0)*shortfall``.\nCFaR follows the package convention ``max(mean - lower_percentile, 0)``.\nTies resolve to the smaller nomination, avoiding accidental over-contracting.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 122
        },
        {
          "name": "cash_flow_at_risk",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.cfar.cash_flow_at_risk",
          "kind": "function",
          "signature": "cash_flow_at_risk(cashflow_model: CashFlowModel, scenarios: Sequence[Scenario], horizon: int, seed: int, consistency: Mapping[str, str] | None=None, *, confidence_level: float=0.95) -> CFaRResult",
          "summary": "Compute CFaR plus summary statistics over a factor scenario set (Req 16).",
          "doc": "Compute CFaR plus summary statistics over a factor scenario set (Req 16).\n\nFor every scenario the pure ``cashflow_model`` is called exactly once, its returned\nper-period vector is validated to have length ``horizon`` and aggregated (summed)\ninto one realised aggregate cash flow. Across scenarios this forms the distribution\nof aggregated cash flow, from which the mean, the percentiles, and the\nshortfall-below-expected at ``confidence_level`` are computed. See the module\ndocstring for the request surface, the exact CFaR definition, and the sign\nconvention.\n\nArgs:\n    cashflow_model: Pure callable mapping one scenario to a 1-D per-period\n        cash-flow vector of length ``horizon``. Called once per scenario; never\n        mutated.\n    scenarios: Non-empty exhaustive factor scenario set (market + operational\n        factors keyed by name).\n    horizon: Number of periods, ``>= 1``.\n    seed: Reproducibility seed, echoed on the result (Req 16.3).\n    consistency: Optional market/operational consistency metadata, carried through\n        to the result verbatim (Req 16.2).\n    confidence_level: Confidence level for the ``cfar_95`` / ``p5`` shortfall\n        measure; defaults to ``0.95``, reproducing the 5th-percentile shortfall\n        documented in the module docstring. Must be in ``[0, 1]``. ``p50`` / ``p95``\n        always report the 50th / 95th percentiles regardless of this parameter.\n\nReturns:\n    A :class:`CFaRResult`.\n\nRaises:\n    ValidationError: If ``horizon < 1``; if ``scenarios`` is empty; if\n        ``confidence_level`` is outside ``[0, 1]``; or if the model returns, for\n        any scenario, a vector whose shape is not ``(horizon,)`` — the message\n        names the returned shape, the horizon, and the scenario index (Req 16.4).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/cfar.py",
          "line": 120
        },
        {
          "name": "check_arbitrage",
          "module": "quantvolt",
          "qualified": "quantvolt.curves.arbitrage.check_arbitrage",
          "kind": "function",
          "signature": "check_arbitrage(curve: ForwardCurve, storage_cost: float=0.0, *, eps: float=_ARBITRAGE_EPS) -> list[ArbitrageWarning]",
          "summary": "Return one :class:`ArbitrageWarning` per consecutive pair violating carry.",
          "doc": "Return one :class:`ArbitrageWarning` per consecutive pair violating carry.\n\nThe exact inequality flagged for a consecutive pair ``p_early < p_late`` is::\n\n    price(p_late) < price(p_early) - storage_cost * months_between - eps\n\ni.e. a negative time spread (far below near) steeper than the cost of carry\ncan explain. Returns an empty list when the curve is clean.\n\nArgs:\n    curve: The forward curve to check.\n    storage_cost: Cost of carry per unit per month, non-negative (default\n        0.0: any strict price inversion is flagged).\n    eps: Absolute numerical slack so a spread exactly at the carry bound\n        is treated as clean rather than a floating-point false positive,\n        positive (default ``1e-9``).\n\nRaises:\n    ValidationError: If ``storage_cost`` is negative (or non-finite), or\n        ``eps`` is not strictly positive.\n    ArbitrageError: if any node price is non-finite, so time spreads are\n        undefined and no violation can be attributed to identifiable nodes.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curves/arbitrage.py",
          "line": 70
        },
        {
          "name": "classify_moneyness",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.implied_vol.classify_moneyness",
          "kind": "function",
          "signature": "classify_moneyness(strike: float, forward: float, tolerance_pct: float=2.0) -> Moneyness",
          "summary": "Classify option moneyness relative to the forward price (Property 32).",
          "doc": "Classify option moneyness relative to the forward price (Property 32).\n\nClassification is from the **call perspective**: a strike above the forward has\nno intrinsic value for a call (OTM); a strike below the forward is ITM. The put\nclassification is the mirror image, so callers holding puts should swap\nITM/OTM. Deviations of at most ``tolerance_pct`` percent of the forward — the\nboundary is *inclusive* — classify as ATM:\n\n- ``|strike - forward| / forward * 100 <= tolerance_pct`` -> ATM\n- ``strike > forward * (1 + tolerance_pct/100)`` -> OTM\n- ``strike < forward * (1 - tolerance_pct/100)`` -> ITM\n\nArgs:\n    strike: Option strike (``K``), positive.\n    forward: Forward price of the underlying (``F``), positive.\n    tolerance_pct: ATM band half-width as a percentage of the forward,\n        non-negative (default 2.0 = within 2% of the forward).\n\nReturns:\n    Exactly one of :class:`Moneyness` ``ATM`` / ``OTM`` / ``ITM``.\n\nRaises:\n    ValidationError: If ``strike`` or ``forward`` is not positive, or\n        ``tolerance_pct`` is negative.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 197
        },
        {
          "name": "clean_spread",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.clean_spread",
          "kind": "function",
          "signature": "clean_spread(spread: SpreadResult, eua_curve: ForwardCurve, emissions_intensity: float) -> CleanSpreadResult",
          "summary": "Deduct the carbon cost from an uncleaned spark or dark spread (Req 2.2).",
          "doc": "Deduct the carbon cost from an uncleaned spark or dark spread (Req 2.2).\n\nDecorator intent as a plain function: wraps one :class:`SpreadResult` and adds\nthe carbon cost, per period: ``cleaned = spread - emissions_intensity *\nEUA_price``. The result keeps the input's ``spread_type``, so cleaning a spark\nspread yields the clean spark spread and cleaning a dark spread the clean dark\nspread — call once per uncleaned spread to obtain both (Property 7).\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless\n``emissions_intensity >= 0``, and :class:`InsufficientDataError` when\n``eua_curve`` lacks any of the spread's delivery periods (Req 2.5) — no\npartial result is returned.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 247
        },
        {
          "name": "compare_cashflow_strategies",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.cashflow_metrics.compare_cashflow_strategies",
          "kind": "function",
          "signature": "compare_cashflow_strategies(data: pl.DataFrame, cashflow_columns: Mapping[str, str], *, benchmark: str, confidence_level: float=0.95) -> CashflowStrategyComparison",
          "summary": "Compare caller-supplied periodic cash flows using one consistent convention.",
          "doc": "Compare caller-supplied periodic cash flows using one consistent convention.\n\nCFaR is ``max(mean - lower percentile, 0)``. Positive reduction fields mean\nlower risk than the benchmark; positive total difference means more cash flow.\nNo annualization is performed because the function does not guess observation\nfrequency.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/cashflow_metrics.py",
          "line": 51
        },
        {
          "name": "crack_spread",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.crack_spread",
          "kind": "function",
          "signature": "crack_spread(product_curves: dict[str, ForwardCurve], crude_curve: ForwardCurve, ratio: tuple[int, ...]=(3, 2, 1)) -> CrackSpreadResult",
          "summary": "Refining margin per delivery period for an ``input:outputs`` crack ratio.",
          "doc": "Refining margin per delivery period for an ``input:outputs`` crack ratio.\n\nConvention: ``ratio[0]`` is the number of crude (input) units and ``ratio[1:]``\nthe product (output) units, matched to ``product_curves`` in insertion order —\nthe default 3:2:1 means 3 crude → 2 of the first product + 1 of the second.\nPer period, over the shared delivery periods of *all* curves::\n\n    spread = (Σᵢ product_priceᵢ * ratio[1 + i] - crude_price * ratio[0]) / ratio[0]\n\ni.e. the margin normalised per unit of crude. For the standard 3:2:1 and 5:3:2\ncracks the output units sum to the input units, so the product weights sum to 1\n(Property 42).\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless ``product_curves``\nis non-empty, ``len(ratio) == len(product_curves) + 1`` and every ratio entry\nis > 0; raises :class:`InsufficientDataError` when no delivery period is common\nto the crude curve and every product curve.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 378
        },
        {
          "name": "credit_var",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.credit_var.credit_var",
          "kind": "function",
          "signature": "credit_var(positions: Sequence[PricedPosition], transition: Mapping[str, npt.ArrayLike], exposures: Mapping[str, float] | None=None, recovery: float | Mapping[str, float]=0.4, seed: int=0, *, path_count: int=100000, asset_correlation: float=0.2, confidences: Sequence[float]=DEFAULT_CONFIDENCES) -> CreditVaRResult",
          "summary": "Compute Credit VaR and expected credit loss over the priced book (Req 17).",
          "doc": "Compute Credit VaR and expected credit loss over the priced book (Req 17).\n\nCounterparty-less positions are set aside as credit-risk-free; every credit-bearing\ncounterparty's default event is drawn jointly with a shared systematic market factor\nvia a one-factor Gaussian copula, and the path loss is the sum of ``LGD * EAD`` over\nthat path's defaulted counterparties. See the module docstring for the request surface,\nthe copula construction, the EAD/LGD conventions, the sign convention, and the\nlimitations.\n\nArgs:\n    positions: The priced book; each position's counterparty is read from its\n        instrument (``ForwardContract.counterparty``; missing / ``None`` -> risk-free).\n    transition: Per-counterparty one-period migration row (last state = default;\n        entries in ``[0, 1]``; sums to ``1`` within ``1e-9``).\n    exposures: Optional per-counterparty exposure; where absent, exposure is the\n        net (summed) NPV of that counterparty's positions. EAD is floored at zero.\n    recovery: Recovery rate in ``[0, 1]``, scalar or per-counterparty. ``LGD = 1 - r``.\n    seed: RNG seed (``>= 0``); results are reproducible under it (Req 17.3).\n    path_count: Number of Monte Carlo paths (``>= 1``).\n    asset_correlation: Copula systematic-factor loading ``rho in [0, 1]``.\n    confidences: The two credit-VaR confidence levels (fractions in ``(0, 1)``,\n        matching :mod:`quantvolt.risk.parametric_var`'s convention) reported as\n        ``credit_var_95`` / ``credit_var_99``; defaults to ``(0.95, 0.99)``.\n\nReturns:\n    A :class:`CreditVaRResult`.\n\nRaises:\n    ValidationError: If ``seed < 0``, ``path_count < 1``, ``asset_correlation`` or any\n        recovery is outside ``[0, 1]``, a transition row has an out-of-range probability\n        or does not sum to 1 within ``1e-9`` (message names the counterparty), a\n        supplied exposure is non-finite, a credit-bearing counterparty has no\n        transition row (message names the counterparty) (Req 17.4), or\n        ``confidences`` does not contain exactly 2 strictly ascending levels in\n        ``(0, 1)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/credit_var.py",
          "line": 207
        },
        {
          "name": "dark_spread",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.dark_spread",
          "kind": "function",
          "signature": "dark_spread(power_curve: ForwardCurve, fuel_curve: ForwardCurve, heat_rate: float, variable_cost: float, emissions_cost: float) -> SpreadResult",
          "summary": "Dark spread (coal-fired generation margin) per shared delivery period.",
          "doc": "Dark spread (coal-fired generation margin) per shared delivery period.\n\nSame formula and validation as :func:`spark_spread` with a coal ``fuel_curve``;\nthe result is labelled ``\"dark\"``. It is a separate immutable object, so\ncomputing it never modifies any spark values (Req 2.1, Property 6).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 229
        },
        {
          "name": "delta_gamma_var",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.parametric_var.delta_gamma_var",
          "kind": "function",
          "signature": "delta_gamma_var(deltas: NDArray[np.float64], gamma: NDArray[np.float64], cov: NDArray[np.float64], confidences: Sequence[float]=DEFAULT_CONFIDENCES, method: str='cornish_fisher', *, psd_tol: float=_PSD_TOL, symmetry_rtol: float=_SYMMETRY_RTOL) -> ParametricVaRResult",
          "summary": "Second-order (delta-gamma) parametric VaR via moment matching (Req 14.2, Property 48).",
          "doc": "Second-order (delta-gamma) parametric VaR via moment matching (Req 14.2, Property 48).\n\nThe quadratic P&L ``ΔP = δᵀΔf + ½·Δfᵀ Γ Δf`` with ``Δf ~ N(0, Σ)`` has, writing\n``Θ = Γ Σ``, the standard delta-gamma-normal cumulants (Britten-Jones & Schaefer,\n\"Non-linear Value-at-Risk\", 1999, eqs. 6-8; Zangari, RiskMetrics Monitor 1996;\nverified here against Monte Carlo):\n\n* ``κ₁ = ½·tr(Θ)`` — mean;\n* ``κ₂ = δᵀΣδ + ½·tr(Θ²)`` — variance;\n* ``κ₃ = 3·δᵀΣΓΣδ + tr(Θ³)`` — third cumulant.\n\nThe loss ``L = -ΔP`` has mean ``-κ₁``, standard deviation ``√κ₂`` and skewness\n``-κ₃/κ₂^1.5``; its ``c``-quantile is ``VaR_c = -κ₁ + √κ₂ · w(z_c, -γ₁)`` where ``w``\nis the third-order Cornish-Fisher map ``w = z + (z²-1)/6·γ₁`` (dispatched by\n``method``). With ``Γ = 0`` all higher cumulants vanish and this collapses **exactly**\nto :func:`parametric_var` (Property 48).\n\nSign sanity: a long-gamma book (``Γ`` positive definite) has ``κ₁ > 0`` (the quadratic\nterm only ever adds to P&L) and positive P&L skewness, so both the mean shift and the\nskewness correction *reduce* VaR relative to the delta-only figure — the expected\ndirection.\n\nArgs:\n    deltas: Portfolio delta by risk factor, a 1-D vector of length ``n``.\n    gamma: The ``n x n`` gamma matrix ``Γ``; must be square, symmetric, and conformable\n        with ``deltas`` — but need **not** be PSD (a book may be long some gammas and\n        short others).\n    cov: The ``n x n`` factor covariance ``Σ`` (validated square/symmetric/PSD).\n    confidences: Confidence levels; defaults to ``(0.95, 0.99)``.\n    method: Delta-gamma quantile method; defaults to ``\"cornish_fisher\"``. Must be a\n        registered method (currently only ``\"cornish_fisher\"``).\n    psd_tol: Absolute tolerance on the smallest eigenvalue of ``Σ`` used by the PSD\n        check; defaults to ``1e-8``.\n    symmetry_rtol: Relative tolerance (against the matrix scale) for the symmetry\n        checks on ``Σ`` and ``Γ``; defaults to ``1e-8``.\n\nReturns:\n    A :class:`ParametricVaRResult` carrying ``method`` and the P&L cumulant moments\n    ``(κ₁, κ₂, κ₃/κ₂^1.5)``.\n\nRaises:\n    ValidationError: on any dimension, symmetry, PSD, confidence, or unknown-``method``\n        violation, naming the offending quantity.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/parametric_var.py",
          "line": 292
        },
        {
          "name": "dispatch_deterministic",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_deterministic.dispatch_deterministic",
          "kind": "function",
          "signature": "dispatch_deterministic(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Solve the perfect-foresight optimal dispatch of ``plant`` (eq. B.1).",
          "doc": "Solve the perfect-foresight optimal dispatch of ``plant`` (eq. B.1).\n\nExact backward-induction DP over a discretised commitment/output state (see\nthe module docstring for the objective, the state space, the discretisation\nand its exactness, and the unit-commitment conventions). All inputs are\nvalidated before any computation and never mutated.\n\nArgs:\n    plant: The operating model (heat-rate curve, capacities, start costs,\n        ramp rate, durations).\n    power_prices: Power price ``P_t`` per period (may be negative).\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period (drives ``HR`` and\n        ``c_max``).\n    initial_online: Whether the unit is producing entering the horizon.\n    initial_output: Output entering the horizon (MW); must be on the grid\n        when ``initial_online`` (ignored otherwise).\n    initial_uptime: Producing periods already accrued (min-run); defaults to\n        \"min-run already satisfied\". Only used when ``initial_online``.\n    initial_downtime: Periods already offline (keys the first start's bucket\n        and min-down); must be ``>= 1`` (a unit \"not online\" has been offline for\n        at least one period); defaults to a long, cold, restart-ready downtime.\n        Only used when not ``initial_online``.\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    discount_factors: Per-period discount factors (default all 1.0).\n\nReturns:\n    The optimal :class:`DispatchSchedule`; ``total_value`` is the\n    perfect-foresight upper bound of Property 62.\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a\n        discount factor or ``output_step`` is non-positive; if\n        ``c_max(temp) < c_min`` or ``heat_rate(q, temp) ≤ 0`` at a supplied\n        temperature; if ``initial_output`` is off-grid while online; if\n        ``initial_downtime < 1`` while offline; or if the supplied initial\n        condition admits no feasible schedule.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_deterministic.py",
          "line": 298
        },
        {
          "name": "dispatch_value",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_sdp.dispatch_value",
          "kind": "function",
          "signature": "dispatch_value(plant: PlantModel, factor_model: DispatchFactorModel, *, method: str='lsm', seed: int, path_count: int=4096, output_step: float | None=None, availability: Sequence[float] | None=None, discount_factors: Sequence[float] | None=None, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, evaluation: MonteCarloEvaluation | None=None, antithetic: bool=True, regression_basis_degree: int=2) -> DispatchResult",
          "summary": "Value ``plant`` under uncertainty by stochastic DP (eqs. B.2-B.3; Req 21.1-21.2).",
          "doc": "Value ``plant`` under uncertainty by stochastic DP (eqs. B.2-B.3; Req 21.1-21.2).\n\nSolves the Bellman recursion over the deterministic module's commitment state\nmachine, under the risk-adjusted expectation carried by ``factor_model``\n(Req 21.5). See the module docstring for the state machine, the on-peak /\noff-peak Markov split (Req 21.6), the risk-adjusted-drift requirement, the\nforced-outage seam, and the critical-surface representation. All inputs are\nvalidated before any computation and never mutated.\n\nArgs:\n    plant: The operating model (heat-rate curve, capacities, start costs,\n        ramp rate, durations).\n    factor_model: Risk-adjusted factor dynamics and the per-period peak /\n        temperature context (also fixes the horizon ``H``).\n    method: ``\"lsm\"`` (least-squares Monte Carlo) or ``\"tree\"`` (recombining\n        lattice); selected via a dispatch table.\n    seed: Monte Carlo / lattice seed (Req 11.2 determinism); ``>= 0``.\n    path_count: Simulated paths for ``\"lsm\"`` (ignored by ``\"tree\"``); ``>= 1``.\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    availability: Optional per-period forced-outage multiplier ``M`` in\n        ``(0, 1]`` (length ``H``) derating ``c_max``; ``None`` = full\n        availability. A caller may source it from\n        :meth:`OutageDataset.forced_outage_multiplier`.\n    discount_factors: Per-period to-today discount factors (default all 1.0).\n    initial_online: Whether the unit is producing entering the horizon.\n    initial_output: Output entering the horizon (MW); on-grid when online.\n    initial_uptime: Producing periods already accrued (min-run).\n    initial_downtime: Periods already offline (start bucket / min-down); must be\n        ``>= 1`` when not ``initial_online`` (delegated to the reused\n        :func:`~quantvolt.assets.dispatch_deterministic._initial_state`).\n    evaluation: Independent LSM policy-evaluation sample. By default, the fitted\n        policy is evaluated on ``path_count`` fresh paths using ``seed + 1``.\n    antithetic: Whether ``\"lsm\"``'s simulated paths use antithetic variates\n        (default ``True``, matching prior behaviour); ignored by ``\"tree\"``\n        (the lattice has no simulation). Also selects the pair-mean-aware\n        standard-error estimator used for ``evaluation_standard_error``\n        (:class:`DispatchDiagnostics`).\n    regression_basis_degree: Degree of the polynomial regression basis used by\n        ``\"lsm\"``'s continuation-value fit (default ``2``: intercept, linears,\n        squares, pairwise cross terms -- the historical basis); ignored by\n        ``\"tree\"``. Must be ``>= 1``.\n\nReturns:\n    The :class:`DispatchResult` (value + eq. B.5 critical surfaces).\n\nRaises:\n    ValidationError: If ``method`` is unknown; if ``factor_model.drift`` is not\n        risk-adjusted (Req 21.5); if ``path_count`` / ``seed`` /\n        ``discount_factors`` / ``availability`` / ``regression_basis_degree`` are\n        out of range or mis-sized; if a plant curve is infeasible at a supplied\n        temperature; if ``initial_downtime < 1`` while offline; or if the initial\n        condition admits no feasible schedule.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 1120
        },
        {
          "name": "ewma_covariance",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.covariance.ewma_covariance",
          "kind": "function",
          "signature": "ewma_covariance(returns: NDArray[np.float64], lam: float=0.94, *, psd_tol: float=_PSD_TOL) -> NDArray[np.float64]",
          "summary": "RiskMetrics exponentially-weighted covariance forecast (eq. U10.1).",
          "doc": "RiskMetrics exponentially-weighted covariance forecast (eq. U10.1).\n\nIterates the recursion ``Σ_t = λ·Σ_{t-1} + (1-λ)·r_t·r_tᵀ`` over the rows of\n``returns`` (oldest first) and returns the final ``Σ`` — the one-step-ahead covariance\nforecast. Following the RiskMetrics convention the returns are treated as zero-mean\ninnovations (no centring). The recursion is **initialised from the first observation's\nouter product** ``Σ_0 = r_0·r_0ᵀ``; because each update is a convex combination of\nrank-1 PSD outer products, every ``Σ_t`` — and hence the result — is PSD by\nconstruction.\n\nArgs:\n    returns: ``(n_obs, n_assets)`` array of periodic returns, oldest row first.\n    lam: RiskMetrics decay factor in the open interval ``(0, 1)``; the default\n        ``0.94`` is the RiskMetrics daily value.\n    psd_tol: Absolute tolerance on the smallest eigenvalue of the resulting\n        covariance forecast when asserting positive semidefiniteness; defaults to\n        ``1e-8``.\n\nReturns:\n    The symmetric PSD ``(n_assets, n_assets)`` covariance forecast.\n\nRaises:\n    ValidationError: if ``lam`` is not in ``(0, 1)``; if ``returns`` is not a 2-D\n        array with at least 2 observations and 1 asset; if it holds non-finite\n        values; or if the result fails the PSD check within ``psd_tol``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/covariance.py",
          "line": 112
        },
        {
          "name": "forward_spread",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.forward_spread",
          "kind": "function",
          "signature": "forward_spread(power_curve: ForwardCurve, fuel_curve: ForwardCurve, heat_rate: float, variable_cost: float, emissions_cost: float) -> SpreadResult",
          "summary": "Forward spark spread over the curve intersection, for forward price risk.",
          "doc": "Forward spark spread over the curve intersection, for forward price risk.\n\nThe formula is identical to :func:`spark_spread` — forward power minus\nheat-rate-weighted forward fuel minus costs — differing only in time-horizon\ninterpretation, so this delegates to it and returns the same ``\"spark\"``\n-labelled :class:`SpreadResult` (design §2.4, Property 43).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 439
        },
        {
          "name": "futures_delta",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.futures.futures_delta",
          "kind": "function",
          "signature": "futures_delta(contract: FuturesContract | ForwardContract, forward_curve: ForwardCurve, valuation_date: date, discount_curve: DiscountCurve, bump: float=1.0, *, settlement_lag_days: int=0) -> float",
          "summary": "Delta of the contract NPV to the forward price: ``discount_factor * notional``.",
          "doc": "Delta of the contract NPV to the forward price: ``discount_factor * notional``.\n\nThe NPV is linear in the forward price, so this closed form is exact — it is\nwhat a central finite difference at ``forward_price ± bump`` would compute for\nany ``bump > 0`` (up to floating-point round-off), without repricing twice or\nlooking up the forward price at all.\n\nArgs:\n    contract: The futures or forward contract to price.\n    forward_curve: Must have a node for ``contract.delivery_period``.\n    valuation_date: The date NPV is computed as of.\n    discount_curve: Must cover the settlement date.\n    bump: Retained for signature compatibility with the historical\n        finite-difference form and still validated as strictly positive;\n        unused in the closed-form computation itself.\n    settlement_lag_days: Calendar days added to the delivery period's last\n        day to get the settlement date, matching :func:`price_futures` so\n        price and delta agree (default 0, non-negative).\n\nRaises:\n    ValidationError: If ``bump`` is not strictly positive, or\n        ``settlement_lag_days`` is negative.\n    ExpiredContractError: If the delivery period ended strictly before\n        ``valuation_date`` (Req 3.3).\n    MissingTenorError: If ``forward_curve`` has no node for the delivery period\n        or ``discount_curve`` does not cover the settlement date (Req 3.4).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/futures.py",
          "line": 110
        },
        {
          "name": "garch11_covariance",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.covariance.garch11_covariance",
          "kind": "function",
          "signature": "garch11_covariance(returns: NDArray[np.float64], *, psd_tol: float=_PSD_TOL) -> NDArray[np.float64]",
          "summary": "Diagonal GARCH(1,1) + constant-conditional-correlation covariance forecast.",
          "doc": "Diagonal GARCH(1,1) + constant-conditional-correlation covariance forecast.\n\nEstimator (Bollerslev 1990 CCC-GARCH), per the design §2.16 (eqs. U10.2-U10.3):\n\n1. **De-mean** each asset column to obtain innovations ``u_j``.\n2. **Fit** a univariate GARCH(1,1)\n   ``h_{j,t} = omega_j + alpha_j·u²_{j,t-1} + beta_j·h_{j,t-1}`` to each column by\n   Gaussian MLE (:func:`_fit_garch11`), enforcing ``omega_j > 0``, ``alpha_j >= 0``,\n   ``beta_j >= 0``, ``alpha_j + beta_j < 1``.\n3. **Standardise** the residuals ``e_{j,t} = u_{j,t} / √h_{j,t}`` and take their sample\n   correlation matrix ``R`` as the constant conditional correlation.\n4. **Forecast** each asset's one-step-ahead conditional variance\n   ``h_{j,T+1} = omega_j + alpha_j·u²_{j,T} + beta_j·h_{j,T}`` and assemble\n   ``Sigma = D·R·D`` with ``D = diag(√h_{j,T+1})``.\n\n``Σ`` is PSD because ``R`` (a sample correlation matrix) is PSD and ``D·R·D`` is a\ncongruence transform with a real diagonal.\n\nArgs:\n    returns: ``(n_obs, n_assets)`` array of periodic returns, oldest row first. A long\n        series is needed for a meaningful fit.\n    psd_tol: Absolute tolerance on the smallest eigenvalue of the resulting\n        covariance forecast when asserting positive semidefiniteness; defaults to\n        ``1e-8``.\n\nReturns:\n    The symmetric PSD ``(n_assets, n_assets)`` covariance forecast.\n\nRaises:\n    ValidationError: if ``returns`` is not a valid finite 2-D array with at least 2\n        observations; if any per-asset series is degenerate; if any GARCH fit fails\n        to converge or violates ``omega > 0, alpha >= 0, beta >= 0, alpha + beta < 1``\n        (the message names the offending asset and constraint); or if the result\n        fails the PSD check within ``psd_tol``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/covariance.py",
          "line": 234
        },
        {
          "name": "horizon_divide",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_approx.horizon_divide",
          "kind": "function",
          "signature": "horizon_divide(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], sub_horizon: int, *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Horizon-division heuristic: solve independent sub-horizons and sum (Req 21.3).",
          "doc": "Horizon-division heuristic: solve independent sub-horizons and sum (Req 21.3).\n\nThe horizon is cut into consecutive sub-horizons of length ``sub_horizon`` (the\nlast may be shorter) that are solved *independently* by the deterministic DP and\nconcatenated; ``total_value`` is the sum of the sub-values. This is the weekly /\nmonthly sub-period heuristic that keeps each solve small.\n\nBoundary-state approximation. Only the **first** sub-horizon sees the caller's\ninitial condition; every later sub-horizon restarts from a cold, restart-ready\n*offline* state. Dropping the true carried-over commitment state is exactly what\ndecouples the subproblems — and is the approximation. It is **exact** when the\nperiods decouple (zero start costs and non-binding min-run / min-down / ramp),\nbecause the dispatch is then myopic and the start-up state is immaterial. It\n**typically understates** value otherwise (each boundary can pay a spurious\nrestart cost), but it *can* overstate value when a binding min-run / min-down\nconstraint that would span a boundary in the full solve is artificially relaxed\nby the cut.\n\nArgs:\n    plant: The operating model (unchanged; passed to each sub-solve).\n    power_prices: Power price ``P_t`` per period.\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period.\n    sub_horizon: Periods per sub-horizon; must be an integer ``>= 1``.\n    initial_online: Whether the unit is producing entering the *first*\n        sub-horizon.\n    initial_output: Output entering the first sub-horizon (MW); on the grid when\n        online.\n    initial_uptime: Producing periods already accrued entering the first\n        sub-horizon (min-run).\n    initial_downtime: Offline periods already accrued entering the first\n        sub-horizon (start bucket / min-down).\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    discount_factors: Per-period to-today discount factors (default all 1.0);\n        sliced per sub-horizon.\n\nReturns:\n    The concatenated full-horizon :class:`DispatchSchedule`; ``total_value`` is\n    the sum of the sub-horizon values.\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a discount\n        factor or ``output_step`` is non-positive; if ``sub_horizon`` is not an\n        integer ``>= 1``; or if any sub-problem is infeasible (delegated to the\n        deterministic solver).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 218
        },
        {
          "name": "implied_heat_rate",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.implied_heat_rate",
          "kind": "function",
          "signature": "implied_heat_rate(power_curve: ForwardCurve, gas_curve: ForwardCurve, anomaly_range: tuple[float, float] | None=None) -> ImpliedHeatRateResult",
          "summary": "Implied heat rate ``power_price / gas_price`` per shared period (Req 2.3).",
          "doc": "Implied heat rate ``power_price / gas_price`` per shared period (Req 2.3).\n\nValidation is eager and complete before any computation: every shared period's\ngas price must be strictly positive; the first violation raises\n:class:`~quantvolt.exceptions.ValidationError` identifying that delivery period\nand no heat rate is computed (Property 8). When ``anomaly_range=(lo, hi)`` is\nsupplied (requiring ``lo < hi``), periods whose implied heat rate falls\n*strictly outside* the inclusive ``[lo, hi]`` band are flagged in\n``anomalous``; without a range no period is flagged.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 281
        },
        {
          "name": "implied_vol",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.implied_vol.implied_vol",
          "kind": "function",
          "signature": "implied_vol(option_type: Literal['call', 'put'], market_premium: float, forward: float, strike: float, time_to_expiry: float, discount_factor: float, tol: float=0.0001, max_iter: int=100, *, sigma_lower: float=_SIGMA_LOWER, sigma_upper: float=_SIGMA_UPPER, tolerance_pct: float=2.0) -> ImpliedVolResult",
          "summary": "Recover the Black-76 volatility implied by a market premium (Property 31).",
          "doc": "Recover the Black-76 volatility implied by a market premium (Property 31).\n\nRound-trip contract (Property 31): ``implied_vol`` applied to\n``black76_price(sigma0, ...)`` recovers ``sigma0`` within ``tol``. Inversion uses\nBrent over ``[sigma_lower, sigma_upper]`` (default ``[1e-9, 10.0]``) — a bracketing\nsolver, so it cannot diverge near zero vega the way Newton-Raphson would (design\n§2.7). The inversion is performed locally with :func:`brent_root` and a\ncall-counting objective (instead of delegating to\n:func:`~quantvolt.numerics.black76.black76_implied_vol`) so that\n:attr:`ImpliedVolResult.iteration_count` can be reported — the kernel does not\nexpose its iteration count. Both use the same bracket, objective, and tolerance.\n\nNo-arbitrage precondition (Req 5.3), checked before inversion:\n\n- call: ``DF*max(F-K, 0) < market_premium < DF*F``\n- put:  ``DF*max(K-F, 0) < market_premium < DF*K``\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    market_premium: Observed (discounted) option premium to invert, positive.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    time_to_expiry: Time to expiry in years (``T``), positive.\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n    tol: Absolute tolerance on the recovered volatility, positive.\n    max_iter: Maximum Brent iterations, at least 1.\n    sigma_lower: Lower end of the Brent search bracket, positive and strictly\n        below ``sigma_upper`` (default ``1e-9``, matching the kernel's bracket).\n    sigma_upper: Upper end of the Brent search bracket, strictly above\n        ``sigma_lower`` (default ``10.0``).\n    tolerance_pct: ATM band half-width (percent of the forward) passed through to\n        :func:`classify_moneyness` for the reported moneyness (default 2.0).\n\nReturns:\n    An :class:`ImpliedVolResult` with the recovered vol, the moneyness of the\n    quote (at ``tolerance_pct``, default 2% ATM tolerance), the\n    objective-evaluation count, and ``converged=True``.\n\nRaises:\n    ValidationError: If any input violates its domain, or if ``market_premium``\n        lies outside the no-arbitrage bounds (no volatility can reproduce it).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 83
        },
        {
          "name": "linear_cross_hedge",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.variance_min.linear_cross_hedge",
          "kind": "function",
          "signature": "linear_cross_hedge(rho: float, sigma_target: float, sigma_hedge: float) -> float",
          "summary": "Linear two-asset cross-commodity hedge ratio ``rho·sigma_t/sigma_h`` (eq 10.22, Req 18.2).",
          "doc": "Linear two-asset cross-commodity hedge ratio ``rho·sigma_t/sigma_h`` (eq 10.22, Req 18.2).\n\nThe optimal local variance-minimizing hedge of one forward (the target, with\nvolatility ``sigma_t``) with another (the hedge instrument, volatility ``sigma_h``)\nwhen the two follow jointly arithmetic Brownian motions with correlation\n``rho`` (eq 10.21). For a linear product the hedge is constant in ``rho``, ``sigma_t``\nand ``sigma_h``. This is the one-instrument special case of\n:func:`variance_min_hedge`: with ``Σ_hh = [[sigma_h²]]`` and\n``Σ_ht = [rho·sigma_t·sigma_h]``, ``Σ_hh⁻¹ Σ_ht = rho·sigma_t/sigma_h``.\n\nArgs:\n    rho: Correlation between the target and hedge returns, in ``(-1, 1)``.\n    sigma_target: Volatility ``sigma_t`` of the target, strictly positive.\n    sigma_hedge: Volatility ``sigma_h`` of the hedge instrument, strictly positive.\n\nReturns:\n    The hedge ratio ``rho·sigma_t/sigma_h``.\n\nRaises:\n    ValidationError: If ``rho`` is not in ``(-1, 1)`` or either volatility is\n        not strictly positive.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/variance_min.py",
          "line": 129
        },
        {
          "name": "mark_to_market",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.mark_to_market.mark_to_market",
          "kind": "function",
          "signature": "mark_to_market(positions: list[MtMPosition], market_date: date, settlement_prices: dict[tuple[str, DeliveryPeriod], float], forward_curve: ForwardCurve | None=None) -> MtMResult",
          "summary": "Mark each position to market and compute daily and cumulative P&L (Req 10).",
          "doc": "Mark each position to market and compute daily and cumulative P&L (Req 10).\n\n``market_date`` documents the as-of date of the marks: ``settlement_prices``\n(and ``forward_curve``, if given) are the caller's pricing data for that date.\nAll marks come solely from these inputs — the function reads no clock and keeps\nno state — so identical inputs always produce an identical result (Req 10.5).\n\nEach position's ``current_mark`` is resolved by ordered fallback: the\nsettlement price for ``(commodity_id, delivery_period)``; else the node of a\nsame-commodity ``forward_curve``, flagged ``\"estimated\"``; else\n:class:`NoPricingDataError`. P&L is then computed identically for settled and\nestimated marks (Req 10.1):\n\n- ``daily_pnl = (current_mark - prior_mark_price) * notional``\n- ``cumulative_pnl = (current_mark - trade_price) * notional``\n\nResults are returned in input order; ``estimated_count`` is the number of\npositions whose status is ``\"estimated\"``. An empty book yields an empty\nresult. Inputs are never mutated.\n\nRaises:\n    NoPricingDataError: If neither a settlement price nor a same-commodity\n        forward-curve node is available for a position's ``(commodity_id,\n        delivery_period)`` (Req 10.3).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 90
        },
        {
          "name": "monte_carlo_var",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.mc_var.monte_carlo_var",
          "kind": "function",
          "signature": "monte_carlo_var(positions: Sequence[Position], factor_model: FactorModel, physical_drift: TaggedDrift, holding_period: float, path_count: int, seed: int, *, confidences: Sequence[float]=DEFAULT_CONFIDENCES, cvar_confidence: float=DEFAULT_CVAR_CONFIDENCE, antithetic: bool=_ANTITHETIC, bootstrap_replicates: int=_BOOTSTRAP_REPLICATES, min_path_count: int=_MIN_PATH_COUNT) -> McVaRResult",
          "summary": "Full-revaluation Monte Carlo VaR/CVaR over a holding period (Req 15).",
          "doc": "Full-revaluation Monte Carlo VaR/CVaR over a holding period (Req 15).\n\nSee the module docstring for the request surface, the factor flattening convention,\nthe simulation/revaluation mechanics, the sign convention, and the standard-error\nestimator. In short: simulate correlated GBM forward scenarios to the horizon under\nthe physical drift, fully revalue the book on each path, and take loss quantiles.\n\nArgs:\n    positions: raw held instruments (repriced from their definition each path).\n    factor_model: base market state + GBM dynamics over the factor grid.\n    physical_drift: required, measure-tagged per-factor log-drift rates.\n    holding_period: risk horizon (> 0), in ``sigma``'s time unit.\n    path_count: simulated paths (``>= min_path_count``).\n    seed: reproducibility seed.\n    confidences: The two VaR confidence levels (fractions in ``(0, 1)``, matching\n        :mod:`quantvolt.risk.parametric_var`'s convention) reported as ``var_95`` /\n        ``var_99``; defaults to ``(0.95, 0.99)``.\n    cvar_confidence: The CVaR confidence level (a fraction in ``(0, 1)``) reported\n        as ``cvar_975``; defaults to ``0.975``.\n    antithetic: Whether the simulation uses antithetic-variate path pairing;\n        defaults to ``False`` (iid paths). The bootstrap SE estimator resamples\n        individual paths when ``False`` and whole ``(+eps, -eps)`` pairs when\n        ``True``, so both modes yield consistent SE estimates — see the module\n        docstring.\n    bootstrap_replicates: Number of bootstrap resamples for the quantile standard\n        errors; defaults to ``500``. Must be an integer ``>= 2`` (a sample standard\n        deviation across replicates needs at least 2 of them).\n    min_path_count: Minimum accepted ``path_count`` (Req 15.5); defaults to\n        ``1000``.\n\nReturns:\n    A :class:`McVaRResult` with VaR/CVaR at the requested confidence levels\n    (reported as ``var_95``/``var_99``/``cvar_975`` regardless of the levels used)\n    and bootstrap SEs.\n\nRaises:\n    ValidationError: if ``path_count < min_path_count`` (raised *before* simulating,\n        Req 15.5); if ``holding_period <= 0``; if ``physical_drift`` is not tagged\n        physical (Req 15.2); if ``physical_drift.values`` does not match the factor\n        count; if any current forward is not strictly positive (GBM requires\n        ``F_0 > 0``); if ``confidences`` does not contain exactly 2 strictly\n        ascending levels in ``(0, 1)``; if ``cvar_confidence`` is not in ``(0, 1)``;\n        if ``bootstrap_replicates`` is not an integer ``>= 2`` (a standard deviation\n        needs at least 2 replicates); or if ``min_path_count`` is not ``>= 1``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/mc_var.py",
          "line": 362
        },
        {
          "name": "parametric_var",
          "module": "quantvolt",
          "qualified": "quantvolt.risk.parametric_var.parametric_var",
          "kind": "function",
          "signature": "parametric_var(deltas: NDArray[np.float64], cov: NDArray[np.float64], confidences: Sequence[float]=DEFAULT_CONFIDENCES, *, psd_tol: float=_PSD_TOL, symmetry_rtol: float=_SYMMETRY_RTOL) -> ParametricVaRResult",
          "summary": "First-order (delta) parametric VaR ``VaR_c = z_c·√(δᵀΣδ)`` (Req 14.1, Property 47).",
          "doc": "First-order (delta) parametric VaR ``VaR_c = z_c·√(δᵀΣδ)`` (Req 14.1, Property 47).\n\nValidates all inputs before any arithmetic (Req 14.4): ``deltas`` is a finite 1-D\nvector; ``cov`` is square, symmetric (within ``symmetry_rtol``), conformable with\n``deltas`` (a mismatch names both dimensions), and positive semidefinite within\n``psd_tol`` (a violation names the offending smallest eigenvalue). See the module\ndocstring for the sign convention, the z-score policy, and the fast PSD test.\n\nArgs:\n    deltas: Portfolio delta by risk factor, a 1-D vector of length ``n``.\n    cov: The ``n x n`` factor covariance forecast ``Σ`` over the loss horizon\n        (e.g. from :mod:`quantvolt.risk.covariance`).\n    confidences: Confidence levels; defaults to ``(0.95, 0.99)``. Each must be in\n        ``(0, 1)``; ``0.95`` / ``0.99`` use the mandated constants ``1.645`` / ``2.326``.\n    psd_tol: Absolute tolerance on the smallest eigenvalue of ``Σ`` used by the PSD\n        check; defaults to ``1e-8`` (the design's documented tolerance, Req 14.4).\n    symmetry_rtol: Relative tolerance (against the matrix scale) for the symmetry\n        check on ``Σ``; defaults to ``1e-8``.\n\nReturns:\n    A :class:`ParametricVaRResult` with ``method=\"delta\"`` and a zero-mean,\n    zero-skew P&L description (``pnl_variance = δᵀΣδ``).\n\nRaises:\n    ValidationError: on any dimension, symmetry, PSD, or confidence violation, naming\n        the offending quantity.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/parametric_var.py",
          "line": 235
        },
        {
          "name": "power_cap_payoff",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.power_cap_payoff",
          "kind": "function",
          "signature": "power_cap_payoff(spot_price: float, strike: float, volume_mwh: float) -> float",
          "summary": "Realised long-cap payoff ``max(spot - strike, 0) * volume``.",
          "doc": "Realised long-cap payoff ``max(spot - strike, 0) * volume``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 31
        },
        {
          "name": "power_floor_payoff",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.power_floor_payoff",
          "kind": "function",
          "signature": "power_floor_payoff(spot_price: float, strike: float, volume_mwh: float) -> float",
          "summary": "Realised long-floor payoff ``max(strike - spot, 0) * volume``.",
          "doc": "Realised long-floor payoff ``max(strike - spot, 0) * volume``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 39
        },
        {
          "name": "price_asian",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.price_asian",
          "kind": "function",
          "signature": "price_asian(request: AsianOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, time_bump: float=_TIME_BUMP, averaging_points: int=_MC_AVERAGING_POINTS) -> ExoticOptionResult",
          "summary": "Price an average-price Asian option on a forward (Req 6.1).",
          "doc": "Price an average-price Asian option on a forward (Req 6.1).\n\nMethod dispatch (Simple Factory): ``request.method`` if given, otherwise the\naveraging-type default — Turnbull-Wakeman for ``\"arithmetic\"``, Kemna-Vorst for\n``\"geometric\"``. Each closed form prices exactly one averaging type, so an explicit\nmethod that contradicts ``request.averaging`` is rejected rather than silently\nrepriced (fail loudly, coding-style.md §7). ``\"monte_carlo\"`` must be requested\nexplicitly and additionally requires ``seed`` and ``path_count >= 1000``.\n\nClosed forms return central finite-difference Greeks of the selected kernel; the\nMonte Carlo path returns ``Greeks.zero()`` (MC Greeks arrive with the Rust engine,\nTask 59) plus the kernel's ``standard_error``.\n\nArgs:\n    request: Fully specified Asian option; validated eagerly before any\n        computation (Req 6.4).\n    forward_bump_fraction: Relative forward bump used for the closed-form\n        delta/gamma finite differences, positive (default ``1e-4``). Unused\n        for ``method=\"monte_carlo\"``.\n    vol_bump: Absolute vol bump for the closed-form vega finite difference,\n        positive (default ``1e-4``). Unused for ``method=\"monte_carlo\"``.\n    time_bump: Absolute time bump for the closed-form theta finite\n        difference, positive (default ``1e-6``). Unused for\n        ``method=\"monte_carlo\"``.\n    averaging_points: Number of discrete fixings in the Monte Carlo averaging\n        schedule, at least 1 (default 252, one trading year of daily\n        fixings). Unused for the closed forms (continuous averaging).\n\nReturns:\n    Premium, Greeks, and — for Monte Carlo only — the standard error.\n\nRaises:\n    ValidationError: If ``forward``, ``strike``, ``sigma`` or ``time_to_expiry``\n        is not > 0, ``discount_factor`` is outside ``(0, 1]``, ``method``\n        contradicts ``averaging``, ``forward_bump_fraction``/``vol_bump``/\n        ``time_bump`` is not > 0, ``averaging_points`` < 1, or — for\n        ``method=\"monte_carlo\"`` — ``seed`` is missing or ``path_count`` < 1000.\n    NativeExtensionError: If ``method=\"monte_carlo\"`` is requested without a\n        built native Rust extension.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 301
        },
        {
          "name": "price_barrier",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.price_barrier",
          "kind": "function",
          "signature": "price_barrier(request: BarrierOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, time_bump: float=_TIME_BUMP) -> ExoticOptionResult",
          "summary": "Price a single-barrier option via the Reiner-Rubinstein closed form (Req 6.2).",
          "doc": "Price a single-barrier option via the Reiner-Rubinstein closed form (Req 6.2).\n\nBarrier-vs-forward consistency (Property 17): an *up* barrier must sit strictly\nabove the forward and a *down* barrier strictly below — a barrier on the wrong\nside (or exactly at the forward) is already breached at inception and is rejected\nbefore any computation. Greeks are central finite differences of the barrier\nkernel.\n\nArgs:\n    request: Fully specified barrier option; validated eagerly before any\n        computation (Req 6.4).\n    forward_bump_fraction: Relative forward bump for delta/gamma, positive\n        (default ``1e-4``).\n    vol_bump: Absolute vol bump for vega, positive (default ``1e-4``).\n    time_bump: Absolute time bump for theta, positive (default ``1e-6``).\n\nReturns:\n    Premium and Greeks (``standard_error`` is ``None`` for closed forms).\n\nRaises:\n    ValidationError: If ``forward``, ``strike``, ``barrier``, ``sigma`` or\n        ``time_to_expiry`` is not > 0, ``discount_factor`` is outside ``(0, 1]``,\n        ``forward_bump_fraction``/``vol_bump``/``time_bump`` is not > 0, or\n        ``barrier`` is on the wrong side of ``forward`` for ``barrier_type``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 372
        },
        {
          "name": "price_cap_floor",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.vanilla.price_cap_floor",
          "kind": "function",
          "signature": "price_cap_floor(request: CapFloorRequest, *, max_strip_periods: int=_MAX_STRIP_PERIODS) -> CapFloorResult",
          "summary": "Price a cap/floor as a strip of independently priced caplets/floorlets.",
          "doc": "Price a cap/floor as a strip of independently priced caplets/floorlets.\n\nComposite intent (Req 5.6, Property 16): each period is priced through\n:func:`price_vanilla_option` with its own forward, volatility,\ntime-to-expiry, discount factor and notional; the result carries both the\nper-period results and their plain sums (aggregate premium via ``sum``,\naggregate Greeks via ``Greeks.__add__`` from ``Greeks.zero()``), so the\naggregate equals the sum of the per-period values exactly.\n\nConsistency rule: each caplet's own ``option_type`` must price on the same\ncall/put side as the strip — ``\"call\"``/``\"cap\"`` labels inside a ``\"cap\"``\nstrip, ``\"put\"``/``\"floor\"`` inside a ``\"floor\"`` strip. A mismatched\ncaplet is rejected with a :class:`ValidationError` rather than silently\nrepriced as the strip side (fail loudly, coding-style.md §7).\n\nStrike/notional consistency (Req 5.6): a cap/floor strip has ONE strike\n(the cap/floor rate) and ONE notional; per Req 5.6 only ``forward``,\n``discount_factor`` and ``time_to_expiry`` vary caplet-by-caplet. Every\ncaplet's own ``strike`` and ``notional`` fields (each caplet is a full\n:class:`VanillaOptionRequest`, so it structurally carries them) must\ntherefore equal ``request.strike`` / ``request.notional`` exactly; a\ndivergent caplet is rejected with a :class:`ValidationError` naming the\ncaplet index rather than silently pricing on its own (ignored) values.\n\nArgs:\n    request: The strip; validated eagerly — including the strip-length\n        cap — before any pricing.\n    max_strip_periods: Maximum number of caplets/floorlets in the strip,\n        at least 1 (default 120, Req 5.6).\n\nReturns:\n    Aggregate premium/Greeks plus the per-period results, ordered as the\n    input caplets.\n\nRaises:\n    ValidationError: If ``strike`` or ``notional`` is not > 0,\n        ``max_strip_periods`` < 1, ``caplets`` is empty or exceeds\n        ``max_strip_periods``, a caplet's ``option_type`` is on the wrong\n        side for the strip, a caplet's ``strike``/``notional`` diverges\n        from the strip's (naming the caplet index), or any caplet fails\n        the :func:`price_vanilla_option` domain checks.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 117
        },
        {
          "name": "price_futures",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.futures.price_futures",
          "kind": "function",
          "signature": "price_futures(contract: FuturesContract | ForwardContract, forward_curve: ForwardCurve, valuation_date: date, discount_curve: DiscountCurve, *, settlement_lag_days: int=0) -> FuturesPricingResult",
          "summary": "Price a futures or forward contract against a forward curve (Req 3.1, 3.2).",
          "doc": "Price a futures or forward contract against a forward curve (Req 3.1, 3.2).\n\n``NPV = discount_factor(settlement_date) * (forward_price - contract_price) * notional``\nwith a positive notional meaning long; ``delta`` is :func:`futures_delta` at the\ndefault bump. ``settlement_date`` is the delivery period's last day plus\n``settlement_lag_days`` calendar days.\n\nArgs:\n    contract: The futures or forward contract to price.\n    forward_curve: Must have a node for ``contract.delivery_period``.\n    valuation_date: The date NPV is computed as of.\n    discount_curve: Must cover the settlement date.\n    settlement_lag_days: Calendar days added to the delivery period's last\n        day to get the settlement date used for the discount factor\n        (default 0, non-negative).\n\nRaises:\n    ValidationError: If ``settlement_lag_days`` is negative.\n    ExpiredContractError: If the delivery period ended strictly before\n        ``valuation_date`` (Req 3.3).\n    MissingTenorError: If ``forward_curve`` has no node for the delivery period\n        or ``discount_curve`` does not cover the settlement date (Req 3.4).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/futures.py",
          "line": 65
        },
        {
          "name": "price_lookback",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.exotic.price_lookback",
          "kind": "function",
          "signature": "price_lookback(request: LookbackOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, time_bump: float=_TIME_BUMP) -> ExoticOptionResult",
          "summary": "Price a lookback option on a forward (Req 6.3).",
          "doc": "Price a lookback option on a forward (Req 6.3).\n\nStrike-type dispatch: ``\"floating\"`` prices via Goldman-Sosin-Gatto and must carry\n``strike=None`` (the strike *is* the running extreme); ``\"fixed\"`` prices via\nConze-Viswanathan and requires a positive ``strike``. Greeks are central finite\ndifferences of the selected kernel.\n\nArgs:\n    request: Fully specified lookback option; validated eagerly before any\n        computation (Req 6.4).\n    forward_bump_fraction: Relative forward bump for delta/gamma, positive\n        (default ``1e-4``).\n    vol_bump: Absolute vol bump for vega, positive (default ``1e-4``).\n    time_bump: Absolute time bump for theta, positive (default ``1e-6``).\n\nReturns:\n    Premium and Greeks (``standard_error`` is ``None`` for closed forms).\n\nRaises:\n    ValidationError: If ``forward``, ``sigma`` or ``time_to_expiry`` is not > 0,\n        ``discount_factor`` is outside ``(0, 1]``,\n        ``forward_bump_fraction``/``vol_bump``/``time_bump`` is not > 0, a\n        floating-strike request carries a ``strike``, or a fixed-strike request\n        is missing a positive ``strike``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 500
        },
        {
          "name": "price_spark_spread_option",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spread_option.price_spark_spread_option",
          "kind": "function",
          "signature": "price_spark_spread_option(request: SpreadOptionRequest, heat_rate: float, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, correlation_bump: float=_CORRELATION_BUMP) -> SpreadOptionResult",
          "summary": "Price a spark spread: a call on ``F_power - heat_rate * F_gas - strike`` (Req 7.3).",
          "doc": "Price a spark spread: a call on ``F_power - heat_rate * F_gas - strike`` (Req 7.3).\n\n``request.forward1`` is the power forward and ``request.forward2`` the RAW gas\nforward. The gas-leg notional is ``notional_power x heat_rate``, realised by\ntransforming the request to ``forward2 * heat_rate`` (``sigma2`` unchanged: a\nconstant multiple of a lognormal forward keeps the same lognormal volatility)\nand delegating to :func:`price_spread_option`. ``forward_bump_fraction``/\n``vol_bump``/``correlation_bump`` are passed through unchanged.\n\n``delta2`` convention (Req 7.2): the transformed request's ``delta2`` is the\nsensitivity to the SCALED gas forward (``heat_rate x F_gas``); this function\nchain-rules it back onto the raw ``F_gas`` the caller passed\n(``delta2_raw = delta2_transformed x heat_rate``), so ``delta2`` always means\n\"sensitivity to the underlying commodity forward the caller supplied\" — the\nsame convention :mod:`quantvolt.pricing.tolling` uses for its fuel/EUA deltas.\n\nRaises:\n    ValidationError: If ``heat_rate`` is not > 0, or the (transformed)\n        request violates any :func:`price_spread_option` constraint.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 201
        },
        {
          "name": "price_spread_option",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spread_option.price_spread_option",
          "kind": "function",
          "signature": "price_spread_option(request: SpreadOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, correlation_bump: float=_CORRELATION_BUMP) -> SpreadOptionResult",
          "summary": "Price a spread call and its sensitivities (Req 7.1, 7.2).",
          "doc": "Price a spread call and its sensitivities (Req 7.1, 7.2).\n\n``strike == 0.0`` prices via Margrabe's exact formula, any other strike via\nKirk's approximation (Property 18). The premium is the kernel premium\nscaled by ``request.notional``; the five sensitivities are central finite\ndifferences of the same kernel, likewise notional-scaled (module docstring\nlists the bump sizes).\n\nArgs:\n    request: Fully specified spread-option request; validated eagerly\n        before any computation.\n    forward_bump_fraction: Relative forward bump for delta1/delta2,\n        positive (default ``1e-4``).\n    vol_bump: Absolute vol bump for vega1/vega2, positive (default\n        ``1e-4``).\n    correlation_bump: Absolute correlation bump for\n        ``correlation_sensitivity``, positive (default ``1e-4``); clamped\n        so ``correlation +/- bump`` stays strictly inside ``(-1, 1)``.\n\nRaises:\n    ValidationError: If ``correlation`` is outside ``(-1, 1)`` (Req 7.4),\n        any of ``forward1``, ``forward2``, ``sigma1``, ``sigma2``,\n        ``time_to_expiry``, ``notional`` is not > 0, ``strike`` < 0,\n        ``discount_factor`` is outside ``(0, 1]``, or\n        ``forward_bump_fraction``/``vol_bump``/``correlation_bump`` is not\n        > 0.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 119
        },
        {
          "name": "price_swap",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.swap.price_swap",
          "kind": "function",
          "signature": "price_swap(swap: SwapContract, forward_curve: ForwardCurve, discount_curve: DiscountCurve, *, day_count: Callable[[date, date], float]=actual_365, settlement_lag_days: int=0, rate_bump: float=_BASIS_POINT) -> SwapPricingResult",
          "summary": "Price a fixed-for-floating swap: NPV, per-period delta, and rho (Req 4.1-4.3).",
          "doc": "Price a fixed-for-floating swap: NPV, per-period delta, and rho (Req 4.1-4.3).\n\nSee the module docstring for the cash-flow (payer-of-fixed / receiver-of-floating)\nand rho (per-bp parallel shift of the continuously compounded zero rate) conventions.\n\nArgs:\n    swap: The swap contract to price.\n    forward_curve: Must cover every delivery period in ``swap.schedule``.\n    discount_curve: Must cover every period's settlement date.\n    day_count: Year-fraction convention used for the rho computation, taking\n        ``(start, end)`` and returning the fraction of a year (default\n        :func:`~quantvolt.numerics.daycount.actual_365`).\n    settlement_lag_days: Calendar days added to each period's last day to get\n        the settlement date used for both the discount-factor lookup and the\n        rho year fraction (default 0, non-negative).\n    rate_bump: The per-basis-point size used to scale rho — the NPV change\n        per this parallel shift of the continuously compounded zero rate\n        (default ``1e-4``, i.e. one basis point).\n\nValidation is eager and ordered, before any computation:\n\n1. ``swap.schedule.periods`` is non-empty;\n2. sort-and-scan overlap/duplicate detection, raising :class:`ValidationError`\n   identifying each offending pair (defensive — see\n   :func:`_require_no_overlapping_periods`);\n3. coverage: every delivery period on the forward curve, then every settlement\n   date within the discount curve's tenor range, raising\n   :class:`MissingTenorError` identifying the missing period(s).\n\nInputs are never mutated; identical inputs produce identical results.\n\nRaises:\n    ValidationError: If ``settlement_lag_days`` is negative or ``rate_bump``\n        is not > 0, in addition to the schedule/coverage errors above.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/swap.py",
          "line": 117
        },
        {
          "name": "price_tolling_agreement",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.tolling.price_tolling_agreement",
          "kind": "function",
          "signature": "price_tolling_agreement(plant: PlantConfig, power_curve: ForwardCurve, fuel_curve: ForwardCurve, eua_curve: ForwardCurve, vol_surface: VolatilitySurface, correlation_matrix: np.ndarray, schedule: DeliverySchedule, discount_curve: DiscountCurve, *, capacity: float=_UNIT_NOTIONAL, fuel_sigma: VolatilitySurface | None=None, matrix_tolerance: float=_MATRIX_TOLERANCE, day_count: Callable[[date, date], float]=actual_365, settlement_lag_days: int=0) -> TollingResult",
          "summary": "Value a tolling agreement as a strip of clean spread options (Req 8.1-8.5).",
          "doc": "Value a tolling agreement as a strip of clean spread options (Req 8.1-8.5).\n\nOne clean spark (gas) / clean dark (coal) spread option per delivery\nperiod — see the module docstring for the leg composition, unit chain,\nsingle-surface volatility, correlation-indexing and discounting\nconventions. Validation is eager and complete before any pricing:\nschedule length, correlation matrix, full forward-curve / vol-surface /\ndiscount-curve coverage of the schedule.\n\nArgs:\n    plant: Heat rate, variable O&M cost, emissions intensity, fuel type.\n    power_curve: Power forwards; must cover every schedule period.\n    fuel_curve: Gas or coal forwards; must cover every schedule period.\n    eua_curve: EUA forwards; must cover every schedule period.\n    vol_surface: Surface used for the power leg of every period (and the\n        fuel+carbon leg too, when ``fuel_sigma`` is ``None``).\n    correlation_matrix: At least 3x3, ordered ``[power, fuel, eua]``.\n    schedule: 1-1200 delivery periods.\n    discount_curve: Must cover every period's settlement date.\n    capacity: Per-period notional in MWh, positive (default 1.0 —\n        unit-capacity; the historical behaviour). Scales every per-period\n        spread-option notional and the intrinsic-value payoff.\n    fuel_sigma: Optional separate volatility surface for the fuel+carbon\n        leg; must cover every schedule period. ``None`` (default) reuses\n        ``vol_surface`` for both legs, exactly as before.\n    matrix_tolerance: Absolute tolerance for the correlation matrix's\n        symmetry / unit-diagonal checks (default ``1e-9``); must be > 0\n        (a non-positive or NaN tolerance would silently disable or\n        misreport those checks).\n    day_count: Year-fraction convention for each period's time-to-expiry,\n        taking ``(start, end)`` (default\n        :func:`~quantvolt.numerics.daycount.actual_365`).\n    settlement_lag_days: Calendar days added to each period's last day to\n        get the settlement date used for the discount-factor lookup\n        (default 0, non-negative). Does NOT affect the option's\n        ``time_to_expiry``, which is always ``day_count`` from\n        ``discount_curve.reference_date`` to ``period.last_day`` — the\n        decision horizon, not the payment date.\n\nReturns:\n    NPV, intrinsic/time value decomposition, per-period values, and\n    per-period plus aggregate deltas for ``\"power\"``/``\"fuel\"``/``\"eua\"``\n    (aggregate == sum of per-period exactly, Property 20).\n\nRaises:\n    ValidationError: If the schedule has more than 1200 periods; if the\n        correlation matrix is not a square ndarray of size >= 3x3,\n        symmetric with unit diagonal (within ``matrix_tolerance``) and\n        off-diagonals strictly inside (-1, 1) (Property 19); if\n        ``capacity`` is not > 0, ``settlement_lag_days`` is negative, or\n        ``matrix_tolerance`` is not > 0 (including ``NaN``); or\n        if any per-period spread-option input violates\n        :func:`price_spread_option`'s domain (e.g. a non-positive power or\n        fuel+carbon leg forward).\n    InsufficientDataError: If any forward curve misses any schedule period\n        (naming the commodity and the missing periods, Req 8.4), or the\n        vol surface (or ``fuel_sigma``) misses any tenor (naming them,\n        Req 8.5).\n    MissingTenorError: If the discount curve does not cover every\n        period's settlement date.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/tolling.py",
          "line": 231
        },
        {
          "name": "price_vanilla_option",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.vanilla.price_vanilla_option",
          "kind": "function",
          "signature": "price_vanilla_option(request: VanillaOptionRequest) -> VanillaOptionResult",
          "summary": "Price a single vanilla European option on a forward under Black-76.",
          "doc": "Price a single vanilla European option on a forward under Black-76.\n\n``\"cap\"`` and ``\"floor\"`` requests denote a single caplet/floorlet and are\npriced as the equivalent call/put on the floating (forward) price. Premium\nand Greeks are per-unit kernel outputs scaled by ``notional``.\n\nArgs:\n    request: Fully specified option; all domains are validated eagerly\n        before any computation (Req 5.4).\n\nReturns:\n    The notional-scaled premium and Greeks.\n\nRaises:\n    ValidationError: If ``forward``, ``strike``, ``sigma``,\n        ``time_to_expiry`` or ``notional`` is not > 0, or\n        ``discount_factor`` is outside ``(0, 1]``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 71
        },
        {
          "name": "settle_energy_portfolio",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.settlement.settle_energy_portfolio",
          "kind": "function",
          "signature": "settle_energy_portfolio(portfolio: Portfolio, interval_data: Mapping[str, pl.DataFrame], *, ppa_columns: Mapping[str, PpaDataColumns] | None=None, hedge_columns: Mapping[str, PowerHedgeDataColumns] | None=None, imbalance_policies: Mapping[str, MissingImbalancePricePolicy] | None=None) -> PortfolioSettlement",
          "summary": "Settle all PPA and typed power-hedge positions using caller-owned data.",
          "doc": "Settle all PPA and typed power-hedge positions using caller-owned data.\n\n``interval_data`` is keyed by ``Position.position_id``. Other financial\ninstruments remain in ``unsettled`` because their realized exchange/OTC\nsettlement conventions belong to their own engines. PPA hedges represented as\nseparate portfolio positions are not also embedded in the PPA ledger, preventing\ndouble counting at aggregation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/portfolio/settlement.py",
          "line": 51
        },
        {
          "name": "settle_power_hedge_interval",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.power_hedge.settle_power_hedge_interval",
          "kind": "function",
          "signature": "settle_power_hedge_interval(contract: PowerHedgeContract, interval: PowerDeliveryInterval, spot_price_per_mwh: float) -> PowerHedgeSettlement",
          "summary": "Settle one observed interval; this is realized payoff, not option valuation.",
          "doc": "Settle one observed interval; this is realized payoff, not option valuation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 45
        },
        {
          "name": "settle_power_hedges_frame",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.power_hedge.settle_power_hedges_frame",
          "kind": "function",
          "signature": "settle_power_hedges_frame(contracts: Sequence[PowerHedgeContract], data: pl.DataFrame, *, interval_start_column: str='interval_start_utc', interval_end_column: str='interval_end_utc', spot_price_column: str='spot_price_per_mwh', columns: PowerHedgeDataColumns | None=None) -> pl.DataFrame",
          "summary": "Settle hedges against caller data, returning one row per active hedge/interval.",
          "doc": "Settle hedges against caller data, returning one row per active hedge/interval.\n\nInput order is preserved. Intervals need not be contiguous because hedge books\nmay be evaluated on selected observations, but duplicate starts and unsorted\nobservations are rejected.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 82
        },
        {
          "name": "settle_ppa_frame",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.settle_ppa_frame",
          "kind": "function",
          "signature": "settle_ppa_frame(contract: PpaContract, data: pl.DataFrame, *, columns: PpaDataColumns | None=None, imbalance_policy: MissingImbalancePricePolicy=MissingImbalancePricePolicy.ERROR, require_contiguous: bool=True, hedges: Sequence[PowerHedgeContract]=()) -> pl.DataFrame",
          "summary": "Validate and settle caller-supplied interval data into a canonical ledger.",
          "doc": "Validate and settle caller-supplied interval data into a canonical ledger.\n\nInputs remain caller-owned and are never modified. Column names may be mapped\nwith ``PpaDataColumns``. By default physical PPAs require genuine shortfall and\nexcess prices: using spot as an imbalance proxy must be explicitly requested.\n\nThe result contains one row per input interval and every signed cash-flow\ncomponent used to reconstruct ``net_cashflow``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 135
        },
        {
          "name": "settle_ppa_interval",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.ppa.settle_ppa_interval",
          "kind": "function",
          "signature": "settle_ppa_interval(contract: PpaContract, interval: PowerDeliveryInterval, *, contracted_mwh: float, metered_generation_mwh: float, spot_price_per_mwh: float, shortfall_price_per_mwh: float | None=None, excess_price_per_mwh: float | None=None, hedge_cashflow: float=0.0, option_payoff: float=0.0, option_premium: float=0.0, variable_cost: float=0.0, transaction_cost: float=0.0) -> PpaIntervalSettlement",
          "summary": "Settle one PPA interval from a producer's perspective.",
          "doc": "Settle one PPA interval from a producer's perspective.\n\nFor a physical PPA, contracted energy earns the fixed price; own generation\nserves that obligation first, a shortfall is bought at ``shortfall_price``,\nand excess generation is sold at ``excess_price``. Missing imbalance prices\nexplicitly fall back to spot.\n\nFor a financial CfD, all metered generation is sold spot and the contracted\nvolume receives ``fixed - spot``. There is no physical delivery shortfall.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 278
        },
        {
          "name": "spark_spread",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.spreads.spark_spread",
          "kind": "function",
          "signature": "spark_spread(power_curve: ForwardCurve, fuel_curve: ForwardCurve, heat_rate: float, variable_cost: float, emissions_cost: float) -> SpreadResult",
          "summary": "Spark spread (gas-fired generation margin) per shared delivery period.",
          "doc": "Spark spread (gas-fired generation margin) per shared delivery period.\n\nFor each period in the intersection of ``power_curve`` and ``fuel_curve``:\n``power_price - heat_rate * fuel_price - variable_cost - emissions_cost``\n(Req 2.1, Property 6). Computing a spark spread never reads or writes any dark\nvalues: each call returns a new immutable :class:`SpreadResult` labelled\n``\"spark\"``, so any existing dark result remains untouched.\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless ``heat_rate > 0``,\n``variable_cost >= 0`` and ``emissions_cost >= 0``, and\n:class:`InsufficientDataError` when the curves share no delivery periods.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 205
        },
        {
          "name": "storage_intrinsic",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.storage.storage_intrinsic",
          "kind": "function",
          "signature": "storage_intrinsic(model: StorageModel, forward_curve: ForwardCurve, *, inventory_step: float | None=None, grid_steps: int=_DEFAULT_GRID_STEPS) -> IntrinsicResult",
          "summary": "Optimal forward-locked injection/withdrawal schedule and its value (Req 22.1).",
          "doc": "Optimal forward-locked injection/withdrawal schedule and its value (Req 22.1).\n\nExact backward-induction dynamic program over the discretised inventory grid: with the\nforward curve's per-period prices known, it finds the injection/withdrawal schedule that\nmaximises total cash flow subject to the inventory bounds, the injection/withdrawal\nratchets and the terminal-inventory condition — all enforced at *every* step by the\nfeasible-transition set (Req 22.3). See the module docstring for the discretisation,\nthe cash-flow conventions and the exactness statement.\n\nArgs:\n    model: The storage parameters.\n    forward_curve: The forward curve whose node prices drive the schedule; nodes are taken\n        in chronological order, one delivery period per horizon step.\n    inventory_step: Inventory-grid spacing (volume); defaults to\n        ``working_capacity / grid_steps``. Must divide the distances from\n        ``min_inventory`` to ``initial_inventory`` and ``terminal_inventory``.\n    grid_steps: Number of inventory-grid intervals used to derive the default\n        ``inventory_step`` when it is not supplied (default ``50``). Ignored when\n        ``inventory_step`` is given explicitly. Must be ``>= 1``.\n\nReturns:\n    The optimal :class:`IntrinsicResult`.\n\nRaises:\n    ValidationError: If ``inventory_step`` is non-positive; if ``grid_steps < 1``; if the\n        initial/terminal inventory is off-grid; if a ratchet returns a negative rate at a\n        grid level; or if a hard terminal target is unreachable from the initial inventory\n        over the horizon.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 382
        },
        {
          "name": "storage_value",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.storage.storage_value",
          "kind": "function",
          "signature": "storage_value(model: StorageModel, forward_curve: ForwardCurve, factor_model: StorageFactorModel, seed: int, *, inventory_step: float | None=None, grid_steps: int=_DEFAULT_GRID_STEPS, lsm_basis_degree: int=_LSM_BASIS_DEGREE, antithetic: bool=True) -> StorageValueResult",
          "summary": "Total (intrinsic + extrinsic) storage value via Least-Squares Monte Carlo (Req 22.2).",
          "doc": "Total (intrinsic + extrinsic) storage value via Least-Squares Monte Carlo (Req 22.2).\n\nSimulates forward-consistent spot paths with ``factor_model`` (see\n:class:`StorageFactorModel`) and runs a backward induction over ``(time, inventory)`` that\nfinds the optimal *adaptive* injection/withdrawal policy. At each period and inventory\nlevel the decision maximises ``immediate cash flow + continuation value``, where the\ncontinuation value of each reachable next level is estimated by regressing the pathwise\nnext-period value on the polynomial basis ``[1, S, S**2]`` of the current spot ``S``\n(Longstaff-Schwartz). The regression is used only to choose the action; the value is then\naccumulated from the *realised* pathwise continuation to limit foldback bias. All the\ninventory-bound, ratchet and terminal constraints are enforced by the same\nfeasible-transition set as the intrinsic DP (Req 22.3).\n\nExtrinsic value via a control variate (Property 64)\n---------------------------------------------------\nThe extrinsic component is estimated as the mean pathwise difference between the adaptive\npolicy value and the *fixed intrinsic schedule* evaluated on the **same** simulated paths\n(common random numbers): ``extrinsic = mean_p[V_adaptive(p) - V_fixed(p)]``. Because the\nfixed forward-locked schedule is one feasible policy available to the optimal adaptive\npolicy, the difference is non-negative in expectation, and sharing the price paths cancels\nthe bulk of the sampling variance — so ``extrinsic >= 0`` holds robustly rather than being\nswamped by the (large) variance of ``total`` alone. ``total`` is anchored on the exact\nintrinsic value as ``intrinsic + extrinsic``, and ``extrinsic`` is reported honestly with\nits standard error rather than clamped (a small negative value within a few standard errors\nis Monte Carlo noise, per the Property-64 tolerance floor).\n\nArgs:\n    model: The storage parameters.\n    forward_curve: The forward curve (its node prices are the per-period forward means).\n    factor_model: The single-factor spot model and MC controls.\n    seed: RNG seed; identical inputs and seed give identical results (Req 11.2).\n    inventory_step: Inventory-grid spacing, shared with :func:`storage_intrinsic`.\n    grid_steps: Number of inventory-grid intervals used to derive the default\n        ``inventory_step`` when it is not supplied, shared with :func:`storage_intrinsic`\n        (default ``50``). Must be ``>= 1``.\n    lsm_basis_degree: Degree of the polynomial regression basis\n        ``[1, S, ..., S**lsm_basis_degree]`` used for the LSM continuation value (default\n        ``2``, i.e. ``[1, S, S**2]``). Must be ``>= 1``.\n    antithetic: Whether the simulated spot paths use antithetic variates (default\n        ``True``, matching prior behaviour). Also selects the pair-mean-aware\n        standard-error estimator used for ``standard_error`` (see\n        :func:`_standard_error`).\n\nReturns:\n    The :class:`StorageValueResult` with ``total``, ``intrinsic``, ``extrinsic`` and the\n    Monte Carlo ``standard_error`` of ``total``.\n\nRaises:\n    ValidationError: For the same grid/ratchet/terminal violations as\n        :func:`storage_intrinsic`, if ``seed`` is negative, or if ``lsm_basis_degree < 1``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 553
        },
        {
          "name": "time_aggregate",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.dispatch_approx.time_aggregate",
          "kind": "function",
          "signature": "time_aggregate(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], block_hours: int, *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Time-aggregation heuristic: solve on ``block_hours``-hour blocks, rescale (Req 21.3).",
          "doc": "Time-aggregation heuristic: solve on ``block_hours``-hour blocks, rescale (Req 21.3).\n\nEach consecutive run of ``block_hours`` periods is averaged into one coarse\nperiod (power, fuel, temperature, and — if supplied — discount factor), the\ndeterministic dispatch is solved on the coarse series, and the coarse per-period\nresult is expanded back to the original resolution with each block's cash flow\nrecurring ``block_hours`` times (the rescaling). The returned\n:class:`DispatchSchedule` therefore has the original horizon's length and a\n``total_value`` equal to ``block_hours`` times the coarse value.\n\nExactness and bias. On **block-constant** prices (each series constant within\nevery block) the block average is lossless and, for a unit that incurs no start\nwithin the horizon, the rescaled value equals the full-resolution optimum\nexactly. When a start *is* incurred inside a block, the once-per-block start\ncost is replicated across the block's sub-periods, understating the value — a\ndocumented downward bias that shrinks with fewer/cheaper starts. Sub-block ramp\nand commitment freedom (and any intra-block discount-factor variation) are the\nother, generally small, sources of error. Duration/timer arguments are counted\nin *coarse* periods (blocks) inside the coarse solve; pass them accordingly.\n\nArgs:\n    plant: The operating model (unchanged; passed to the coarse solve).\n    power_prices: Power price ``P_t`` per (fine) period.\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period.\n    block_hours: Periods per aggregation block; must be an integer ``>= 1`` that\n        divides the horizon evenly.\n    initial_online: Whether the unit is producing entering the horizon.\n    initial_output: Output entering the horizon (MW); on the coarse grid when\n        online.\n    initial_uptime: Producing (coarse) periods already accrued (min-run).\n    initial_downtime: Offline (coarse) periods already accrued (start bucket /\n        min-down).\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    discount_factors: Per-period to-today discount factors (default all 1.0);\n        block-averaged before the coarse solve.\n\nReturns:\n    A full-resolution :class:`DispatchSchedule`; ``total_value`` is the rescaled\n    coarse value.\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a discount\n        factor or ``output_step`` is non-positive; if ``block_hours`` is not an\n        integer ``>= 1`` or does not divide the horizon; or if the coarse problem\n        is itself infeasible (delegated to the deterministic solver).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 98
        },
        {
          "name": "valuation_benchmark",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.long_dated.valuation_benchmark",
          "kind": "function",
          "signature": "valuation_benchmark(period: DeliveryPeriod, forward_curve: ForwardCurve, spot_model: SpotModel, corporate_premium: CorporatePremium) -> BenchmarkResult",
          "summary": "Value ``period`` off the forward curve where liquid, else off projected spot.",
          "doc": "Value ``period`` off the forward curve where liquid, else off projected spot.\n\nWhere the liquid ``forward_curve`` covers ``period``, the forward price is the\nvaluation benchmark and no projected-spot value is substituted (Req 23.1). A\nperiod present on the curve counts as forward-based whether its node is\n``observed`` or ``interpolated`` — both lie within the liquid forward span. Where\nthe curve does not cover ``period``, the value is projected as\n``spot_model(period) + corporate_premium.premium`` and tagged\n:attr:`ValuationSource.PROJECTED` (Req 23.2).\n\n``corporate_premium`` is validated eagerly (before the liquidity branch) so a\nmarket-tagged or untagged premium is rejected regardless of this period's\nliquidity — the corporate risk premium is never applied silently (Req 19.3).\n\nArgs:\n    period: The delivery period to value.\n    forward_curve: The liquid forward curve; membership of ``period`` decides the\n        regime.\n    spot_model: Pure callable ``DeliveryPeriod -> float`` giving the model spot\n        expectation used when no liquid forward exists. Never mutated.\n    corporate_premium: The additive corporate risk premium, explicitly tagged\n        :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`.\n\nReturns:\n    A :class:`BenchmarkResult` whose ``source`` tags the regime prominently.\n\nRaises:\n    ValidationError: If ``corporate_premium`` is not an explicitly corporate-tagged\n        :class:`CorporatePremium`.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 169
        },
        {
          "name": "value_portfolio",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.valuation.value_portfolio",
          "kind": "function",
          "signature": "value_portfolio(portfolio: Portfolio, market_data: MarketData, pricers: Mapping[type[Any], Pricer] | None=None) -> PortfolioValuation",
          "summary": "Value every position via its registered pricer and aggregate the NPV (Req 13.2-13.6).",
          "doc": "Value every position via its registered pricer and aggregate the NPV (Req 13.2-13.6).\n\nThe dispatch registry is :data:`DEFAULT_PRICERS` merged with the caller-supplied\n``pricers`` (caller entries win) — the open/closed extension seam: new instrument\ntypes are registered, never edited in (Req 13.4). Positions are processed in\nportfolio order; a position whose instrument type has no registered pricer is\nreturned in ``unpriced`` rather than raising, so the rest of the book is still\nvalued, and ``total_npv`` sums the priced positions only (Req 13.3).\n\nPricing errors — :class:`~quantvolt.exceptions.ExpiredContractError`,\n:class:`~quantvolt.exceptions.MissingTenorError`, a missing forward curve from\n:meth:`MarketData.curve_for` — **propagate**: they are data errors on a position\nthe registry *does* know how to price, not registry misses, and silently skipping\nthem would hide a mispriced book.\n\nInputs are never mutated, and identical inputs produce identical results (Req 13.6).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/portfolio/valuation.py",
          "line": 196
        },
        {
          "name": "value_transport_right",
          "module": "quantvolt",
          "qualified": "quantvolt.pricing.transmission_right.value_transport_right",
          "kind": "function",
          "signature": "value_transport_right(right: TransportRight, curve_a: ForwardCurve, curve_b: ForwardCurve, discount_curve: DiscountCurve, *, vols: tuple[float, float] | None=None, correlation: float | None=None, day_count: Callable[[date, date], float]=actual_365, settlement_lag_days: int=0) -> TransportRightResult",
          "summary": "Value a transmission or pipeline right (Req 24.1-24.5, Properties 67-68).",
          "doc": "Value a transmission or pipeline right (Req 24.1-24.5, Properties 67-68).\n\n``curve_a`` is the origin (hub A) forward curve and ``curve_b`` the destination\n(hub B) curve; their commodity ids must match ``right.origin`` / ``right.destination``\nso curves cannot be silently swapped. Valuation covers the shared periods of both\ncurves within the right's schedule (Req 24.5). Each period's settlement is its\n``last_day`` plus ``settlement_lag_days`` (the swap/tolling convention): the\ndiscount factor is taken there. For the option path, ``time_to_expiry`` is\n``day_count`` (default actual/365) from ``discount_curve.reference_date`` to the\nperiod's ``last_day`` (the flow decision horizon) — ``settlement_lag_days`` never\nshifts the volatility horizon, only the discount-factor lookup date.\n\nIntrinsic value is ``Σ D · Q_delivered · max(P_B - P_A - T_AB, 0)``. Supplying\n``vols=(sigma_origin, sigma_destination)`` and ``correlation`` (both or neither,\nReq 24.2) adds the spread-option extrinsic value per period. A ``BIDIRECTIONAL``\nright commits each period to the best of A→B (tariff ``tariff``), B→A (tariff\n``reverse_tariff``, defaulting to ``tariff``) or no-flow, and is subadditive versus\ntwo one-way rights (Property 68).\n\nArgs:\n    right: The transmission or pipeline right to value.\n    curve_a: Origin (hub A) forward curve.\n    curve_b: Destination (hub B) forward curve.\n    discount_curve: Discount curve for settlement dates.\n    vols: Optional ``(sigma_origin, sigma_destination)`` pair (both or\n        neither with ``correlation``).\n    correlation: Optional origin/destination correlation (both or neither\n        with ``vols``).\n    day_count: Year-fraction convention for the option ``time_to_expiry``,\n        taking ``(start, end)`` (default\n        :func:`~quantvolt.numerics.daycount.actual_365`).\n    settlement_lag_days: Calendar days added to each period's last day to\n        get the settlement date used for the discount factor (default 0,\n        non-negative). Does NOT affect the option's ``time_to_expiry``,\n        which is always ``day_count`` to ``period.last_day``.\n\nRaises:\n    ValidationError: If ``vols``/``correlation`` are not supplied both-or-neither\n        (Req 24.2), if the curve commodity ids do not match ``right.origin`` /\n        ``right.destination``, if ``settlement_lag_days`` is negative, or if a\n        location forward is non-positive on the option path (from the\n        spread-option engine).\n    InsufficientDataError: If the two curves share no schedule period (Req 24.5).\n    MissingTenorError: If the discount curve does not cover a period's settlement.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/transmission_right.py",
          "line": 241
        },
        {
          "name": "var_applicability_guard",
          "module": "quantvolt",
          "qualified": "quantvolt.assets.long_dated.var_applicability_guard",
          "kind": "function",
          "signature": "var_applicability_guard(position: PricedPosition, *, strict: bool=False) -> VarApplicabilityVerdict",
          "summary": "Flag short-horizon VaR as inapplicable for a projected-spot-valued position.",
          "doc": "Flag short-horizon VaR as inapplicable for a projected-spot-valued position.\n\nReads the position's provenance from ``position.position.tags``: a position\ncarrying the :attr:`ValuationSource.PROJECTED` tag was valued off projected spot,\nfor which short-horizon VaR is not meaningful — VaR is meaningful only in liquid\nmarkets (Chapter-10 caveat, Req 23.3). Absence of that tag is treated as\nforward-based / liquid and therefore VaR-applicable.\n\nDesigned to be *consulted* by MC-VaR / parametric-VaR callers: they inspect the\nreturned verdict and exclude the position (or switch to CFaR / scenario analysis)\nwithout this module modifying ``risk/``. With ``strict=True`` the guard instead\nraises for an inapplicable position, for callers that prefer to hard-fail.\n\nArgs:\n    position: The priced position to judge, as consumed by the risk engines.\n    strict: When ``True``, raise :class:`ValidationError` for a projected-spot\n        position instead of returning an ``applicable=False`` verdict.\n\nReturns:\n    A :class:`VarApplicabilityVerdict` with ``applicable`` and a ``reason``.\n\nRaises:\n    ValidationError: If ``strict`` is ``True`` and the position is projected-valued.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 213
        },
        {
          "name": "variance_min_hedge",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.variance_min.variance_min_hedge",
          "kind": "function",
          "signature": "variance_min_hedge(sigma_hh: NDArray[np.float64], sigma_ht: NDArray[np.float64], *, condition_limit: float=_CONDITION_LIMIT) -> NDArray[np.float64]",
          "summary": "Variance-minimizing hedge ratios ``h* = Σ_hh⁻¹ Σ_ht`` (Req 18.1, Property 54).",
          "doc": "Variance-minimizing hedge ratios ``h* = Σ_hh⁻¹ Σ_ht`` (Req 18.1, Property 54).\n\nGiven a target exposure and ``n`` hedge instruments described by their return\ncovariance with the target (``Σ_ht``) and with each other (``Σ_hh``), returns\nthe ratios ``h*`` that minimise the local variance of the hedged position.\n``h*`` solves the normal-equation system ``Σ_hh·h* = Σ_ht``.\n\nThe system is solved with :func:`numpy.linalg.solve` after an explicit\nconditioning check: a singular or ill-conditioned ``Σ_hh`` raises rather than\nsilently returning a pseudo-inverse solution (a pseudo-inverse would hide the\nfact that the hedge instruments are collinear and the ratios are not\nidentified).\n\nArgs:\n    sigma_hh: The ``(n, n)`` covariance matrix of the hedge instruments with\n        each other. Must be square, symmetric, finite and non-singular.\n    sigma_ht: The length-``n`` covariance vector of the hedge instruments with\n        the target exposure. Must be conformable with ``sigma_hh``.\n    condition_limit: Upper bound on the 2-norm condition number of ``sigma_hh``\n        before it is treated as numerically singular; defaults to ``1/eps``, the\n        point past which the linear solve loses all significant digits.\n\nReturns:\n    The ``(n,)`` ``float64`` array of variance-minimizing hedge ratios. For a\n    single instrument (``n == 1``) this collapses to\n    :func:`linear_cross_hedge`'s ``rho·sigma_t/sigma_h`` (Property 54).\n\nRaises:\n    ValidationError: If ``sigma_hh`` is not a non-empty square 2-D matrix, is\n        not symmetric, contains non-finite values, is singular or\n        ill-conditioned; if ``condition_limit`` is not strictly positive; or if\n        ``sigma_ht`` is not a finite 1-D vector conformable with ``sigma_hh``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/variance_min.py",
          "line": 50
        },
        {
          "name": "walk_forward_ppa_nomination",
          "module": "quantvolt",
          "qualified": "quantvolt.hedging.ppa_walk_forward.walk_forward_ppa_nomination",
          "kind": "function",
          "signature": "walk_forward_ppa_nomination(contract: PpaContract, data: pl.DataFrame, rebalance_utc: Sequence[datetime], *, evaluation_end_utc: datetime, capacity_mwh_per_interval: float, columns: PpaNominationColumns | None=None, lookback: timedelta | None=None, objective: PpaNominationObjective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR, risk_aversion: float=1.0, confidence_level: float=0.95, grid_steps: int=100) -> PpaWalkForwardResult",
          "summary": "Refit at each cutoff and apply only until the next cutoff.",
          "doc": "Refit at each cutoff and apply only until the next cutoff.\n\n``lookback=None`` uses an expanding window. A positive ``lookback`` uses a\nrolling window. Intervals crossing a rebalance boundary are rejected rather\nthan assigned partly in-sample and partly out-of-sample.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_walk_forward.py",
          "line": 34
        },
        {
          "name": "BUILT_IN_COMMODITIES",
          "module": "quantvolt",
          "qualified": "quantvolt.models.commodity.BUILT_IN_COMMODITIES",
          "kind": "constant",
          "signature": "BUILT_IN_COMMODITIES",
          "summary": "Read-only-by-convention registry of the package's built-in European power, gas and carbon commodity definitions, keyed by stable commodity ID..",
          "doc": "Read-only-by-convention registry of the package's built-in European power, gas and carbon commodity definitions, keyed by stable commodity ID.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 1
        },
        {
          "name": "Instrument",
          "module": "quantvolt",
          "qualified": "quantvolt.portfolio.model.Instrument",
          "kind": "constant",
          "signature": "Instrument",
          "summary": "Public type alias for the instrument variants that a Portfolio Position can hold..",
          "doc": "Public type alias for the instrument variants that a Portfolio Position can hold.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 1
        }
      ]
    },
    {
      "name": "models",
      "qualified": "quantvolt.models",
      "description": "Immutable domain objects for commodities, periods, curves and instruments.",
      "symbols": [
        {
          "name": "CommodityConfig",
          "module": "models",
          "qualified": "quantvolt.models.commodity.CommodityConfig",
          "kind": "class",
          "signature": "CommodityConfig(commodity_id: str, price_unit: str, hub: Hub)",
          "summary": "Immutable commodity definition containing the stable commodity ID, human-readable name and delivery hub..",
          "doc": "Immutable commodity definition containing the stable commodity ID, human-readable name and delivery hub.",
          "methods": [],
          "fields": [
            {
              "name": "commodity_id",
              "type": "str",
              "default": null
            },
            {
              "name": "price_unit",
              "type": "str",
              "default": null
            },
            {
              "name": "hub",
              "type": "Hub",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 23
        },
        {
          "name": "CurveNode",
          "module": "models",
          "qualified": "quantvolt.models.curve.CurveNode",
          "kind": "class",
          "signature": "CurveNode(period: DeliveryPeriod, price: float, status: Literal['observed', 'interpolated'])",
          "summary": "A single ``(period, price)`` point on a forward curve.",
          "doc": "A single ``(period, price)`` point on a forward curve.\n\n``status`` records whether the price was ``\"observed\"`` in the market or\n``\"interpolated\"`` between observations. Prices may be negative — negative\npower prices are real in European power markets — so they are never rejected.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "price",
              "type": "float",
              "default": null
            },
            {
              "name": "status",
              "type": "Literal['observed', 'interpolated']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/curve.py",
          "line": 29
        },
        {
          "name": "DeliveryPeriod",
          "module": "models",
          "qualified": "quantvolt.models.schedule.DeliveryPeriod",
          "kind": "class",
          "signature": "DeliveryPeriod(year: int, month: int)",
          "summary": "A single calendar month of delivery, identified by ``(year, month)``.",
          "doc": "A single calendar month of delivery, identified by ``(year, month)``.\n\n``order=True`` gives periods a natural chronological ordering: comparisons and\n``sorted(...)`` fall back to the ``(year, month)`` tuple in field order, so a\nperiod knows how to rank itself (Tell-Don't-Ask) and callers never compare raw\nints. Years are constrained to the range :class:`datetime.date` can represent,\nwhich also guarantees :attr:`last_day` never fails.",
          "methods": [
            {
              "name": "last_day",
              "signature": "last_day(self) -> date",
              "summary": "The calendar last day of this month (e.g. 2024-02 -> 2024-02-29)."
            }
          ],
          "fields": [
            {
              "name": "year",
              "type": "int",
              "default": null
            },
            {
              "name": "month",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/schedule.py",
          "line": 31
        },
        {
          "name": "DeliverySchedule",
          "module": "models",
          "qualified": "quantvolt.models.schedule.DeliverySchedule",
          "kind": "class",
          "signature": "DeliverySchedule(periods: tuple[DeliveryPeriod, ...])",
          "summary": "An ordered, non-empty run of delivery periods.",
          "doc": "An ordered, non-empty run of delivery periods.\n\nConsistency invariant: periods are strictly increasing by ``(year, month)``,\nso there are no duplicate or overlapping months. The schedule validates this\nfor itself at construction rather than trusting callers (Tell-Don't-Ask).",
          "methods": [],
          "fields": [
            {
              "name": "periods",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/schedule.py",
          "line": 56
        },
        {
          "name": "DiscountCurve",
          "module": "models",
          "qualified": "quantvolt.models.discount_curve.DiscountCurve",
          "kind": "class",
          "signature": "DiscountCurve(reference_date: date, tenors: tuple[date, ...], factors: tuple[float, ...])",
          "summary": "A term structure of discount factors keyed by tenor date.",
          "doc": "A term structure of discount factors keyed by tenor date.\n\n``tenors`` and ``factors`` are parallel, so ``factors[i]`` is the discount\nfactor observed for ``tenors[i]``.\n\nConventions (validated eagerly in ``__post_init__``):\n\n- ``tenors`` is non-empty and strictly increasing.\n- Every tenor lies strictly *after* ``reference_date`` (``tenor > reference_date``);\n  a discount curve prices future cash flows, so ``reference_date`` itself is not a tenor.\n- Every factor lies in ``(0, 1]`` (see :func:`require_discount_factor`).",
          "methods": [
            {
              "name": "discount_factor",
              "signature": "discount_factor(self, target_date: date) -> float",
              "summary": "Discount factor for ``target_date`` by linear interpolation."
            }
          ],
          "fields": [
            {
              "name": "reference_date",
              "type": "date",
              "default": null
            },
            {
              "name": "tenors",
              "type": "tuple[date, ...]",
              "default": null
            },
            {
              "name": "factors",
              "type": "tuple[float, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/discount_curve.py",
          "line": 14
        },
        {
          "name": "ForwardContract",
          "module": "models",
          "qualified": "quantvolt.models.instruments.ForwardContract",
          "kind": "class",
          "signature": "ForwardContract(commodity: CommodityConfig, delivery_period: DeliveryPeriod, contract_price: float, notional: float, granularity: Granularity = Granularity.MONTHLY, settlement_type: SettlementType = SettlementType.PHYSICAL, counterparty: str | None = None)",
          "summary": "Bilateral forward — customisable, OTC, physical or financial settlement.",
          "doc": "Bilateral forward — customisable, OTC, physical or financial settlement.\n\n``counterparty`` is retained for credit-risk tracking.",
          "methods": [],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "contract_price",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "granularity",
              "type": "Granularity",
              "default": "Granularity.MONTHLY"
            },
            {
              "name": "settlement_type",
              "type": "SettlementType",
              "default": "SettlementType.PHYSICAL"
            },
            {
              "name": "counterparty",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 83
        },
        {
          "name": "ForwardCurve",
          "module": "models",
          "qualified": "quantvolt.models.curve.ForwardCurve",
          "kind": "class",
          "signature": "ForwardCurve(commodity: CommodityConfig, market_date: date, nodes: tuple[CurveNode, ...])",
          "summary": "A discrete forward curve: one node per delivery period, ordered by period.",
          "doc": "A discrete forward curve: one node per delivery period, ordered by period.\n\nConsistency invariants, validated eagerly in :meth:`__post_init__`:\n\n- ``nodes`` is non-empty.\n- Nodes are strictly increasing by :class:`DeliveryPeriod` (reusing the period's\n  own ordering), so there are no duplicate periods.\n- Every node's ``status`` is one of ``{\"observed\", \"interpolated\"}``.\n\nPrices are *not* constrained: negative forward prices occur in European power\nmarkets and are accepted verbatim.\n\nEquality is tolerance-based (see :meth:`__eq__`), so ``eq=False`` disables the\ndataclass-generated comparison and this class supplies its own ``__eq__`` /\n``__hash__`` pair.",
          "methods": [
            {
              "name": "price_at",
              "signature": "price_at(self, period: DeliveryPeriod) -> float",
              "summary": "Return the price of the node whose period equals ``period``."
            },
            {
              "name": "to_dict",
              "signature": "to_dict(self) -> dict[str, Any]",
              "summary": "Serialise the whole object graph to JSON-friendly built-ins."
            },
            {
              "name": "from_dict",
              "signature": "from_dict(cls, data: dict[str, Any]) -> ForwardCurve",
              "summary": "Reconstruct a :class:`ForwardCurve` from :meth:`to_dict` output."
            }
          ],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "market_date",
              "type": "date",
              "default": null
            },
            {
              "name": "nodes",
              "type": "tuple[CurveNode, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/curve.py",
          "line": 43
        },
        {
          "name": "FuturesContract",
          "module": "models",
          "qualified": "quantvolt.models.instruments.FuturesContract",
          "kind": "class",
          "signature": "FuturesContract(commodity: CommodityConfig, delivery_period: DeliveryPeriod, contract_price: float, notional: float, granularity: Granularity = Granularity.MONTHLY, settlement_type: SettlementType = SettlementType.FINANCIAL)",
          "summary": "Exchange-traded futures — standardised, margined, typically financial settlement.",
          "doc": "Exchange-traded futures — standardised, margined, typically financial settlement.",
          "methods": [],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "contract_price",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "granularity",
              "type": "Granularity",
              "default": "Granularity.MONTHLY"
            },
            {
              "name": "settlement_type",
              "type": "SettlementType",
              "default": "SettlementType.FINANCIAL"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 68
        },
        {
          "name": "Granularity",
          "module": "models",
          "qualified": "quantvolt.models.schedule.Granularity",
          "kind": "class",
          "signature": "Granularity()",
          "summary": "Single source of delivery granularity, reused by instruments (Task 3).",
          "doc": "Single source of delivery granularity, reused by instruments (Task 3).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "HOURLY",
              "value": "'hourly'"
            },
            {
              "name": "DAILY",
              "value": "'daily'"
            },
            {
              "name": "MONTHLY",
              "value": "'monthly'"
            },
            {
              "name": "QUARTERLY",
              "value": "'quarterly'"
            },
            {
              "name": "YEARLY",
              "value": "'yearly'"
            }
          ],
          "source": "src/quantvolt/models/schedule.py",
          "line": 20
        },
        {
          "name": "Greeks",
          "module": "models",
          "qualified": "quantvolt.models.greeks.Greeks",
          "kind": "class",
          "signature": "Greeks(delta: float, gamma: float, vega: float, theta: float, rho: float)",
          "summary": "First-order (and gamma) option sensitivities.",
          "doc": "First-order (and gamma) option sensitivities.\n\nAll fields are per-unit-of-underlying sensitivities. Instances are immutable\nvalue objects; the arithmetic helpers return new ``Greeks`` rather than\nmutating in place.",
          "methods": [
            {
              "name": "scale",
              "signature": "scale(self, factor: float) -> Greeks",
              "summary": "Elementwise multiply by ``factor`` (e.g. a position size or weight)."
            },
            {
              "name": "zero",
              "signature": "zero(cls) -> Greeks",
              "summary": "Additive identity — the natural start value when summing Greeks."
            }
          ],
          "fields": [
            {
              "name": "delta",
              "type": "float",
              "default": null
            },
            {
              "name": "gamma",
              "type": "float",
              "default": null
            },
            {
              "name": "vega",
              "type": "float",
              "default": null
            },
            {
              "name": "theta",
              "type": "float",
              "default": null
            },
            {
              "name": "rho",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/greeks.py",
          "line": 25
        },
        {
          "name": "Hub",
          "module": "models",
          "qualified": "quantvolt.models.commodity.Hub",
          "kind": "class",
          "signature": "Hub(hub_id: str, exchange: str, price_unit: str)",
          "summary": "Immutable market hub definition with stable ID, display name and country or market area..",
          "doc": "Immutable market hub definition with stable ID, display name and country or market area.",
          "methods": [],
          "fields": [
            {
              "name": "hub_id",
              "type": "str",
              "default": null
            },
            {
              "name": "exchange",
              "type": "str",
              "default": null
            },
            {
              "name": "price_unit",
              "type": "str",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 16
        },
        {
          "name": "InstrumentPriceRecord",
          "module": "models",
          "qualified": "quantvolt.models.instruments.InstrumentPriceRecord",
          "kind": "class",
          "signature": "InstrumentPriceRecord(instrument_id: str, commodity: CommodityConfig, delivery_period: DeliveryPeriod, price: float)",
          "summary": "An observed price for a commodity over a delivery period.",
          "doc": "An observed price for a commodity over a delivery period.",
          "methods": [],
          "fields": [
            {
              "name": "instrument_id",
              "type": "str",
              "default": null
            },
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "price",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 58
        },
        {
          "name": "Moneyness",
          "module": "models",
          "qualified": "quantvolt.models.vol_surface.Moneyness",
          "kind": "class",
          "signature": "Moneyness()",
          "summary": "Option moneyness relative to the forward (design §3.1).",
          "doc": "Option moneyness relative to the forward (design §3.1).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "ATM",
              "value": "'atm'"
            },
            {
              "name": "OTM",
              "value": "'otm'"
            },
            {
              "name": "ITM",
              "value": "'itm'"
            }
          ],
          "source": "src/quantvolt/models/vol_surface.py",
          "line": 19
        },
        {
          "name": "PipelineRight",
          "module": "models",
          "qualified": "quantvolt.models.instruments.PipelineRight",
          "kind": "class",
          "signature": "PipelineRight(origin: str, destination: str, tariff: float, quantity: float, schedule: DeliverySchedule, direction: TransportDirection = TransportDirection.A_TO_B, loss: float = 0.0, capacity: float | None = None, reverse_tariff: float | None = None)",
          "summary": "A right to move **gas** from origin hub A to destination hub B (Req 24).",
          "doc": "A right to move **gas** from origin hub A to destination hub B (Req 24).\n\nEconomically identical to :class:`TransmissionRight` — same payoff\n``Q_delivered * max(P_B - P_A - T_AB, 0)`` and the same field set — differing\nonly in intent (gas pipeline capacity rather than power transmission). Kept a\ndistinct type so a book never silently conflates power transmission with gas\ntransport; both are priced by the one ``value_transport_right`` engine.\n\nSee :class:`TransmissionRight` for the field semantics.",
          "methods": [],
          "fields": [
            {
              "name": "origin",
              "type": "str",
              "default": null
            },
            {
              "name": "destination",
              "type": "str",
              "default": null
            },
            {
              "name": "tariff",
              "type": "float",
              "default": null
            },
            {
              "name": "quantity",
              "type": "float",
              "default": null
            },
            {
              "name": "schedule",
              "type": "DeliverySchedule",
              "default": null
            },
            {
              "name": "direction",
              "type": "TransportDirection",
              "default": "TransportDirection.A_TO_B"
            },
            {
              "name": "loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "capacity",
              "type": "float | None",
              "default": "None"
            },
            {
              "name": "reverse_tariff",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 196
        },
        {
          "name": "PlantConfig",
          "module": "models",
          "qualified": "quantvolt.models.instruments.PlantConfig",
          "kind": "class",
          "signature": "PlantConfig(heat_rate: float, variable_om_cost: float, emissions_intensity: float, fuel_type: Literal['gas', 'coal'])",
          "summary": "Thermal-plant conversion parameters.",
          "doc": "Thermal-plant conversion parameters.",
          "methods": [],
          "fields": [
            {
              "name": "heat_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "variable_om_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "emissions_intensity",
              "type": "float",
              "default": null
            },
            {
              "name": "fuel_type",
              "type": "Literal['gas', 'coal']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 117
        },
        {
          "name": "PowerDeliveryInterval",
          "module": "models",
          "qualified": "quantvolt.models.interval.PowerDeliveryInterval",
          "kind": "class",
          "signature": "PowerDeliveryInterval(start_utc: datetime, end_utc: datetime)",
          "summary": "One unambiguous half-open power-delivery interval ``[start_utc, end_utc)``.",
          "doc": "One unambiguous half-open power-delivery interval ``[start_utc, end_utc)``.",
          "methods": [
            {
              "name": "duration_minutes",
              "signature": "duration_minutes(self) -> int",
              "summary": "Exact delivery duration in whole minutes."
            },
            {
              "name": "duration_hours",
              "signature": "duration_hours(self) -> float",
              "summary": "Exact delivery duration in hours, used for MW-to-MWh cash-flow conversion."
            }
          ],
          "fields": [
            {
              "name": "start_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "end_utc",
              "type": "datetime",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/interval.py",
          "line": 26
        },
        {
          "name": "PowerHedgeContract",
          "module": "models",
          "qualified": "quantvolt.models.power_hedge.PowerHedgeContract",
          "kind": "class",
          "signature": "PowerHedgeContract(hedge_id: str, hedge_type: PowerHedgeType, position: PowerHedgePosition, start_utc: datetime, end_utc: datetime, volume_mwh: float, strike_per_mwh: float, upper_strike_per_mwh: float | None = None, allocated_premium_per_mwh: float = 0.0)",
          "summary": "Terms for one realized, financially settled power hedge.",
          "doc": "Terms for one realized, financially settled power hedge.\n\n``allocated_premium_per_mwh`` is an explicit allocation to each delivery\ninterval, not an option valuation. Long positions pay it and short positions\nreceive it. A long collar owns the floor and writes the cap.",
          "methods": [
            {
              "name": "covers",
              "signature": "covers(self, interval: PowerDeliveryInterval) -> bool",
              "summary": "Whether the complete delivery interval is inside the hedge term."
            }
          ],
          "fields": [
            {
              "name": "hedge_id",
              "type": "str",
              "default": null
            },
            {
              "name": "hedge_type",
              "type": "PowerHedgeType",
              "default": null
            },
            {
              "name": "position",
              "type": "PowerHedgePosition",
              "default": null
            },
            {
              "name": "start_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "end_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "volume_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "strike_per_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "upper_strike_per_mwh",
              "type": "float | None",
              "default": "None"
            },
            {
              "name": "allocated_premium_per_mwh",
              "type": "float",
              "default": "0.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/power_hedge.py",
          "line": 36
        },
        {
          "name": "PowerHedgePosition",
          "module": "models",
          "qualified": "quantvolt.models.power_hedge.PowerHedgePosition",
          "kind": "class",
          "signature": "PowerHedgePosition()",
          "summary": "Payoff ownership; long swap means receive fixed and pay floating.",
          "doc": "Payoff ownership; long swap means receive fixed and pay floating.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "LONG",
              "value": "'long'"
            },
            {
              "name": "SHORT",
              "value": "'short'"
            }
          ],
          "source": "src/quantvolt/models/power_hedge.py",
          "line": 28
        },
        {
          "name": "PowerHedgeType",
          "module": "models",
          "qualified": "quantvolt.models.power_hedge.PowerHedgeType",
          "kind": "class",
          "signature": "PowerHedgeType()",
          "summary": "Supported realized payoff shapes.",
          "doc": "Supported realized payoff shapes.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "FIXED_PRICE_SWAP",
              "value": "'fixed_price_swap'"
            },
            {
              "name": "CAP",
              "value": "'cap'"
            },
            {
              "name": "FLOOR",
              "value": "'floor'"
            },
            {
              "name": "COLLAR",
              "value": "'collar'"
            }
          ],
          "source": "src/quantvolt/models/power_hedge.py",
          "line": 19
        },
        {
          "name": "PpaContract",
          "module": "models",
          "qualified": "quantvolt.models.ppa.PpaContract",
          "kind": "class",
          "signature": "PpaContract(contract_id: str, bidding_zone: str, fixed_price_per_mwh: float, start_utc: datetime, end_utc: datetime, volume_basis: PpaVolumeBasis, settlement_type: PpaSettlementType = PpaSettlementType.PHYSICAL, counterparty: str | None = None)",
          "summary": "Producer-side PPA commercial terms.",
          "doc": "Producer-side PPA commercial terms.\n\nThe interval volume is deliberately supplied to settlement rather than\nembedded here: a shaped profile can contain tens of thousands of intervals,\nwhile a pay-as-produced profile is known only after metering.",
          "methods": [
            {
              "name": "covers",
              "signature": "covers(self, interval: PowerDeliveryInterval) -> bool",
              "summary": "Whether the complete interval falls inside the PPA delivery term."
            }
          ],
          "fields": [
            {
              "name": "contract_id",
              "type": "str",
              "default": null
            },
            {
              "name": "bidding_zone",
              "type": "str",
              "default": null
            },
            {
              "name": "fixed_price_per_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "start_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "end_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "volume_basis",
              "type": "PpaVolumeBasis",
              "default": null
            },
            {
              "name": "settlement_type",
              "type": "PpaSettlementType",
              "default": "PpaSettlementType.PHYSICAL"
            },
            {
              "name": "counterparty",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/ppa.py",
          "line": 29
        },
        {
          "name": "PpaSettlementType",
          "module": "models",
          "qualified": "quantvolt.models.ppa.PpaSettlementType",
          "kind": "class",
          "signature": "PpaSettlementType()",
          "summary": "Whether the PPA delivers energy or settles only its fixed-for-floating difference.",
          "doc": "Whether the PPA delivers energy or settles only its fixed-for-floating difference.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "PHYSICAL",
              "value": "'physical'"
            },
            {
              "name": "FINANCIAL_CFD",
              "value": "'financial_cfd'"
            }
          ],
          "source": "src/quantvolt/models/ppa.py",
          "line": 21
        },
        {
          "name": "PpaVolumeBasis",
          "module": "models",
          "qualified": "quantvolt.models.ppa.PpaVolumeBasis",
          "kind": "class",
          "signature": "PpaVolumeBasis()",
          "summary": "How the contracted energy volume is determined for each interval.",
          "doc": "How the contracted energy volume is determined for each interval.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "BASELOAD",
              "value": "'baseload'"
            },
            {
              "name": "SHAPED",
              "value": "'shaped'"
            },
            {
              "name": "PAY_AS_PRODUCED",
              "value": "'pay_as_produced'"
            }
          ],
          "source": "src/quantvolt/models/ppa.py",
          "line": 13
        },
        {
          "name": "RiskType",
          "module": "models",
          "qualified": "quantvolt.models.instruments.RiskType",
          "kind": "class",
          "signature": "RiskType()",
          "summary": "Risk categories for derivatives and physical positions.",
          "doc": "Risk categories for derivatives and physical positions.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "EXECUTION",
              "value": "'execution'"
            },
            {
              "name": "BASIS",
              "value": "'basis'"
            },
            {
              "name": "LIQUIDITY",
              "value": "'liquidity'"
            },
            {
              "name": "CREDIT",
              "value": "'credit'"
            },
            {
              "name": "STORAGE",
              "value": "'storage'"
            },
            {
              "name": "TRANSMISSION",
              "value": "'transmission'"
            }
          ],
          "source": "src/quantvolt/models/instruments.py",
          "line": 46
        },
        {
          "name": "SettlementType",
          "module": "models",
          "qualified": "quantvolt.models.instruments.SettlementType",
          "kind": "class",
          "signature": "SettlementType()",
          "summary": "How a contract settles at delivery.",
          "doc": "How a contract settles at delivery.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "PHYSICAL",
              "value": "'physical'"
            },
            {
              "name": "FINANCIAL",
              "value": "'financial'"
            }
          ],
          "source": "src/quantvolt/models/instruments.py",
          "line": 24
        },
        {
          "name": "SwapContract",
          "module": "models",
          "qualified": "quantvolt.models.instruments.SwapContract",
          "kind": "class",
          "signature": "SwapContract(commodity: CommodityConfig, fixed_rate: float, floating_index: str, notional: float, schedule: DeliverySchedule, granularity: Granularity = Granularity.MONTHLY)",
          "summary": "Fixed-for-floating swap — OTC, customisable, financial settlement.",
          "doc": "Fixed-for-floating swap — OTC, customisable, financial settlement.",
          "methods": [],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "fixed_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "floating_index",
              "type": "str",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "schedule",
              "type": "DeliverySchedule",
              "default": null
            },
            {
              "name": "granularity",
              "type": "Granularity",
              "default": "Granularity.MONTHLY"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 102
        },
        {
          "name": "TransmissionRight",
          "module": "models",
          "qualified": "quantvolt.models.instruments.TransmissionRight",
          "kind": "class",
          "signature": "TransmissionRight(origin: str, destination: str, tariff: float, quantity: float, schedule: DeliverySchedule, direction: TransportDirection = TransportDirection.A_TO_B, loss: float = 0.0, capacity: float | None = None, reverse_tariff: float | None = None)",
          "summary": "A right to move **power** from origin hub A to destination hub B (Req 24).",
          "doc": "A right to move **power** from origin hub A to destination hub B (Req 24).\n\nThe per-period payoff to the holder is ``Q_delivered * max(P_B - P_A - T_AB, 0)``\n(§12): buy at the origin ``P_A``, pay the transport tariff ``T_AB``, sell at the\ndestination ``P_B`` — an option exercised only when the locational spread covers\nthe tariff. ``delivered = quantity * (1 - loss)``, further capped by ``capacity``.\n\nFields:\n    origin: commodity_id of hub A (the origin forward curve). Matched against\n        the origin curve's commodity when priced.\n    destination: commodity_id of hub B (the destination forward curve).\n    tariff: per-period transport cost T_AB (>= 0), in the price unit.\n    quantity: per-period available quantity Q (>= 0).\n    schedule: the delivery periods the right covers.\n    direction: A_TO_B (default), B_TO_A, or BIDIRECTIONAL.\n    loss: transmission loss fraction in [0, 1); delivered = Q * (1 - loss).\n    capacity: optional physical cap; effective quantity = min(Q, capacity).\n    reverse_tariff: T_BA (>= 0) for the B->A leg of a BIDIRECTIONAL right;\n        when omitted a bidirectional right reuses ``tariff`` symmetrically.",
          "methods": [],
          "fields": [
            {
              "name": "origin",
              "type": "str",
              "default": null
            },
            {
              "name": "destination",
              "type": "str",
              "default": null
            },
            {
              "name": "tariff",
              "type": "float",
              "default": null
            },
            {
              "name": "quantity",
              "type": "float",
              "default": null
            },
            {
              "name": "schedule",
              "type": "DeliverySchedule",
              "default": null
            },
            {
              "name": "direction",
              "type": "TransportDirection",
              "default": "TransportDirection.A_TO_B"
            },
            {
              "name": "loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "capacity",
              "type": "float | None",
              "default": "None"
            },
            {
              "name": "reverse_tariff",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/instruments.py",
          "line": 157
        },
        {
          "name": "TransportDirection",
          "module": "models",
          "qualified": "quantvolt.models.instruments.TransportDirection",
          "kind": "class",
          "signature": "TransportDirection()",
          "summary": "Permitted flow direction of a transmission (power) or pipeline (gas) right.",
          "doc": "Permitted flow direction of a transmission (power) or pipeline (gas) right.\n\n``A_TO_B`` / ``B_TO_A`` are one-way rights (origin A -> destination B, or the\nreverse). ``BIDIRECTIONAL`` is a single capacity unit usable in *either*\ndirection per period — the holder commits it to the economically best flow, so\na bidirectional right is worth no more than owning both one-way rights (Property\n68 subadditivity).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "A_TO_B",
              "value": "'a_to_b'"
            },
            {
              "name": "B_TO_A",
              "value": "'b_to_a'"
            },
            {
              "name": "BIDIRECTIONAL",
              "value": "'bidirectional'"
            }
          ],
          "source": "src/quantvolt/models/instruments.py",
          "line": 31
        },
        {
          "name": "VolatilitySurface",
          "module": "models",
          "qualified": "quantvolt.models.vol_surface.VolatilitySurface",
          "kind": "class",
          "signature": "VolatilitySurface(commodity: CommodityConfig, tenors: tuple[VolatilityTenor, ...])",
          "summary": "A commodity's implied-vol term structure, one :class:`VolatilityTenor` per period.",
          "doc": "A commodity's implied-vol term structure, one :class:`VolatilityTenor` per period.\n\nConsistency invariants (validated eagerly in :meth:`__post_init__`):\n\n- ``tenors`` is non-empty.\n- ``tenors`` is strictly increasing by :attr:`VolatilityTenor.period`, so there\n  are no duplicate periods; the surface validates this for itself rather than\n  trusting callers (Tell-Don't-Ask).",
          "methods": [
            {
              "name": "sigma_at",
              "signature": "sigma_at(self, period: DeliveryPeriod) -> float",
              "summary": "Annualised implied vol for an exact ``period`` match."
            }
          ],
          "fields": [
            {
              "name": "commodity",
              "type": "CommodityConfig",
              "default": null
            },
            {
              "name": "tenors",
              "type": "tuple[VolatilityTenor, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/vol_surface.py",
          "line": 43
        },
        {
          "name": "VolatilityTenor",
          "module": "models",
          "qualified": "quantvolt.models.vol_surface.VolatilityTenor",
          "kind": "class",
          "signature": "VolatilityTenor(period: DeliveryPeriod, sigma: float)",
          "summary": "A single point on the vol term structure: an implied vol for one delivery period.",
          "doc": "A single point on the vol term structure: an implied vol for one delivery period.\n\n``sigma`` is an annualised implied volatility and is validated eagerly to be\nstrictly positive in :meth:`__post_init__`.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/models/vol_surface.py",
          "line": 28
        },
        {
          "name": "merge_commodities",
          "module": "models",
          "qualified": "quantvolt.models.commodity.merge_commodities",
          "kind": "function",
          "signature": "merge_commodities(extra_commodities: dict[str, CommodityConfig] | None=None) -> dict[str, CommodityConfig]",
          "summary": "Return a new registry: ``extra_commodities`` merged OVER the built-ins.",
          "doc": "Return a new registry: ``extra_commodities`` merged OVER the built-ins.\n\nCaller-supplied entries win on id collision (Adapter seam, Req 1.6). Neither\n:data:`BUILT_IN_COMMODITIES` nor ``extra_commodities`` is mutated — the result\nis a fresh dict. ``CurveBuilder`` reuses this to assemble its registry.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 49
        },
        {
          "name": "resolve_commodity",
          "module": "models",
          "qualified": "quantvolt.models.commodity.resolve_commodity",
          "kind": "function",
          "signature": "resolve_commodity(commodity_id: str, extra_commodities: dict[str, CommodityConfig] | None=None) -> CommodityConfig",
          "summary": "Look up ``commodity_id`` in the merged registry (caller entries take precedence).",
          "doc": "Look up ``commodity_id`` in the merged registry (caller entries take precedence).\n\nRaises :class:`ValidationError` naming the unknown id and listing the available\nids when no match is found.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 64
        },
        {
          "name": "BUILT_IN_COMMODITIES",
          "module": "models",
          "qualified": "quantvolt.models.commodity.BUILT_IN_COMMODITIES",
          "kind": "constant",
          "signature": "BUILT_IN_COMMODITIES",
          "summary": "Read-only-by-convention registry of the package's built-in European power, gas and carbon commodity definitions, keyed by stable commodity ID..",
          "doc": "Read-only-by-convention registry of the package's built-in European power, gas and carbon commodity definitions, keyed by stable commodity ID.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/models/commodity.py",
          "line": 1
        }
      ]
    },
    {
      "name": "numerics",
      "qualified": "quantvolt.numerics",
      "description": "Pure numerical kernels for pricing, simulation and interpolation.",
      "symbols": [
        {
          "name": "CorrelatedSimulationRequest",
          "module": "numerics",
          "qualified": "quantvolt.numerics.monte_carlo.CorrelatedSimulationRequest",
          "kind": "class",
          "signature": "CorrelatedSimulationRequest(z0: npt.ArrayLike, drift_steps: npt.ArrayLike, covariance_steps: npt.ArrayLike, path_count: int, seed: int, active_steps: npt.ArrayLike | None = None, antithetic: bool = True, repair: bool = False, symmetry_tol: float = field(default=_SYMMETRY_TOL, kw_only=True), psd_tol: float = field(default=_PSD_EIG_TOL, kw_only=True))",
          "summary": "Inputs for a time-varying correlated state simulation.",
          "doc": "Inputs for a time-varying correlated state simulation.\n\nRows of ``drift_steps`` and ``covariance_steps`` are Appendix A's ``mu_t`` and\n``C_t``. ``active_steps[t, d]`` represents the advancing live-tenor set: an inactive\ncoordinate is held fixed during that step. If omitted, positive step variance defines\nactivity. Arrays are copied at the public boundary before entering the native kernel.\n\n``symmetry_tol`` and ``psd_tol`` gate the per-step covariance validation (Property 61\n/ Req 20.3); defaults match the module's standard tolerances.\n\n``eq=False`` disables the auto-generated field-tuple ``__eq__`` (Fix 9): dataclass\nequality by default compares fields with plain ``==``, and NumPy arrays make that\nambiguous (``ValueError: The truth value of an array ... is ambiguous``) — which broke\nboth ``req == deepcopy(req)`` and the shipped\n:func:`~quantvolt.testing.assert_input_unchanged` on this request type, since that\nutility's mutation check falls back to plain ``==`` for a non-array, non-Polars input.\n:meth:`__eq__` below compares array fields via :func:`numpy.array_equal` and every\nother field via plain ``==``. With ``eq=False`` dataclass leaves ``__hash__``\nuntouched (falling back to ``object``'s identity-based hash); this request is a bag of\nmutable-looking array-like fields with no principled value-hash, so identity hashing\nis an acceptable, documented consequence, not a further defect.",
          "methods": [],
          "fields": [
            {
              "name": "z0",
              "type": "npt.ArrayLike",
              "default": null
            },
            {
              "name": "drift_steps",
              "type": "npt.ArrayLike",
              "default": null
            },
            {
              "name": "covariance_steps",
              "type": "npt.ArrayLike",
              "default": null
            },
            {
              "name": "path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "seed",
              "type": "int",
              "default": null
            },
            {
              "name": "active_steps",
              "type": "npt.ArrayLike | None",
              "default": "None"
            },
            {
              "name": "antithetic",
              "type": "bool",
              "default": "True"
            },
            {
              "name": "repair",
              "type": "bool",
              "default": "False"
            },
            {
              "name": "symmetry_tol",
              "type": "float",
              "default": "field(default=_SYMMETRY_TOL, kw_only=True)"
            },
            {
              "name": "psd_tol",
              "type": "float",
              "default": "field(default=_PSD_EIG_TOL, kw_only=True)"
            }
          ],
          "members": [],
          "source": "src/quantvolt/numerics/monte_carlo.py",
          "line": 74
        },
        {
          "name": "DriftKind",
          "module": "numerics",
          "qualified": "quantvolt.numerics.risk_adjustment.DriftKind",
          "kind": "class",
          "signature": "DriftKind()",
          "summary": "Probability measure a drift belongs to (used by the physical-drift guard).",
          "doc": "Probability measure a drift belongs to (used by the physical-drift guard).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "PHYSICAL",
              "value": "'physical'"
            },
            {
              "name": "RISK_NEUTRAL",
              "value": "'risk_neutral'"
            }
          ],
          "source": "src/quantvolt/numerics/risk_adjustment.py",
          "line": 52
        },
        {
          "name": "InterpolationMethod",
          "module": "numerics",
          "qualified": "quantvolt.numerics.interpolation.InterpolationMethod",
          "kind": "class",
          "signature": "InterpolationMethod()",
          "summary": "Type alias restricting interpolation selection to the supported piecewise-flat, piecewise-linear and cubic-spline method names..",
          "doc": "Type alias restricting interpolation selection to the supported piecewise-flat, piecewise-linear and cubic-spline method names.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/interpolation.py",
          "line": 20
        },
        {
          "name": "PriceOfRiskKind",
          "module": "numerics",
          "qualified": "quantvolt.numerics.risk_adjustment.PriceOfRiskKind",
          "kind": "class",
          "signature": "PriceOfRiskKind()",
          "summary": "Provenance of a price of risk lambda. Stated by the caller, never inferred.",
          "doc": "Provenance of a price of risk lambda. Stated by the caller, never inferred.\n\nThe two kinds produce the *same* risk-adjustment arithmetic (eqs 10.4 to 10.6);\nthey differ only in where lambda comes from and therefore in how it may be used.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "MARKET",
              "value": "'market'"
            },
            {
              "name": "CORPORATE",
              "value": "'corporate'"
            }
          ],
          "source": "src/quantvolt/numerics/risk_adjustment.py",
          "line": 41
        },
        {
          "name": "actual_360",
          "module": "numerics",
          "qualified": "quantvolt.numerics.daycount.actual_360",
          "kind": "function",
          "signature": "actual_360(start: date, end: date) -> float",
          "summary": "Fractional years between ``start`` and ``end`` under the actual/360 convention.",
          "doc": "Fractional years between ``start`` and ``end`` under the actual/360 convention.\n\nComputed as the *actual* number of calendar days elapsed (so leap days such\nas 29 Feb are counted) divided by a fixed 360.0 — the money-market convention\nused for some gas/power short-tenor instruments.\n\nThe result is **signed**: when ``end`` precedes ``start`` the day difference is\nnegative and the returned fraction is negative. Coincident dates yield ``0.0``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/daycount.py",
          "line": 20
        },
        {
          "name": "actual_365",
          "module": "numerics",
          "qualified": "quantvolt.numerics.daycount.actual_365",
          "kind": "function",
          "signature": "actual_365(start: date, end: date) -> float",
          "summary": "Fractional years between ``start`` and ``end`` under the actual/365 convention.",
          "doc": "Fractional years between ``start`` and ``end`` under the actual/365 convention.\n\nComputed as the *actual* number of calendar days elapsed (so leap days such\nas 29 Feb are counted) divided by a fixed 365.0.\n\nThe result is **signed**: when ``end`` precedes ``start`` the day difference is\nnegative and the returned fraction is negative. Coincident dates yield ``0.0``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/daycount.py",
          "line": 8
        },
        {
          "name": "asian_monte_carlo",
          "module": "numerics",
          "qualified": "quantvolt.numerics.monte_carlo.asian_monte_carlo",
          "kind": "function",
          "signature": "asian_monte_carlo(forward: float, strike: float, sigma: float, time_to_expiry: float, discount_factor: float, averaging_points: int, option_type: Literal['call', 'put'], geometric: bool, seed: int, path_count: int, *, antithetic: bool=True) -> tuple[float, float]",
          "summary": "Return ``(premium, standard_error)`` via the Rust MC kernel.",
          "doc": "Return ``(premium, standard_error)`` via the Rust MC kernel.\n\nArgs:\n    antithetic: Draw paths in ``(+eps, -eps)`` antithetic-variate pairs\n        (default ``True``, matching the kernel's previous always-on\n        behavior). ``False`` draws every path independently.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/monte_carlo.py",
          "line": 133
        },
        {
          "name": "barrier_analytic",
          "module": "numerics",
          "qualified": "quantvolt.numerics.exotic.barrier_analytic",
          "kind": "function",
          "signature": "barrier_analytic(option_type: Literal['call', 'put'], barrier_type: Literal['up_in', 'up_out', 'down_in', 'down_out'], forward: float, strike: float, barrier: float, sigma: float, time_to_expiry: float, discount_factor: float) -> float",
          "summary": "Single-barrier option, Reiner-Rubinstein / Merton closed form (no rebate).",
          "doc": "Single-barrier option, Reiner-Rubinstein / Merton closed form (no rebate).\n\nThe full set of ``{up, down} x {in, out} x {call, put}`` barriers is assembled from the\nstandard building blocks ``A, B, C, D`` (Haug, *The Complete Guide to Option Pricing\nFormulas*), with ``phi = +1`` for a call / ``-1`` for a put and ``eta = +1`` for a *down*\nbarrier / ``-1`` for an *up* barrier. With the forward-world carry ``b == 0`` the drift\nparameter is ``mu = -1/2`` and ``exp((b-r)T) = DF``, so block ``A`` reduces exactly to the\nvanilla Black-76 premium. Because a knock-in and its matching knock-out partition that\nvanilla premium, ``in + out`` reprices the vanilla by construction (in/out parity, rebate 0).\n\nThe combination selected depends on whether the strike sits above or below the barrier, per\nthe Reiner-Rubinstein table; the choice of blocks is a dispatch on\n``(option_type, barrier_type)`` rather than a nested switch.\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    barrier_type: ``\"up_in\"``, ``\"up_out\"``, ``\"down_in\"`` or ``\"down_out\"``.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    barrier: Barrier level (``H``); must sit above ``F`` for *up* and below ``F`` for *down*.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n\nReturns:\n    The discounted single-barrier option premium (no rebate).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/exotic.py",
          "line": 151
        },
        {
          "name": "black76_greeks",
          "module": "numerics",
          "qualified": "quantvolt.numerics.black76.black76_greeks",
          "kind": "function",
          "signature": "black76_greeks(option_type: Literal['call', 'put'], forward: float, strike: float, sigma: float, time_to_expiry: float, discount_factor: float) -> Greeks",
          "summary": "Black-76 sensitivities for a European option on a forward.",
          "doc": "Black-76 sensitivities for a European option on a forward.\n\nSign conventions (each sensitivity is per unit of the named input):\n\n- ``delta`` = ``d(price)/d(forward)`` = ``DF*N(d1)`` (call), ``DF*(N(d1)-1)`` (put).\n- ``gamma`` = second derivative of price w.r.t. the forward =\n  ``DF*n(d1)/(F*sigma*sqrt(T))`` — identical for call and put.\n- ``vega``  = ``d(price)/d(sigma)`` = ``DF*F*n(d1)*sqrt(T)`` per unit vol —\n  identical for call and put, and strictly positive.\n- ``theta`` = time *decay* ``-d(price)/d(T)`` (negative for a long option when\n  ``r == 0``) = ``r*price - DF*F*n(d1)*sigma/(2*sqrt(T))`` with ``r = -ln(DF)/T``.\n- ``rho``   = ``d(price)/d(r)`` with the forward held fixed and ``DF = e^{-rT}``\n  = ``-T*price`` (uses the call price for a call, the put price for a put).\n\nWhen ``sigma*sqrt(T)`` collapses to zero (zero vol or zero time-to-expiry) the\nforward is deterministic, exactly as in :func:`black76_price`, and this function\nfalls back to the degenerate limit (:func:`_black76_greeks_degenerate`): ``gamma``\nand ``vega`` vanish, ``delta`` is a step at the strike (``DF/2`` at ``F == K``, by\nconvention — see :func:`_black76_greeks_degenerate`), ``theta`` keeps only the\ndiscounting-carry term, and ``rho`` is unchanged.\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n\nReturns:\n    A :class:`Greeks` value object ``(delta, gamma, vega, theta, rho)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/black76.py",
          "line": 158
        },
        {
          "name": "black76_implied_vol",
          "module": "numerics",
          "qualified": "quantvolt.numerics.black76.black76_implied_vol",
          "kind": "function",
          "signature": "black76_implied_vol(option_type: Literal['call', 'put'], market_premium: float, forward: float, strike: float, time_to_expiry: float, discount_factor: float, tol: float=0.0001, *, vol_lower: float=1e-09, vol_upper: float=10.0, max_iter: int=100) -> float",
          "summary": "Recover the Black-76 volatility that reprices ``market_premium``.",
          "doc": "Recover the Black-76 volatility that reprices ``market_premium``.\n\nThe premium is monotonically increasing in ``sigma``, bounded below by the\ndiscounted intrinsic value (as ``sigma -> 0``) and above by the discounted\nforward/strike (as ``sigma -> inf``). The market premium must therefore lie\nstrictly inside those no-arbitrage bounds, checked *before* inversion\n(Req 5.3):\n\n- call: ``DF*max(F-K, 0) < premium < DF*F``\n- put:  ``DF*max(K-F, 0) < premium < DF*K``\n\nA premium outside its bounds cannot be reproduced by any volatility, so this\nis a numeric precondition on the caller-supplied premium and raises\n:class:`~quantvolt.exceptions.NumericalError` (a ``ValueError`` subclass, for\ncompatibility with callers using the low-level kernel API directly).\nInversion then uses Brent's method over ``[vol_lower, vol_upper]`` (default\n``[1e-9, 10.0]``) — a bracketing solver, so it cannot diverge near zero vega\nthe way Newton-Raphson would (design §2.7).\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    market_premium: Observed (discounted) option premium to invert.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n    tol: Absolute x-tolerance on the recovered volatility.\n    vol_lower: Lower Brent bracket endpoint for the recovered volatility,\n        must be strictly positive.\n    vol_upper: Upper Brent bracket endpoint, must be strictly greater than\n        ``vol_lower``.\n    max_iter: Maximum number of Brent iterations.\n\nReturns:\n    The implied volatility ``sigma`` located in ``[vol_lower, vol_upper]``.\n\nRaises:\n    NumericalError: If ``market_premium`` lies outside the no-arbitrage bounds,\n        or if ``vol_lower``/``vol_upper`` do not form a valid bracket.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/black76.py",
          "line": 220
        },
        {
          "name": "black76_price",
          "module": "numerics",
          "qualified": "quantvolt.numerics.black76.black76_price",
          "kind": "function",
          "signature": "black76_price(option_type: Literal['call', 'put'], forward: float, strike: float, sigma: float, time_to_expiry: float, discount_factor: float) -> float",
          "summary": "Black-76 discounted premium for a European option on a forward.",
          "doc": "Black-76 discounted premium for a European option on a forward.\n\n``d1 = (ln(F/K) + 0.5*sigma**2*T) / (sigma*sqrt(T))``,\n``d2 = d1 - sigma*sqrt(T)``,\n``call = DF*(F*N(d1) - K*N(d2))``, ``put = DF*(K*N(-d2) - F*N(-d1))``.\n\nWhen ``sigma*sqrt(T)`` collapses to zero (zero vol or zero time-to-expiry)\nthe forward is deterministic, so the premium falls back to the discounted\nintrinsic value: ``DF*max(F-K, 0)`` for a call, ``DF*max(K-F, 0)`` for a put.\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n\nReturns:\n    The discounted option premium.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/black76.py",
          "line": 58
        },
        {
          "name": "brent_root",
          "module": "numerics",
          "qualified": "quantvolt.numerics.rootfind.brent_root",
          "kind": "function",
          "signature": "brent_root(f: Callable[[float], float], a: float, b: float, tol: float=0.0001, max_iter: int=100) -> float",
          "summary": "Find a root of ``f`` in ``[a, b]`` via Brent's method.",
          "doc": "Find a root of ``f`` in ``[a, b]`` via Brent's method.\n\nThin wrapper over :func:`scipy.optimize.brentq`. Brent's method is a\nbracketing solver, chosen over Newton-Raphson for implied-vol inversion so\nthat it cannot diverge near zero vega (design note §2.7).\n\nArgs:\n    f: Continuous scalar function to solve ``f(x) == 0``.\n    a: Lower bracket endpoint.\n    b: Upper bracket endpoint.\n    tol: Absolute x-tolerance (``xtol``) for convergence.\n    max_iter: Maximum number of iterations (``maxiter``).\n\nReturns:\n    The located root ``x`` in ``[a, b]``.\n\nRaises:\n    NumericalError: If ``f(a)`` and ``f(b)`` share the same sign and therefore\n        do not bracket a root.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/rootfind.py",
          "line": 18
        },
        {
          "name": "build_covariance",
          "module": "numerics",
          "qualified": "quantvolt.numerics.monte_carlo.build_covariance",
          "kind": "function",
          "signature": "build_covariance(sigma: npt.ArrayLike, corr: npt.ArrayLike, dt: float, *, symmetry_tol: float=_SYMMETRY_TOL, unit_diagonal_tol: float=_UNIT_DIAGONAL_TOL) -> npt.NDArray[np.float64]",
          "summary": "Assemble the one-step covariance ``C = diag(sigma)·R·diag(sigma)·Δt`` (Appendix A, eq A.8).",
          "doc": "Assemble the one-step covariance ``C = diag(sigma)·R·diag(sigma)·Δt`` (Appendix A, eq A.8).\n\n``sigma`` is the flat per-index instantaneous volatility vector over the flattened\ncommodity/tenor state, ``corr`` the ``(D, D)`` cross-commodity/cross-tenor\ncorrelation matrix ``R`` (eq A.7), and ``dt`` the step length ``Δt``. Entry\n``C[a, b] = sigma_a · R[a, b] · sigma_b · Δt``.\n\nA per-index ``sigma = 0`` marks an **expired tenor** (eq A.5): it zeroes that row and\ncolumn of ``C``, and the simulator then holds that state fixed. Validation is eager\n(Req 11.5): ``dt > 0``; ``sigma`` finite and non-negative; ``corr`` square, finite,\nsymmetric (within ``symmetry_tol``), unit-diagonal (within ``unit_diagonal_tol``),\nentries in ``[-1, 1]``. The assembled matrix is *not* PSD-checked here — that gate\nlives in :func:`simulate_correlated_forwards`, which consumes it.\n\nArgs:\n    sigma: Flat per-index volatility vector.\n    corr: ``(D, D)`` correlation matrix ``R``.\n    dt: Step length ``Δt``, positive.\n    symmetry_tol: Maximum tolerated ``max(|R - Rᵀ|)`` asymmetry.\n    unit_diagonal_tol: Maximum tolerated deviation of ``diag(R)`` from 1.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/monte_carlo.py",
          "line": 227
        },
        {
          "name": "cubic_spline",
          "module": "numerics",
          "qualified": "quantvolt.numerics.interpolation.cubic_spline",
          "kind": "function",
          "signature": "cubic_spline(knot_times: NDArray[np.float64], knot_prices: NDArray[np.float64], query_times: NDArray[np.float64], *, bc_type: str='natural') -> NDArray[np.float64]",
          "summary": "Cubic spline through the knots via :class:`scipy.interpolate.CubicSpline`.",
          "doc": "Cubic spline through the knots via :class:`scipy.interpolate.CubicSpline`.\n\n``bc_type`` selects the boundary condition (default ``\"natural\"``, which sets\nthe second derivative to zero at both ends). The spline passes through every\nknot exactly regardless of ``bc_type``.\n\nArgs:\n    knot_times: Strictly increasing knot times.\n    knot_prices: Knot prices, same length as ``knot_times``.\n    query_times: Times at which to evaluate the spline.\n    bc_type: One of ``\"not-a-knot\"``, ``\"periodic\"``, ``\"clamped\"``,\n        ``\"natural\"`` — the boundary condition passed to\n        :class:`scipy.interpolate.CubicSpline`.\n\nRaises:\n    NumericalError: If ``bc_type`` is not one of the supported string values,\n        or if :class:`scipy.interpolate.CubicSpline` itself rejects the knots\n        (e.g. non-increasing ``knot_times``, mismatched lengths, too few knots,\n        or mismatched periodic endpoints) — mirroring\n        :func:`~quantvolt.numerics.rootfind.brent_root`'s wrapping of scipy\n        errors, so no raw ``ValueError`` escapes this package's exception\n        hierarchy (``coding-style.md`` §7).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/interpolation.py",
          "line": 65
        },
        {
          "name": "finite_difference_bump",
          "module": "numerics",
          "qualified": "quantvolt.numerics.rootfind.finite_difference_bump",
          "kind": "function",
          "signature": "finite_difference_bump(f: Callable[[float], float], x: float, bump: float) -> float",
          "summary": "Central difference: ``(f(x + bump) - f(x - bump)) / (2 * bump)``.",
          "doc": "Central difference: ``(f(x + bump) - f(x - bump)) / (2 * bump)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/rootfind.py",
          "line": 63
        },
        {
          "name": "kemna_vorst",
          "module": "numerics",
          "qualified": "quantvolt.numerics.exotic.kemna_vorst",
          "kind": "function",
          "signature": "kemna_vorst(forward: float, strike: float, sigma: float, time_to_expiry: float, discount_factor: float, option_type: Literal['call', 'put']) -> float",
          "summary": "Geometric-average Asian option, Kemna-Vorst *exact* closed form.",
          "doc": "Geometric-average Asian option, Kemna-Vorst *exact* closed form.\n\nThe continuous geometric average of a lognormal forward is itself lognormal, so the option\nis priced exactly by Black-76 on an adjusted forward and volatility:\n``sigma_g = sigma/sqrt(3)`` and ``F_g = F*exp(-sigma**2*T/12)`` (the convexity correction\nof the geometric average under the forward measure with ``b == 0``). Geometric averaging\nlowers both the effective level and the effective volatility, so this price sits below the\ncorresponding vanilla Black-76 premium. The ``sigma -> 0`` limit is handled inside\n:func:`~quantvolt.numerics.black76.black76_price` (``F_g -> F``, ``sigma_g -> 0``).\n\nArgs:\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n    option_type: ``\"call\"`` or ``\"put\"``.\n\nReturns:\n    The discounted geometric-average Asian option premium.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/exotic.py",
          "line": 114
        },
        {
          "name": "kirk",
          "module": "numerics",
          "qualified": "quantvolt.numerics.spread_models.kirk",
          "kind": "function",
          "signature": "kirk(forward1: float, forward2: float, strike: float, sigma1: float, sigma2: float, rho: float, time_to_expiry: float, discount_factor: float) -> float",
          "summary": "Kirk's approximation for a call on ``forward1 - forward2 - strike``.",
          "doc": "Kirk's approximation for a call on ``forward1 - forward2 - strike``.\n\nKirk approximates the spread option by treating the shifted short leg\n``F2K = forward2 + strike`` as a single lognormal asset with an effective\nvolatility\n\n    ``sigma_eff = sqrt(sigma1**2 + (sigma2*w)**2 - 2*rho*sigma1*sigma2*w)``\n\nwhere ``w = forward2 / F2K``. When ``strike == 0`` this collapses to the\nexact Margrabe form (``F2K == forward2`` and ``w == 1``). The premium is\nmonotonically decreasing in ``strike``.\n\nThe approximation's domain is exactly ``forward2 + strike > 0``: the shifted\nshort leg ``F2K`` must itself be a positive \"asset\" for Kirk's single-lognormal\ntreatment to mean anything (a lognormal cannot have a non-positive level). So\n``strike`` may be negative, but only down to just above ``-forward2``; at\n``strike == -forward2`` the weight ``w = forward2 / F2K`` divides by zero, and\nbelow it ``F2K < 0`` makes ``log(forward1 / F2K)`` undefined.\n\nArgs:\n    forward1: Forward price of the long leg (``F1``), positive.\n    forward2: Forward price of the short leg (``F2``), positive.\n    strike: Spread strike ``K``; may be negative, zero, or positive, but\n        ``forward2 + strike`` must be strictly positive.\n    sigma1: Volatility of ``forward1``.\n    sigma2: Volatility of ``forward2``.\n    rho: Correlation between the two legs, in ``(-1, 1)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to the settlement date, in ``(0, 1]``.\n\nReturns:\n    The discounted call premium on the spread.\n\nRaises:\n    ValidationError: If ``forward2 + strike`` is not strictly positive (Kirk's\n        approximation has no shifted-asset representation there).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/spread_models.py",
          "line": 64
        },
        {
          "name": "lookback_fixed",
          "module": "numerics",
          "qualified": "quantvolt.numerics.exotic.lookback_fixed",
          "kind": "function",
          "signature": "lookback_fixed(option_type: Literal['call', 'put'], forward: float, strike: float, sigma: float, time_to_expiry: float, discount_factor: float) -> float",
          "summary": "Conze-Viswanathan fixed-strike lookback (running extreme = forward at inception).",
          "doc": "Conze-Viswanathan fixed-strike lookback (running extreme = forward at inception).\n\nA fixed-strike lookback pays ``max(max_t F_t - K, 0)`` (call) or ``max(K - min_t F_t, 0)``\n(put). With the running extreme equal to the forward at inception and the forward-world carry\n``b == 0``:\n\n- Call, ``K > F``: the two leading terms are exactly the vanilla Black-76 call, plus the\n  finite tail :func:`_lookback_tail` struck at ``K``.\n- Call, ``K <= F``: ``max_t F_t >= F >= K`` so the payoff is ``(max_t F_t - F) + (F - K)`` —\n  the discounted deterministic part ``DF*(F - K)`` plus a floating-strike lookback *put*\n  (whose payoff is exactly ``max_t F_t - F_T`` and prices ``DF*(E[max_t F_t] - F)``).\n- Put mirrors the call about ``K = F`` (running minimum), reusing the floating-strike call.\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n\nReturns:\n    The discounted fixed-strike lookback premium.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/exotic.py",
          "line": 281
        },
        {
          "name": "lookback_floating",
          "module": "numerics",
          "qualified": "quantvolt.numerics.exotic.lookback_floating",
          "kind": "function",
          "signature": "lookback_floating(option_type: Literal['call', 'put'], forward: float, sigma: float, time_to_expiry: float, discount_factor: float) -> float",
          "summary": "Goldman-Sosin-Gatto floating-strike lookback (running extreme = forward at inception).",
          "doc": "Goldman-Sosin-Gatto floating-strike lookback (running extreme = forward at inception).\n\nA floating-strike lookback pays ``F_T - min_t F_t`` (call, struck at the running minimum) or\n``max_t F_t - F_T`` (put, struck at the running maximum). At inception the running extreme\nequals the forward, so ``ln(F/extreme) = 0``; with the forward-world carry ``b == 0`` the two\n``N(.)`` terms collapse to ``F*DF*(N(a) - N(-a))`` with ``a = sigma*sqrt(T)/2``, and the\nsingular ``sigma**2/(2b)`` tail is replaced by its finite limit (:func:`_lookback_tail`).\nThe value is strictly positive and dominates the corresponding vanilla premium.\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    forward: Forward price of the underlying (``F``), positive.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n\nReturns:\n    The discounted floating-strike lookback premium.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/exotic.py",
          "line": 248
        },
        {
          "name": "margrabe",
          "module": "numerics",
          "qualified": "quantvolt.numerics.spread_models.margrabe",
          "kind": "function",
          "signature": "margrabe(forward1: float, forward2: float, sigma1: float, sigma2: float, rho: float, time_to_expiry: float, discount_factor: float) -> float",
          "summary": "Zero-strike spread (exchange) option: a call on ``forward1 - forward2``.",
          "doc": "Zero-strike spread (exchange) option: a call on ``forward1 - forward2``.\n\nMargrabe's exact closed form for the option to exchange one asset for\nanother (equivalently, a zero-strike spread call). The spread volatility\n\n    ``sigma = sqrt(sigma1**2 + sigma2**2 - 2*rho*sigma1*sigma2)``\n\nrises as ``rho`` falls, so the premium increases as correlation decreases.\n\nArgs:\n    forward1: Forward price of the long leg (``F1``), positive.\n    forward2: Forward price of the short leg (``F2``), positive.\n    sigma1: Volatility of ``forward1``.\n    sigma2: Volatility of ``forward2``.\n    rho: Correlation between the two legs, in ``(-1, 1)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to the settlement date, in ``(0, 1]``.\n\nReturns:\n    The discounted call premium on the spread.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/spread_models.py",
          "line": 25
        },
        {
          "name": "piecewise_flat",
          "module": "numerics",
          "qualified": "quantvolt.numerics.interpolation.piecewise_flat",
          "kind": "function",
          "signature": "piecewise_flat(knot_times: NDArray[np.float64], knot_prices: NDArray[np.float64], query_times: NDArray[np.float64]) -> NDArray[np.float64]",
          "summary": "Step function: each query holds the price of the nearest knot at-or-below it.",
          "doc": "Step function: each query holds the price of the nearest knot at-or-below it.\n\nA query landing exactly on a knot takes that knot's price; a query before the\nfirst knot takes the first knot's price; a query past the last knot holds the\nlast knot's price. Vectorised via :func:`numpy.searchsorted` (no Python loops).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/interpolation.py",
          "line": 29
        },
        {
          "name": "piecewise_linear",
          "module": "numerics",
          "qualified": "quantvolt.numerics.interpolation.piecewise_linear",
          "kind": "function",
          "signature": "piecewise_linear(knot_times: NDArray[np.float64], knot_prices: NDArray[np.float64], query_times: NDArray[np.float64]) -> NDArray[np.float64]",
          "summary": "Linear interpolation between knots via :func:`numpy.interp`.",
          "doc": "Linear interpolation between knots via :func:`numpy.interp`.\n\nQueries outside the knot range are clamped to the nearest endpoint value.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/interpolation.py",
          "line": 47
        },
        {
          "name": "price_of_risk",
          "module": "numerics",
          "qualified": "quantvolt.numerics.risk_adjustment.price_of_risk",
          "kind": "function",
          "signature": "price_of_risk(mu: float, r: float, sigma: float) -> float",
          "summary": "Price of risk ``lambda = (mu - r)/sigma`` -- excess return per unit vol (eq 10.4).",
          "doc": "Price of risk ``lambda = (mu - r)/sigma`` -- excess return per unit vol (eq 10.4).\n\nArgs:\n    mu: Drift of the underlying under the physical measure.\n    r: Risk-free rate.\n    sigma: Volatility of the underlying, strictly positive.\n\nReturns:\n    The price of risk ``lambda``.\n\nRaises:\n    ValidationError: If ``sigma`` is not strictly positive.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/risk_adjustment.py",
          "line": 59
        },
        {
          "name": "require_physical_drift",
          "module": "numerics",
          "qualified": "quantvolt.numerics.risk_adjustment.require_physical_drift",
          "kind": "function",
          "signature": "require_physical_drift(drift_kind: DriftKind, field_name: str='drift') -> None",
          "summary": "Reject a risk-neutral drift where a physical (P-measure) drift is required.",
          "doc": "Reject a risk-neutral drift where a physical (P-measure) drift is required.\n\nReused by the MC-VaR / CFaR risk engines: real-world risk must evolve under the\nphysical measure P, not the risk-neutral measure Q (Chapter-10 caveat), so a drift\ntagged :attr:`DriftKind.RISK_NEUTRAL` cannot be fed to a loss-distribution\nsimulation. Accepts :attr:`DriftKind.PHYSICAL` silently.\n\nArgs:\n    drift_kind: The measure tag carried on the caller's drift.\n    field_name: Name of the offending caller field, used in the error message.\n\nRaises:\n    ValidationError: If ``drift_kind`` is not :attr:`DriftKind.PHYSICAL`, naming\n        ``field_name`` and the physical-measure requirement.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/risk_adjustment.py",
          "line": 122
        },
        {
          "name": "risk_adjusted_drift",
          "module": "numerics",
          "qualified": "quantvolt.numerics.risk_adjustment.risk_adjusted_drift",
          "kind": "function",
          "signature": "risk_adjusted_drift(mu: float, lambda_s: float, sigma: float) -> float",
          "summary": "Risk-adjusted drift ``mu - lambda_S*sigma`` (eq 10.5).",
          "doc": "Risk-adjusted drift ``mu - lambda_S*sigma`` (eq 10.5).\n\nDrift term of the risk-adjusted process ``dS*/S* = (mu - lambda_S*sigma)dt + sigma*dW``.\n\nArgs:\n    mu: Drift of the underlying under the physical measure.\n    lambda_s: Price of S risk ``lambda_S`` (from :func:`price_of_risk`,\n        :func:`tradable_price_of_risk`, or a caller-supplied corporate value).\n    sigma: Volatility of the underlying, strictly positive.\n\nReturns:\n    The risk-adjusted drift. For a tradable underlying with\n    ``lambda_S = (mu + y - r)/sigma`` this collapses to ``r - y`` (Property 58).\n\nRaises:\n    ValidationError: If ``sigma`` is not strictly positive.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/risk_adjustment.py",
          "line": 100
        },
        {
          "name": "simulate_correlated_forwards",
          "module": "numerics",
          "qualified": "quantvolt.numerics.monte_carlo.simulate_correlated_forwards",
          "kind": "function",
          "signature": "simulate_correlated_forwards(z0: npt.ArrayLike, drift: npt.ArrayLike, cov: npt.ArrayLike, steps: int, path_count: int, seed: int, antithetic: bool=True, *, repair: bool=False, symmetry_tol: float=_SYMMETRY_TOL, psd_tol: float=_PSD_EIG_TOL) -> npt.NDArray[np.float64]",
          "summary": "Simulate correlated multi-commodity log-forward curves (Appendix A, GBM).",
          "doc": "Simulate correlated multi-commodity log-forward curves (Appendix A, GBM).\n\nGiven the initial log-forward vector ``z0 = log F(0, ·)`` (flattened over the\ncommodity/tenor state, dimension ``D``), a per-step drift ``μ`` (``drift``, length\n``D``), and the assembled covariance ``C`` (``cov``, ``(D, D)``), each of ``steps``\nsteps draws ``ε ~ N(0, I)`` and updates ``Z ← Z + μ + L·ε`` where ``L = chol(C)``\n(eqs A.9-A.13). Returns a ``float64`` array of shape ``(n_paths, steps + 1, D)``;\nrecord 0 of each path is ``z0``.\n\nConventions (see ``rust/src/paths.rs``):\n\n* **Measure-agnostic.** The caller supplies ``μ`` under its own measure — physical\n  ``P`` for VaR/scenarios, risk-neutral ``Q`` for pricing (where\n  ``μ = -½·diag(C)`` makes the forward a martingale).\n* **Expired-tenor masking (eq A.5).** A state index with zero variance\n  (``C[d, d] == 0``, i.e. ``sigma_d = 0``) is held fixed at ``z0[d]`` on every path and\n  step — drift and noise both suppressed.\n* **Antithetic variates (default on).** Paths are drawn in ``(+ε, -ε)`` pairs; each\n  pair counts as 2 toward ``path_count`` and an odd ``path_count`` rounds up.\n* **Determinism (Req 11.2).** Identical inputs and ``seed`` give bit-identical paths;\n  the Rust RNG stream does not match NumPy's.\n\nPSD gate (Property 61 / Req 20.3): a non-symmetric or non-PSD ``cov`` raises\n``ValidationError`` naming the violated property; ``repair=True`` opts into a\nnearest-PSD (Higham eigenvalue-clipping) projection instead. ``symmetry_tol`` and\n``psd_tol`` gate that check (defaults match the module's standard tolerances).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/monte_carlo.py",
          "line": 359
        },
        {
          "name": "simulate_correlated_term_structure",
          "module": "numerics",
          "qualified": "quantvolt.numerics.monte_carlo.simulate_correlated_term_structure",
          "kind": "function",
          "signature": "simulate_correlated_term_structure(request: CorrelatedSimulationRequest) -> npt.NDArray[np.float64]",
          "summary": "Simulate Appendix-A paths with step-specific dynamics and tenor activity.",
          "doc": "Simulate Appendix-A paths with step-specific dynamics and tenor activity.\n\nThis is the source-faithful time-inhomogeneous counterpart to\n:func:`simulate_correlated_forwards`. It accepts a parameter object because the\ndynamics, sampling controls, and expiry mask form one related input clump.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/monte_carlo.py",
          "line": 426
        },
        {
          "name": "simulate_ou_paths",
          "module": "numerics",
          "qualified": "quantvolt.numerics.monte_carlo.simulate_ou_paths",
          "kind": "function",
          "signature": "simulate_ou_paths(x0: float, kappa: float, mu: float, sigma: float, dt: float, steps: int, path_count: int, *, seed: int) -> npt.NDArray[np.float64]",
          "summary": "Simulate seeded Ornstein-Uhlenbeck (mean-reverting) paths via the Rust kernel.",
          "doc": "Simulate seeded Ornstein-Uhlenbeck (mean-reverting) paths via the Rust kernel.\n\nEuler recursion ``x_{t+dt} = x_t + kappa*(mu - x_t)*dt + sigma*sqrt(dt)*z``. Returns a\n``float64`` array of shape ``(path_count, steps + 1)`` with ``x0`` in column 0.\nDeterministic per ``seed`` (Req 11.2) — seeded-Rust-RNG reproducible, not\nNumPy-matching. Complements the OU *fit* in ``stats/mean_reversion.py`` (this is the\nforward simulation). Raises ``NativeExtensionError`` if ``_core`` is not built and\n``ValidationError`` for non-finite params, ``dt <= 0``, or ``steps``/``path_count`` < 1.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/monte_carlo.py",
          "line": 191
        },
        {
          "name": "tradable_price_of_risk",
          "module": "numerics",
          "qualified": "quantvolt.numerics.risk_adjustment.tradable_price_of_risk",
          "kind": "function",
          "signature": "tradable_price_of_risk(mu: float, y: float, r: float, sigma: float) -> float",
          "summary": "Price of risk for a fully tradable underlying ``lambda_S = (mu + y - r)/sigma`` (eq 10.6).",
          "doc": "Price of risk for a fully tradable underlying ``lambda_S = (mu + y - r)/sigma`` (eq 10.6).\n\nAdds the net convenience yield ``y`` (including storage costs) to the numerator.\nWhen the underlying is *not* fully hedgeable, lambda_S is instead a free,\ncaller-supplied parameter (Req 19.2) and this function should not be used to derive it.\n\nArgs:\n    mu: Drift of the underlying under the physical measure.\n    y: Net convenience yield including storage costs.\n    r: Risk-free rate.\n    sigma: Volatility of the underlying, strictly positive.\n\nReturns:\n    The tradable price of risk ``lambda_S``.\n\nRaises:\n    ValidationError: If ``sigma`` is not strictly positive.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/risk_adjustment.py",
          "line": 77
        },
        {
          "name": "turnbull_wakeman",
          "module": "numerics",
          "qualified": "quantvolt.numerics.exotic.turnbull_wakeman",
          "kind": "function",
          "signature": "turnbull_wakeman(forward: float, strike: float, sigma: float, time_to_expiry: float, discount_factor: float, option_type: Literal['call', 'put']) -> float",
          "summary": "Arithmetic-average Asian option, Turnbull-Wakeman moment-matched closed form.",
          "doc": "Arithmetic-average Asian option, Turnbull-Wakeman moment-matched closed form.\n\nThe arithmetic average of the forward is not lognormal, so its first two moments under\nthe forward measure are matched to a lognormal and priced with Black-76. With ``b == 0``\nthe expected average equals the forward, ``M1 = F``, and the second moment is\n\n    ``M2 = F**2 * 2*(exp(sigma**2*T) - 1 - sigma**2*T) / (sigma**2*T)**2``.\n\nThe matched volatility is ``sigma_a = sqrt(ln(M2/M1**2)/T)`` and the option is\n``black76_price(option_type, M1, K, sigma_a, T, DF)``. As ``sigma*sqrt(T) -> 0`` the average\nis deterministic (``= F``) and both moments collapse to ``M1**2``, so the price falls back\nto the discounted intrinsic value ``DF*max(F-K, 0)`` (call) / ``DF*max(K-F, 0)`` (put).\n``M1`` cancels out of ``M2/M1**2``, so the moment ratio (:func:`_asian_second_moment_ratio`)\nis evaluated directly in ``var = sigma**2*T``, avoiding the catastrophic cancellation of\na naive ``exp(var) - 1 - var`` for small ``var``.\n\nArgs:\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    sigma: Volatility of the forward, per ``sqrt(year)``.\n    time_to_expiry: Time to expiry in years (``T``).\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n    option_type: ``\"call\"`` or ``\"put\"``.\n\nReturns:\n    The discounted arithmetic-average Asian option premium.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/exotic.py",
          "line": 67
        },
        {
          "name": "INTERPOLATION_METHODS",
          "module": "numerics",
          "qualified": "quantvolt.numerics.interpolation.INTERPOLATION_METHODS",
          "kind": "constant",
          "signature": "INTERPOLATION_METHODS",
          "summary": "Registry mapping every supported interpolation method name to its numerical implementation..",
          "doc": "Registry mapping every supported interpolation method name to its numerical implementation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/numerics/interpolation.py",
          "line": 1
        }
      ]
    },
    {
      "name": "curves",
      "qualified": "quantvolt.curves",
      "description": "Forward-curve construction and no-arbitrage checks.",
      "symbols": [
        {
          "name": "ArbitrageChecker",
          "module": "curves",
          "qualified": "quantvolt.curves.arbitrage.ArbitrageChecker",
          "kind": "class",
          "signature": "ArbitrageChecker()",
          "summary": "Thin class alias over :func:`check_arbitrage` (Task 18).",
          "doc": "Thin class alias over :func:`check_arbitrage` (Task 18).\n\n``ArbitrageChecker`` was originally the sole home of this logic; per\n``coding-style.md`` §0/§2 a stateless single-method class is realised as a\nmodule function instead (the \"lightest Python construct\"). The class is kept\n— delegating to :func:`check_arbitrage` — only because it is part of the\npublic facade and directly exercised by tests as ``ArbitrageChecker().check(...)``.",
          "methods": [
            {
              "name": "check",
              "signature": "check(self, curve: ForwardCurve, storage_cost: float=0.0, *, eps: float=_ARBITRAGE_EPS) -> list[ArbitrageWarning]",
              "summary": "See :func:`check_arbitrage`."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curves/arbitrage.py",
          "line": 147
        },
        {
          "name": "ArbitrageWarning",
          "module": "curves",
          "qualified": "quantvolt.curves.arbitrage.ArbitrageWarning",
          "kind": "class",
          "signature": "ArbitrageWarning(periods: tuple[DeliveryPeriod, ...], message: str)",
          "summary": "A localised storage-arbitrage violation between identifiable curve nodes.",
          "doc": "A localised storage-arbitrage violation between identifiable curve nodes.\n\n``periods`` holds the offending consecutive pair ``(p_early, p_late)``; ``message``\ndescribes the negative time spread and the cost of carry it exceeds.",
          "methods": [],
          "fields": [
            {
              "name": "periods",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            },
            {
              "name": "message",
              "type": "str",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curves/arbitrage.py",
          "line": 59
        },
        {
          "name": "CurveBuilder",
          "module": "curves",
          "qualified": "quantvolt.curves.builder.CurveBuilder",
          "kind": "class",
          "signature": "CurveBuilder(extra_commodities: dict[str, CommodityConfig] | None=None)",
          "summary": "Config-holding class: merges BUILT_IN_COMMODITIES with caller extensions.",
          "doc": "Config-holding class: merges BUILT_IN_COMMODITIES with caller extensions.",
          "methods": [
            {
              "name": "build",
              "signature": "build(self, commodity: CommodityConfig, market_date: date, instruments: list[InstrumentPriceRecord], interpolation: Literal['piecewise_flat', 'piecewise_linear', 'cubic_spline']='piecewise_linear', tolerance: float=0.01, storage_cost: float=0.0) -> CurveBuildResult",
              "summary": "Build a gap-filled forward curve from observed instrument prices."
            },
            {
              "name": "from_dict",
              "signature": "from_dict(data: dict[str, Any]) -> ForwardCurve",
              "summary": ""
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curves/builder.py",
          "line": 56
        },
        {
          "name": "CurveBuildResult",
          "module": "curves",
          "qualified": "quantvolt.curves.builder.CurveBuildResult",
          "kind": "class",
          "signature": "CurveBuildResult(curve: ForwardCurve, arbitrage_warnings: list[ArbitrageWarning], reprice_residuals: dict[str, float])",
          "summary": "Outcome of a curve build: the curve, any arbitrage warnings, reprice residuals.",
          "doc": "Outcome of a curve build: the curve, any arbitrage warnings, reprice residuals.",
          "methods": [],
          "fields": [
            {
              "name": "curve",
              "type": "ForwardCurve",
              "default": null
            },
            {
              "name": "arbitrage_warnings",
              "type": "list[ArbitrageWarning]",
              "default": null
            },
            {
              "name": "reprice_residuals",
              "type": "dict[str, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curves/builder.py",
          "line": 38
        },
        {
          "name": "check_arbitrage",
          "module": "curves",
          "qualified": "quantvolt.curves.arbitrage.check_arbitrage",
          "kind": "function",
          "signature": "check_arbitrage(curve: ForwardCurve, storage_cost: float=0.0, *, eps: float=_ARBITRAGE_EPS) -> list[ArbitrageWarning]",
          "summary": "Return one :class:`ArbitrageWarning` per consecutive pair violating carry.",
          "doc": "Return one :class:`ArbitrageWarning` per consecutive pair violating carry.\n\nThe exact inequality flagged for a consecutive pair ``p_early < p_late`` is::\n\n    price(p_late) < price(p_early) - storage_cost * months_between - eps\n\ni.e. a negative time spread (far below near) steeper than the cost of carry\ncan explain. Returns an empty list when the curve is clean.\n\nArgs:\n    curve: The forward curve to check.\n    storage_cost: Cost of carry per unit per month, non-negative (default\n        0.0: any strict price inversion is flagged).\n    eps: Absolute numerical slack so a spread exactly at the carry bound\n        is treated as clean rather than a floating-point false positive,\n        positive (default ``1e-9``).\n\nRaises:\n    ValidationError: If ``storage_cost`` is negative (or non-finite), or\n        ``eps`` is not strictly positive.\n    ArbitrageError: if any node price is non-finite, so time spreads are\n        undefined and no violation can be attributed to identifiable nodes.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curves/arbitrage.py",
          "line": 70
        }
      ]
    },
    {
      "name": "pricing",
      "qualified": "quantvolt.pricing",
      "description": "Energy derivatives, spreads, options and settlement pricers.",
      "symbols": [
        {
          "name": "AsianOptionRequest",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.AsianOptionRequest",
          "kind": "class",
          "signature": "AsianOptionRequest(option_type: Literal['call', 'put'], averaging: Literal['arithmetic', 'geometric'], strike: float, forward: float, sigma: float, time_to_expiry: float, discount_factor: float, method: Literal['turnbull_wakeman', 'kemna_vorst', 'monte_carlo'] | None = None, seed: int | None = None, path_count: int = 10000)",
          "summary": "Inputs for an Asian option calculation.",
          "doc": "Inputs for an Asian option calculation. Select arithmetic or geometric averaging and the requested analytic or seeded Monte Carlo method; all price, volatility, expiry, discounting, averaging and notional assumptions are explicit fields.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "averaging",
              "type": "Literal['arithmetic', 'geometric']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "method",
              "type": "Literal['turnbull_wakeman', 'kemna_vorst', 'monte_carlo'] | None",
              "default": "None"
            },
            {
              "name": "seed",
              "type": "int | None",
              "default": "None"
            },
            {
              "name": "path_count",
              "type": "int",
              "default": "10000"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 60
        },
        {
          "name": "BarrierOptionRequest",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.BarrierOptionRequest",
          "kind": "class",
          "signature": "BarrierOptionRequest(option_type: Literal['call', 'put'], barrier_type: Literal['up_in', 'up_out', 'down_in', 'down_out'], strike: float, barrier: float, forward: float, sigma: float, time_to_expiry: float, discount_factor: float)",
          "summary": "Inputs for an analytic barrier option.",
          "doc": "Inputs for an analytic barrier option. The barrier direction and knock behavior are encoded by the option/barrier type together with spot/forward, strike, barrier, volatility, expiry and discounting assumptions.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "barrier_type",
              "type": "Literal['up_in', 'up_out', 'down_in', 'down_out']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "barrier",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 74
        },
        {
          "name": "BasisResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.BasisResult",
          "kind": "class",
          "signature": "BasisResult(per_period: dict[DeliveryPeriod, float], mean: float, std: float, p5: float, p95: float)",
          "summary": "Per-period locational basis (A - B) with summary statistics (Req 2.4).",
          "doc": "Per-period locational basis (A - B) with summary statistics (Req 2.4).\n\n``std`` is the standard deviation (population by default, ``ddof=0``);\n``p5``/``p95`` are the ``lower_percentile``/``upper_percentile`` (5th/95th by\ndefault) via :func:`numpy.percentile` (linear interpolation). See :func:`basis`.",
          "methods": [],
          "fields": [
            {
              "name": "per_period",
              "type": "dict[DeliveryPeriod, float]",
              "default": null
            },
            {
              "name": "mean",
              "type": "float",
              "default": null
            },
            {
              "name": "std",
              "type": "float",
              "default": null
            },
            {
              "name": "p5",
              "type": "float",
              "default": null
            },
            {
              "name": "p95",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 93
        },
        {
          "name": "CalendarSpreadResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.CalendarSpreadResult",
          "kind": "class",
          "signature": "CalendarSpreadResult(period_early: DeliveryPeriod, period_late: DeliveryPeriod, price_difference: float, storage_cost_total: float, spread: float)",
          "summary": "Storage-related calendar spread between two delivery periods (Property 44).",
          "doc": "Storage-related calendar spread between two delivery periods (Property 44).\n\n``price_difference`` is the raw later-minus-earlier price difference;\n``storage_cost_total`` is ``storage_cost`` (per month) times the number of\nmonths between the two periods; ``spread`` is the storage-adjusted value\n(``price_difference - storage_cost_total``). A positive ``spread`` indicates\ncontango net of carry (profitable storage injection); negative indicates\nbackwardation.",
          "methods": [],
          "fields": [
            {
              "name": "period_early",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "period_late",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "price_difference",
              "type": "float",
              "default": null
            },
            {
              "name": "storage_cost_total",
              "type": "float",
              "default": null
            },
            {
              "name": "spread",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 121
        },
        {
          "name": "CapFloorRequest",
          "module": "pricing",
          "qualified": "quantvolt.pricing.vanilla.CapFloorRequest",
          "kind": "class",
          "signature": "CapFloorRequest(option_type: Literal['cap', 'floor'], strike: float, notional: float, caplets: tuple[VanillaOptionRequest, ...])",
          "summary": "Inputs for a cap or floor strip over aligned forward, strike, volatility, expiry and discount-factor sequences..",
          "doc": "Inputs for a cap or floor strip over aligned forward, strike, volatility, expiry and discount-factor sequences.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['cap', 'floor']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "caplets",
              "type": "tuple[VanillaOptionRequest, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 45
        },
        {
          "name": "CapFloorResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.vanilla.CapFloorResult",
          "kind": "class",
          "signature": "CapFloorResult(premium: float, greeks: Greeks, per_period: tuple[VanillaOptionResult, ...])",
          "summary": "Aggregate cap/floor premium together with the individual caplet or floorlet contributions used to reconcile it..",
          "doc": "Aggregate cap/floor premium together with the individual caplet or floorlet contributions used to reconcile it.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "greeks",
              "type": "Greeks",
              "default": null
            },
            {
              "name": "per_period",
              "type": "tuple[VanillaOptionResult, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 53
        },
        {
          "name": "CleanSpreadResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.CleanSpreadResult",
          "kind": "class",
          "signature": "CleanSpreadResult(spread_type: SpreadType, per_period: dict[DeliveryPeriod, float], carbon_cost: dict[DeliveryPeriod, float])",
          "summary": "A carbon-cleaned spread: base ``spread_type``, cleaned values, carbon cost.",
          "doc": "A carbon-cleaned spread: base ``spread_type``, cleaned values, carbon cost.\n\n``per_period`` holds the cleaned spread (uncleaned - carbon cost) and\n``carbon_cost`` the deducted ``emissions_intensity * EUA_price`` per period,\nso callers can reconstruct the uncleaned spread (Property 7).",
          "methods": [],
          "fields": [
            {
              "name": "spread_type",
              "type": "SpreadType",
              "default": null
            },
            {
              "name": "per_period",
              "type": "dict[DeliveryPeriod, float]",
              "default": null
            },
            {
              "name": "carbon_cost",
              "type": "dict[DeliveryPeriod, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 66
        },
        {
          "name": "CrackSpreadResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.CrackSpreadResult",
          "kind": "class",
          "signature": "CrackSpreadResult(per_period: dict[DeliveryPeriod, float], ratio: tuple[int, ...])",
          "summary": "Refining margin per delivery period, normalised per unit of crude.",
          "doc": "Refining margin per delivery period, normalised per unit of crude.\n\n``ratio`` echoes the crack convention used, e.g. ``(3, 2, 1)`` — crude units\nfirst, then one output entry per product curve in insertion order.",
          "methods": [],
          "fields": [
            {
              "name": "per_period",
              "type": "dict[DeliveryPeriod, float]",
              "default": null
            },
            {
              "name": "ratio",
              "type": "tuple[int, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 109
        },
        {
          "name": "ExoticOptionResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.ExoticOptionResult",
          "kind": "class",
          "signature": "ExoticOptionResult(premium: float, greeks: Greeks, standard_error: float | None = None)",
          "summary": "Typed exotic-option output containing premium, method attribution and optional Monte Carlo standard error..",
          "doc": "Typed exotic-option output containing premium, method attribution and optional Monte Carlo standard error.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "greeks",
              "type": "Greeks",
              "default": null
            },
            {
              "name": "standard_error",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 97
        },
        {
          "name": "FuturesPricingResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.futures.FuturesPricingResult",
          "kind": "class",
          "signature": "FuturesPricingResult(npv: float, delta: float)",
          "summary": "NPV and forward-price delta of a futures/forward contract.",
          "doc": "NPV and forward-price delta of a futures/forward contract.",
          "methods": [],
          "fields": [
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "delta",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/futures.py",
          "line": 27
        },
        {
          "name": "ImpliedHeatRateResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.ImpliedHeatRateResult",
          "kind": "class",
          "signature": "ImpliedHeatRateResult(per_period: dict[DeliveryPeriod, float], anomalous: tuple[DeliveryPeriod, ...])",
          "summary": "Implied heat rate (power/gas) per shared period plus anomaly flags.",
          "doc": "Implied heat rate (power/gas) per shared period plus anomaly flags.\n\n``anomalous`` lists, in chronological order, the periods whose implied heat\nrate falls strictly outside the caller-supplied ``anomaly_range``; it is empty\nwhen no range was supplied (Req 2.3).",
          "methods": [],
          "fields": [
            {
              "name": "per_period",
              "type": "dict[DeliveryPeriod, float]",
              "default": null
            },
            {
              "name": "anomalous",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 80
        },
        {
          "name": "ImpliedVolResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.implied_vol.ImpliedVolResult",
          "kind": "class",
          "signature": "ImpliedVolResult(implied_vol: float, moneyness: Moneyness, iteration_count: int, converged: bool)",
          "summary": "Outcome of a premium inversion (design \"Implied Volatility Calculator\").",
          "doc": "Outcome of a premium inversion (design \"Implied Volatility Calculator\").\n\n``iteration_count`` is the number of objective (Black-76 repricing) evaluations\nBrent performed, including the two bracket-endpoint evaluations — the closest\nobservable proxy for the solver's iteration count. This matches\n:func:`scipy.optimize.brentq`'s own evaluation count exactly (verified by\n``test_implied_vol.py::test_iteration_count_matches_scipy_brentq_call_count_exactly``):\n:func:`~quantvolt.numerics.rootfind.brent_root` no longer pre-evaluates the\nendpoints itself before delegating to ``brentq`` (which evaluates them again\ninternally), a redundant pre-check that previously double-counted them and\ninflated this value by exactly 2. ``converged`` is ``True`` whenever a result is\nreturned; non-convergence raises instead of returning a partial result (fail\nloudly, ``coding-style.md`` §7).",
          "methods": [],
          "fields": [
            {
              "name": "implied_vol",
              "type": "float",
              "default": null
            },
            {
              "name": "moneyness",
              "type": "Moneyness",
              "default": null
            },
            {
              "name": "iteration_count",
              "type": "int",
              "default": null
            },
            {
              "name": "converged",
              "type": "bool",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 61
        },
        {
          "name": "LookbackOptionRequest",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.LookbackOptionRequest",
          "kind": "class",
          "signature": "LookbackOptionRequest(option_type: Literal['call', 'put'], strike_type: Literal['floating', 'fixed'], forward: float, sigma: float, time_to_expiry: float, discount_factor: float, strike: float | None = None)",
          "summary": "Inputs for a fixed- or floating-strike lookback option, including observed extrema, volatility, expiry, discounting and notional..",
          "doc": "Inputs for a fixed- or floating-strike lookback option, including observed extrema, volatility, expiry, discounting and notional.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "strike_type",
              "type": "Literal['floating', 'fixed']",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "strike",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 86
        },
        {
          "name": "MissingImbalancePricePolicy",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.MissingImbalancePricePolicy",
          "kind": "class",
          "signature": "MissingImbalancePricePolicy()",
          "summary": "How batch settlement handles absent physical imbalance-price columns.",
          "doc": "How batch settlement handles absent physical imbalance-price columns.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "ERROR",
              "value": "'error'"
            },
            {
              "name": "USE_SPOT",
              "value": "'use_spot'"
            }
          ],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 82
        },
        {
          "name": "MtMPosition",
          "module": "pricing",
          "qualified": "quantvolt.pricing.mark_to_market.MtMPosition",
          "kind": "class",
          "signature": "MtMPosition(commodity_id: str, delivery_period: DeliveryPeriod, notional: float, trade_price: float, prior_mark_price: float)",
          "summary": "An open position to be marked to market (Req 10.1).",
          "doc": "An open position to be marked to market (Req 10.1).\n\n``prior_mark_price`` is the mark from the previous valuation date and\n``trade_price`` the original contract price. Both may be negative — negative\nenergy prices are real in European markets — but ``notional`` must be\nstrictly positive (validated eagerly at construction).",
          "methods": [],
          "fields": [
            {
              "name": "commodity_id",
              "type": "str",
              "default": null
            },
            {
              "name": "delivery_period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "trade_price",
              "type": "float",
              "default": null
            },
            {
              "name": "prior_mark_price",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 24
        },
        {
          "name": "MtMPositionResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.mark_to_market.MtMPositionResult",
          "kind": "class",
          "signature": "MtMPositionResult(daily_pnl: float, cumulative_pnl: float, current_mark: float, status: Literal['settled', 'estimated'])",
          "summary": "Per-position mark, P&L pair, and how the mark was sourced (Req 10.1, 10.2).",
          "doc": "Per-position mark, P&L pair, and how the mark was sourced (Req 10.1, 10.2).",
          "methods": [],
          "fields": [
            {
              "name": "daily_pnl",
              "type": "float",
              "default": null
            },
            {
              "name": "cumulative_pnl",
              "type": "float",
              "default": null
            },
            {
              "name": "current_mark",
              "type": "float",
              "default": null
            },
            {
              "name": "status",
              "type": "Literal['settled', 'estimated']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 44
        },
        {
          "name": "MtMResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.mark_to_market.MtMResult",
          "kind": "class",
          "signature": "MtMResult(positions: tuple[MtMPositionResult, ...], estimated_count: int)",
          "summary": "Per-position results in input order plus the count of estimated marks.",
          "doc": "Per-position results in input order plus the count of estimated marks.",
          "methods": [],
          "fields": [
            {
              "name": "positions",
              "type": "tuple[MtMPositionResult, ...]",
              "default": null
            },
            {
              "name": "estimated_count",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 54
        },
        {
          "name": "OptionQuote",
          "module": "pricing",
          "qualified": "quantvolt.pricing.implied_vol.OptionQuote",
          "kind": "class",
          "signature": "OptionQuote(period: DeliveryPeriod, strike: float, premium: float, forward: float, option_type: Literal['call', 'put'], time_to_expiry: float, discount_factor: float)",
          "summary": "One observed option quote used to build a volatility surface (design \"Volatility Surface Builder\"). A plain immutable carrier: every field is validated at the :func:`implied_vol` boundary when the quote is inverted.",
          "doc": "One observed option quote used to build a volatility surface (design\n\"Volatility Surface Builder\"). A plain immutable carrier: every field is\nvalidated at the :func:`implied_vol` boundary when the quote is inverted.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "option_type",
              "type": "Literal['call', 'put']",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 282
        },
        {
          "name": "PowerHedgeDataColumns",
          "module": "pricing",
          "qualified": "quantvolt.pricing.power_hedge.PowerHedgeDataColumns",
          "kind": "class",
          "signature": "PowerHedgeDataColumns(interval_start_utc: str = 'interval_start_utc', interval_end_utc: str = 'interval_end_utc', spot_price_per_mwh: str = 'spot_price_per_mwh')",
          "summary": "Map caller-owned frame columns to realized hedge inputs.",
          "doc": "Map caller-owned frame columns to realized hedge inputs.",
          "methods": [],
          "fields": [
            {
              "name": "interval_start_utc",
              "type": "str",
              "default": "'interval_start_utc'"
            },
            {
              "name": "interval_end_utc",
              "type": "str",
              "default": "'interval_end_utc'"
            },
            {
              "name": "spot_price_per_mwh",
              "type": "str",
              "default": "'spot_price_per_mwh'"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 30
        },
        {
          "name": "PowerHedgeSettlement",
          "module": "pricing",
          "qualified": "quantvolt.pricing.power_hedge.PowerHedgeSettlement",
          "kind": "class",
          "signature": "PowerHedgeSettlement(hedge_id: str, interval: PowerDeliveryInterval, spot_price_per_mwh: float, volume_mwh: float, gross_payoff: float, premium_cashflow: float, net_cashflow: float)",
          "summary": "Auditable realized cash flow for one hedge and delivery interval.",
          "doc": "Auditable realized cash flow for one hedge and delivery interval.",
          "methods": [],
          "fields": [
            {
              "name": "hedge_id",
              "type": "str",
              "default": null
            },
            {
              "name": "interval",
              "type": "PowerDeliveryInterval",
              "default": null
            },
            {
              "name": "spot_price_per_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "volume_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "gross_payoff",
              "type": "float",
              "default": null
            },
            {
              "name": "premium_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "net_cashflow",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 17
        },
        {
          "name": "PpaDataColumns",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.PpaDataColumns",
          "kind": "class",
          "signature": "PpaDataColumns(interval_start_utc: str = 'interval_start_utc', interval_end_utc: str = 'interval_end_utc', contracted_mwh: str = 'contracted_mwh', metered_generation_mwh: str = 'metered_generation_mwh', spot_price_per_mwh: str = 'spot_price_per_mwh', shortfall_price_per_mwh: str = 'shortfall_price_per_mwh', excess_price_per_mwh: str = 'excess_price_per_mwh', hedge_cashflow: str = 'hedge_cashflow', option_payoff: str = 'option_payoff', option_premium: str = 'option_premium', variable_cost: str = 'variable_cost', transaction_cost: str = 'transaction_cost')",
          "summary": "Map caller-owned column names onto QuantVolt's PPA settlement inputs.",
          "doc": "Map caller-owned column names onto QuantVolt's PPA settlement inputs.",
          "methods": [],
          "fields": [
            {
              "name": "interval_start_utc",
              "type": "str",
              "default": "'interval_start_utc'"
            },
            {
              "name": "interval_end_utc",
              "type": "str",
              "default": "'interval_end_utc'"
            },
            {
              "name": "contracted_mwh",
              "type": "str",
              "default": "'contracted_mwh'"
            },
            {
              "name": "metered_generation_mwh",
              "type": "str",
              "default": "'metered_generation_mwh'"
            },
            {
              "name": "spot_price_per_mwh",
              "type": "str",
              "default": "'spot_price_per_mwh'"
            },
            {
              "name": "shortfall_price_per_mwh",
              "type": "str",
              "default": "'shortfall_price_per_mwh'"
            },
            {
              "name": "excess_price_per_mwh",
              "type": "str",
              "default": "'excess_price_per_mwh'"
            },
            {
              "name": "hedge_cashflow",
              "type": "str",
              "default": "'hedge_cashflow'"
            },
            {
              "name": "option_payoff",
              "type": "str",
              "default": "'option_payoff'"
            },
            {
              "name": "option_premium",
              "type": "str",
              "default": "'option_premium'"
            },
            {
              "name": "variable_cost",
              "type": "str",
              "default": "'variable_cost'"
            },
            {
              "name": "transaction_cost",
              "type": "str",
              "default": "'transaction_cost'"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 90
        },
        {
          "name": "PpaIntervalSettlement",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.PpaIntervalSettlement",
          "kind": "class",
          "signature": "PpaIntervalSettlement(interval: PowerDeliveryInterval, contracted_mwh: float, metered_generation_mwh: float, own_generation_delivered_mwh: float, shortfall_mwh: float, excess_mwh: float, ppa_cashflow: float, spot_cashflow: float, imbalance_cashflow: float, hedge_cashflow: float, option_payoff: float, option_premium: float, variable_cost: float, transaction_cost: float, net_cashflow: float)",
          "summary": "An auditable producer cash-flow ledger for one delivery interval.",
          "doc": "An auditable producer cash-flow ledger for one delivery interval.",
          "methods": [
            {
              "name": "component_sum",
              "signature": "component_sum(self) -> float",
              "summary": "Reconstruct net cash flow from its signed ledger components."
            }
          ],
          "fields": [
            {
              "name": "interval",
              "type": "PowerDeliveryInterval",
              "default": null
            },
            {
              "name": "contracted_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "metered_generation_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "own_generation_delivered_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "shortfall_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "excess_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "ppa_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "spot_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "imbalance_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "hedge_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "option_payoff",
              "type": "float",
              "default": null
            },
            {
              "name": "option_premium",
              "type": "float",
              "default": null
            },
            {
              "name": "variable_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "transaction_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "net_cashflow",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 48
        },
        {
          "name": "SpreadOptionRequest",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spread_option.SpreadOptionRequest",
          "kind": "class",
          "signature": "SpreadOptionRequest(forward1: float, forward2: float, strike: float, sigma1: float, sigma2: float, correlation: float, time_to_expiry: float, discount_factor: float, notional: float = 1.0)",
          "summary": "Inputs for a call on ``forward1 - forward2 - strike`` (Req 7.1).",
          "doc": "Inputs for a call on ``forward1 - forward2 - strike`` (Req 7.1).",
          "methods": [],
          "fields": [
            {
              "name": "forward1",
              "type": "float",
              "default": null
            },
            {
              "name": "forward2",
              "type": "float",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma1",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma2",
              "type": "float",
              "default": null
            },
            {
              "name": "correlation",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": "1.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 47
        },
        {
          "name": "SpreadOptionResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spread_option.SpreadOptionResult",
          "kind": "class",
          "signature": "SpreadOptionResult(premium: float, delta1: float, delta2: float, vega1: float, vega2: float, correlation_sensitivity: float)",
          "summary": "Premium plus finite-difference sensitivities, all scaled by notional (Req 7.2).",
          "doc": "Premium plus finite-difference sensitivities, all scaled by notional (Req 7.2).\n\n``delta1``/``delta2`` are sensitivities to ``forward1``/``forward2`` exactly as\npassed to :func:`price_spread_option`. :func:`price_spark_spread_option` is the\none exception: it chain-rules ``delta2`` back onto the RAW gas forward it was\ngiven (``request.forward2``, before the internal ``heat_rate`` scaling), so that\n``delta2`` always means \"sensitivity to the underlying commodity forward the\ncaller supplied\" — the same convention :mod:`quantvolt.pricing.tolling` uses when\nit chain-rules a spread option's ``delta2`` onto the raw fuel/EUA forwards.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "delta1",
              "type": "float",
              "default": null
            },
            {
              "name": "delta2",
              "type": "float",
              "default": null
            },
            {
              "name": "vega1",
              "type": "float",
              "default": null
            },
            {
              "name": "vega2",
              "type": "float",
              "default": null
            },
            {
              "name": "correlation_sensitivity",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 62
        },
        {
          "name": "SpreadResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.SpreadResult",
          "kind": "class",
          "signature": "SpreadResult(spread_type: SpreadType, per_period: dict[DeliveryPeriod, float])",
          "summary": "A generation-margin spread per delivery period, labelled by its type.",
          "doc": "A generation-margin spread per delivery period, labelled by its type.\n\n``spread_type`` records whether the values are spark (gas-fired) or dark\n(coal-fired) margins; the label is what lets :func:`clean_spread` name its\noutput and what keeps spark and dark results distinct objects (Property 6).\n``per_period`` preserves chronological key order.",
          "methods": [],
          "fields": [
            {
              "name": "spread_type",
              "type": "SpreadType",
              "default": null
            },
            {
              "name": "per_period",
              "type": "dict[DeliveryPeriod, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 52
        },
        {
          "name": "SwapPricingResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.swap.SwapPricingResult",
          "kind": "class",
          "signature": "SwapPricingResult(npv: float, delta: tuple[float, ...], rho: float)",
          "summary": "Swap valuation output containing total NPV, one forward delta per schedule period and rho for the documented parallel rate bump..",
          "doc": "Swap valuation output containing total NPV, one forward delta per schedule period and rho for the documented parallel rate bump.",
          "methods": [],
          "fields": [
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "delta",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "rho",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/swap.py",
          "line": 48
        },
        {
          "name": "TollingResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.tolling.TollingResult",
          "kind": "class",
          "signature": "TollingResult(npv: float, intrinsic_value: float, time_value: float, per_period_values: tuple[float, ...], per_period_deltas: dict[str, tuple[float, ...]], aggregate_deltas: dict[str, float])",
          "summary": "Strip-level tolling valuation: NPV decomposition plus per-period detail.",
          "doc": "Strip-level tolling valuation: NPV decomposition plus per-period detail.\n\n``per_period_values`` are the discounted per-period spread-option values in\nschedule order; ``npv`` is their sum. ``per_period_deltas`` and\n``aggregate_deltas`` are keyed ``\"power\"``/``\"fuel\"``/``\"eua\"``, and each\naggregate equals the sum of its per-period tuple exactly (Property 20).",
          "methods": [],
          "fields": [
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "intrinsic_value",
              "type": "float",
              "default": null
            },
            {
              "name": "time_value",
              "type": "float",
              "default": null
            },
            {
              "name": "per_period_values",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "per_period_deltas",
              "type": "dict[str, tuple[float, ...]]",
              "default": null
            },
            {
              "name": "aggregate_deltas",
              "type": "dict[str, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/tolling.py",
          "line": 90
        },
        {
          "name": "TransportPeriodValue",
          "module": "pricing",
          "qualified": "quantvolt.pricing.transmission_right.TransportPeriodValue",
          "kind": "class",
          "signature": "TransportPeriodValue(period: DeliveryPeriod, payoff: float, discount_factor: float, intrinsic: float, extrinsic: float, value: float, direction: TransportDirection | None, delta_origin: float, delta_destination: float)",
          "summary": "One shared delivery period's transport-right valuation.",
          "doc": "One shared delivery period's transport-right valuation.\n\n``payoff`` is the undiscounted per-period intrinsic payoff\n``Q_delivered · max(P_sink - P_source - tariff, 0)`` (Property 67 form);\n``intrinsic`` is that payoff discounted at ``discount_factor``; ``extrinsic`` is\nthe option time value (0 without vols); ``value = intrinsic + extrinsic``.\n``direction`` is the committed flow (``None`` for no-flow). ``delta_origin`` and\n``delta_destination`` are ``∂value/∂P_A`` and ``∂value/∂P_B`` from the holder's\nperspective — always opposite in sign for an active flow.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "payoff",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            },
            {
              "name": "intrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "extrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "value",
              "type": "float",
              "default": null
            },
            {
              "name": "direction",
              "type": "TransportDirection | None",
              "default": null
            },
            {
              "name": "delta_origin",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_destination",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/transmission_right.py",
          "line": 64
        },
        {
          "name": "TransportRightResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.transmission_right.TransportRightResult",
          "kind": "class",
          "signature": "TransportRightResult(origin: str, destination: str, intrinsic: float, extrinsic: float, total: float, delta_origin: float, delta_destination: float, per_period: tuple[TransportPeriodValue, ...])",
          "summary": "Aggregate transport-right value plus per-period detail (Req 24.1-24.3).",
          "doc": "Aggregate transport-right value plus per-period detail (Req 24.1-24.3).\n\n``intrinsic``/``extrinsic``/``total`` are the sums over ``per_period`` with\n``total == intrinsic + extrinsic``. ``delta_origin``/``delta_destination`` are the\naggregate per-hub deltas (opposite-signed nets), keyed for the portfolio adapter\nby ``origin``/``destination`` commodity ids.",
          "methods": [],
          "fields": [
            {
              "name": "origin",
              "type": "str",
              "default": null
            },
            {
              "name": "destination",
              "type": "str",
              "default": null
            },
            {
              "name": "intrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "extrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "total",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_origin",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_destination",
              "type": "float",
              "default": null
            },
            {
              "name": "per_period",
              "type": "tuple[TransportPeriodValue, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/transmission_right.py",
          "line": 88
        },
        {
          "name": "VanillaOptionRequest",
          "module": "pricing",
          "qualified": "quantvolt.pricing.vanilla.VanillaOptionRequest",
          "kind": "class",
          "signature": "VanillaOptionRequest(option_type: Literal['call', 'put', 'cap', 'floor'], strike: float, notional: float, forward: float, sigma: float, time_to_expiry: float, discount_factor: float)",
          "summary": "Complete Black–76 call or put inputs: type, strike, notional, forward, volatility, time to expiry and discount factor..",
          "doc": "Complete Black–76 call or put inputs: type, strike, notional, forward, volatility, time to expiry and discount factor.",
          "methods": [],
          "fields": [
            {
              "name": "option_type",
              "type": "Literal['call', 'put', 'cap', 'floor']",
              "default": null
            },
            {
              "name": "strike",
              "type": "float",
              "default": null
            },
            {
              "name": "notional",
              "type": "float",
              "default": null
            },
            {
              "name": "forward",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "time_to_expiry",
              "type": "float",
              "default": null
            },
            {
              "name": "discount_factor",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 28
        },
        {
          "name": "VanillaOptionResult",
          "module": "pricing",
          "qualified": "quantvolt.pricing.vanilla.VanillaOptionResult",
          "kind": "class",
          "signature": "VanillaOptionResult(premium: float, greeks: Greeks)",
          "summary": "Vanilla option output containing discounted premium and the complete analytical Greeks object..",
          "doc": "Vanilla option output containing discounted premium and the complete analytical Greeks object.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "greeks",
              "type": "Greeks",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 39
        },
        {
          "name": "basis",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.basis",
          "kind": "function",
          "signature": "basis(curve_a: ForwardCurve, curve_b: ForwardCurve, start: date, end: date, *, lower_percentile: float=5.0, upper_percentile: float=95.0, ddof: int=0) -> BasisResult",
          "summary": "Locational basis ``price(A) - price(B)`` per period in ``[start, end]`` (Req 2.4).",
          "doc": "Locational basis ``price(A) - price(B)`` per period in ``[start, end]`` (Req 2.4).\n\nThe computation covers the shared delivery periods whose last calendar day\nfalls within the inclusive ``[start, end]`` range; no such period raises\n:class:`InsufficientDataError` naming both commodities and the range rather\nthan returning empty statistics (Property 9). Summary statistics: mean,\nstandard deviation (``ddof=0`` by default — the periods are the whole\npopulation of interest, not a sample), and the ``lower_percentile``/\n``upper_percentile`` (default 5th/95th) via :func:`numpy.percentile`\n(linear interpolation).\n\nArgs:\n    curve_a: First curve of the basis (``A`` in ``A - B``).\n    curve_b: Second curve of the basis.\n    start: Inclusive lower bound on each period's last calendar day.\n    end: Inclusive upper bound; must be ``>= start``.\n    lower_percentile: Percentile reported as ``p5``, in ``[0, 100]``\n        (default 5.0) and strictly below ``upper_percentile``.\n    upper_percentile: Percentile reported as ``p95``, in ``[0, 100]``\n        (default 95.0).\n    ddof: Delta degrees of freedom for :func:`numpy.std`, non-negative\n        (default 0, population standard deviation).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 318
        },
        {
          "name": "build_volatility_surface",
          "module": "pricing",
          "qualified": "quantvolt.pricing.implied_vol.build_volatility_surface",
          "kind": "function",
          "signature": "build_volatility_surface(option_quotes: list[OptionQuote], interpolation: Literal['linear', 'cubic_spline']='linear', extrapolate: bool=False, *, commodity: CommodityConfig) -> VolatilitySurface",
          "summary": "Build an implied-volatility surface from option quotes (Task 36).",
          "doc": "Build an implied-volatility surface from option quotes (Task 36).\n\nEvery quote is inverted through :func:`implied_vol` (so every quote is fully\nvalidated — a bad quote fails loudly rather than being dropped). Because\n:class:`~quantvolt.models.vol_surface.VolatilitySurface` holds **one sigma per\nperiod tenor** (a term structure), multiple strikes quoted for the same period\nare aggregated to the *ATM-nearest* quote's vol: the quote whose strike is\nclosest to its forward (relative distance; first quote wins a tie). This\nanchors each tenor at the most liquid, smile-neutral point; the smile across\nstrikes is thereby collapsed by nearest-ATM selection.\n\nCalendar months missing between the first and last quoted period are filled by\ninterpolating the vol term structure on a monotone month axis with the selected\nmethod; quoted periods keep their exactly inverted vols. With\n``extrapolate=False`` the surface covers only ``[first, last]`` quoted period.\n\n``commodity`` is required and keyword-only: the stub signature carried no\ncommodity, but :class:`VolatilitySurface` requires one, and guessing a default\nwould silently mislabel the surface — an additive keyword parameter completes\nthe stub without breaking positional callers.\n\nArgs:\n    option_quotes: Non-empty list of :class:`OptionQuote` observations.\n    interpolation: ``\"linear\"`` (piecewise linear) or ``\"cubic_spline\"``\n        (natural cubic spline), selected via a dispatch dict.\n    extrapolate: Must be ``False``; extrapolation beyond the quoted period\n        range is not supported (there is no principled extension target).\n    commodity: The commodity the surface belongs to (keyword-only, required).\n\nReturns:\n    A :class:`VolatilitySurface` with one tenor per calendar month from the\n    first to the last quoted period, inclusive. Inputs are never mutated.\n\nRaises:\n    ValidationError: If ``option_quotes`` is empty, ``interpolation`` is\n        unknown, ``extrapolate`` is ``True``, or any quote fails the\n        :func:`implied_vol` domain / no-arbitrage checks.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 309
        },
        {
          "name": "calendar_spread",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.calendar_spread",
          "kind": "function",
          "signature": "calendar_spread(curve: ForwardCurve, period_early: DeliveryPeriod, period_late: DeliveryPeriod, storage_cost: float=0.0) -> CalendarSpreadResult",
          "summary": "Storage-related calendar spread on one curve (Task 34, Property 44).",
          "doc": "Storage-related calendar spread on one curve (Task 34, Property 44).\n\n``spread = price(period_late) - price(period_early) - storage_cost * months``\nwhere ``months`` is the whole-month distance between the two delivery periods\nand ``storage_cost`` is the cost of carry per month. This is the spread a\nstorage operator captures by injecting in ``period_early`` and withdrawing in\n``period_late``; positive means contango net of carry, negative means\nbackwardation.\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless\n``period_early < period_late`` and ``storage_cost >= 0``; a period absent from\nthe curve raises :class:`~quantvolt.exceptions.MissingTenorError` (via\n:meth:`ForwardCurve.price_at`).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 456
        },
        {
          "name": "classify_moneyness",
          "module": "pricing",
          "qualified": "quantvolt.pricing.implied_vol.classify_moneyness",
          "kind": "function",
          "signature": "classify_moneyness(strike: float, forward: float, tolerance_pct: float=2.0) -> Moneyness",
          "summary": "Classify option moneyness relative to the forward price (Property 32).",
          "doc": "Classify option moneyness relative to the forward price (Property 32).\n\nClassification is from the **call perspective**: a strike above the forward has\nno intrinsic value for a call (OTM); a strike below the forward is ITM. The put\nclassification is the mirror image, so callers holding puts should swap\nITM/OTM. Deviations of at most ``tolerance_pct`` percent of the forward — the\nboundary is *inclusive* — classify as ATM:\n\n- ``|strike - forward| / forward * 100 <= tolerance_pct`` -> ATM\n- ``strike > forward * (1 + tolerance_pct/100)`` -> OTM\n- ``strike < forward * (1 - tolerance_pct/100)`` -> ITM\n\nArgs:\n    strike: Option strike (``K``), positive.\n    forward: Forward price of the underlying (``F``), positive.\n    tolerance_pct: ATM band half-width as a percentage of the forward,\n        non-negative (default 2.0 = within 2% of the forward).\n\nReturns:\n    Exactly one of :class:`Moneyness` ``ATM`` / ``OTM`` / ``ITM``.\n\nRaises:\n    ValidationError: If ``strike`` or ``forward`` is not positive, or\n        ``tolerance_pct`` is negative.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 197
        },
        {
          "name": "clean_spread",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.clean_spread",
          "kind": "function",
          "signature": "clean_spread(spread: SpreadResult, eua_curve: ForwardCurve, emissions_intensity: float) -> CleanSpreadResult",
          "summary": "Deduct the carbon cost from an uncleaned spark or dark spread (Req 2.2).",
          "doc": "Deduct the carbon cost from an uncleaned spark or dark spread (Req 2.2).\n\nDecorator intent as a plain function: wraps one :class:`SpreadResult` and adds\nthe carbon cost, per period: ``cleaned = spread - emissions_intensity *\nEUA_price``. The result keeps the input's ``spread_type``, so cleaning a spark\nspread yields the clean spark spread and cleaning a dark spread the clean dark\nspread — call once per uncleaned spread to obtain both (Property 7).\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless\n``emissions_intensity >= 0``, and :class:`InsufficientDataError` when\n``eua_curve`` lacks any of the spread's delivery periods (Req 2.5) — no\npartial result is returned.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 247
        },
        {
          "name": "crack_spread",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.crack_spread",
          "kind": "function",
          "signature": "crack_spread(product_curves: dict[str, ForwardCurve], crude_curve: ForwardCurve, ratio: tuple[int, ...]=(3, 2, 1)) -> CrackSpreadResult",
          "summary": "Refining margin per delivery period for an ``input:outputs`` crack ratio.",
          "doc": "Refining margin per delivery period for an ``input:outputs`` crack ratio.\n\nConvention: ``ratio[0]`` is the number of crude (input) units and ``ratio[1:]``\nthe product (output) units, matched to ``product_curves`` in insertion order —\nthe default 3:2:1 means 3 crude → 2 of the first product + 1 of the second.\nPer period, over the shared delivery periods of *all* curves::\n\n    spread = (Σᵢ product_priceᵢ * ratio[1 + i] - crude_price * ratio[0]) / ratio[0]\n\ni.e. the margin normalised per unit of crude. For the standard 3:2:1 and 5:3:2\ncracks the output units sum to the input units, so the product weights sum to 1\n(Property 42).\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless ``product_curves``\nis non-empty, ``len(ratio) == len(product_curves) + 1`` and every ratio entry\nis > 0; raises :class:`InsufficientDataError` when no delivery period is common\nto the crude curve and every product curve.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 378
        },
        {
          "name": "cumulative_historical_vol",
          "module": "pricing",
          "qualified": "quantvolt.pricing.implied_vol.cumulative_historical_vol",
          "kind": "function",
          "signature": "cumulative_historical_vol(price_series: pl.Series, window: int=252, *, periods_per_year: int=_TRADING_DAYS_PER_YEAR) -> pl.Series",
          "summary": "Rolling annualised realised volatility of log returns (implied-vs-realised).",
          "doc": "Rolling annualised realised volatility of log returns (implied-vs-realised).\n\nComputes ``log(P_t / P_{t-1})`` via Polars, then\n``rolling_std(window) * sqrt(periods_per_year)``. The output has the same length\nas the input; the warm-up (the first ``window`` entries: one for the return\ndifferencing plus ``window - 1`` for the rolling window) is null.\n\nArgs:\n    price_series: Strictly positive price observations, length > ``window``.\n    window: Rolling window length in observations, at least 2 (default 252,\n        one trading year).\n    periods_per_year: Annualisation factor under the square-root-of-time rule,\n        at least 1 (default 252, trading days per year).\n\nReturns:\n    A ``pl.Series`` of annualised realised vols with leading nulls for the\n    warm-up. The input series is never mutated.\n\nRaises:\n    ValidationError: If ``window < 2``, ``periods_per_year < 1``, or any price\n        is not strictly positive.\n    InsufficientDataError: If ``price_series`` has fewer than ``window + 1``\n        observations (no full rolling window of returns exists).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 234
        },
        {
          "name": "dark_spread",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.dark_spread",
          "kind": "function",
          "signature": "dark_spread(power_curve: ForwardCurve, fuel_curve: ForwardCurve, heat_rate: float, variable_cost: float, emissions_cost: float) -> SpreadResult",
          "summary": "Dark spread (coal-fired generation margin) per shared delivery period.",
          "doc": "Dark spread (coal-fired generation margin) per shared delivery period.\n\nSame formula and validation as :func:`spark_spread` with a coal ``fuel_curve``;\nthe result is labelled ``\"dark\"``. It is a separate immutable object, so\ncomputing it never modifies any spark values (Req 2.1, Property 6).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 229
        },
        {
          "name": "forward_spread",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.forward_spread",
          "kind": "function",
          "signature": "forward_spread(power_curve: ForwardCurve, fuel_curve: ForwardCurve, heat_rate: float, variable_cost: float, emissions_cost: float) -> SpreadResult",
          "summary": "Forward spark spread over the curve intersection, for forward price risk.",
          "doc": "Forward spark spread over the curve intersection, for forward price risk.\n\nThe formula is identical to :func:`spark_spread` — forward power minus\nheat-rate-weighted forward fuel minus costs — differing only in time-horizon\ninterpretation, so this delegates to it and returns the same ``\"spark\"``\n-labelled :class:`SpreadResult` (design §2.4, Property 43).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 439
        },
        {
          "name": "futures_delta",
          "module": "pricing",
          "qualified": "quantvolt.pricing.futures.futures_delta",
          "kind": "function",
          "signature": "futures_delta(contract: FuturesContract | ForwardContract, forward_curve: ForwardCurve, valuation_date: date, discount_curve: DiscountCurve, bump: float=1.0, *, settlement_lag_days: int=0) -> float",
          "summary": "Delta of the contract NPV to the forward price: ``discount_factor * notional``.",
          "doc": "Delta of the contract NPV to the forward price: ``discount_factor * notional``.\n\nThe NPV is linear in the forward price, so this closed form is exact — it is\nwhat a central finite difference at ``forward_price ± bump`` would compute for\nany ``bump > 0`` (up to floating-point round-off), without repricing twice or\nlooking up the forward price at all.\n\nArgs:\n    contract: The futures or forward contract to price.\n    forward_curve: Must have a node for ``contract.delivery_period``.\n    valuation_date: The date NPV is computed as of.\n    discount_curve: Must cover the settlement date.\n    bump: Retained for signature compatibility with the historical\n        finite-difference form and still validated as strictly positive;\n        unused in the closed-form computation itself.\n    settlement_lag_days: Calendar days added to the delivery period's last\n        day to get the settlement date, matching :func:`price_futures` so\n        price and delta agree (default 0, non-negative).\n\nRaises:\n    ValidationError: If ``bump`` is not strictly positive, or\n        ``settlement_lag_days`` is negative.\n    ExpiredContractError: If the delivery period ended strictly before\n        ``valuation_date`` (Req 3.3).\n    MissingTenorError: If ``forward_curve`` has no node for the delivery period\n        or ``discount_curve`` does not cover the settlement date (Req 3.4).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/futures.py",
          "line": 110
        },
        {
          "name": "implied_heat_rate",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.implied_heat_rate",
          "kind": "function",
          "signature": "implied_heat_rate(power_curve: ForwardCurve, gas_curve: ForwardCurve, anomaly_range: tuple[float, float] | None=None) -> ImpliedHeatRateResult",
          "summary": "Implied heat rate ``power_price / gas_price`` per shared period (Req 2.3).",
          "doc": "Implied heat rate ``power_price / gas_price`` per shared period (Req 2.3).\n\nValidation is eager and complete before any computation: every shared period's\ngas price must be strictly positive; the first violation raises\n:class:`~quantvolt.exceptions.ValidationError` identifying that delivery period\nand no heat rate is computed (Property 8). When ``anomaly_range=(lo, hi)`` is\nsupplied (requiring ``lo < hi``), periods whose implied heat rate falls\n*strictly outside* the inclusive ``[lo, hi]`` band are flagged in\n``anomalous``; without a range no period is flagged.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 281
        },
        {
          "name": "implied_vol",
          "module": "pricing",
          "qualified": "quantvolt.pricing.implied_vol.implied_vol",
          "kind": "function",
          "signature": "implied_vol(option_type: Literal['call', 'put'], market_premium: float, forward: float, strike: float, time_to_expiry: float, discount_factor: float, tol: float=0.0001, max_iter: int=100, *, sigma_lower: float=_SIGMA_LOWER, sigma_upper: float=_SIGMA_UPPER, tolerance_pct: float=2.0) -> ImpliedVolResult",
          "summary": "Recover the Black-76 volatility implied by a market premium (Property 31).",
          "doc": "Recover the Black-76 volatility implied by a market premium (Property 31).\n\nRound-trip contract (Property 31): ``implied_vol`` applied to\n``black76_price(sigma0, ...)`` recovers ``sigma0`` within ``tol``. Inversion uses\nBrent over ``[sigma_lower, sigma_upper]`` (default ``[1e-9, 10.0]``) — a bracketing\nsolver, so it cannot diverge near zero vega the way Newton-Raphson would (design\n§2.7). The inversion is performed locally with :func:`brent_root` and a\ncall-counting objective (instead of delegating to\n:func:`~quantvolt.numerics.black76.black76_implied_vol`) so that\n:attr:`ImpliedVolResult.iteration_count` can be reported — the kernel does not\nexpose its iteration count. Both use the same bracket, objective, and tolerance.\n\nNo-arbitrage precondition (Req 5.3), checked before inversion:\n\n- call: ``DF*max(F-K, 0) < market_premium < DF*F``\n- put:  ``DF*max(K-F, 0) < market_premium < DF*K``\n\nArgs:\n    option_type: ``\"call\"`` or ``\"put\"``.\n    market_premium: Observed (discounted) option premium to invert, positive.\n    forward: Forward price of the underlying (``F``), positive.\n    strike: Option strike (``K``), positive.\n    time_to_expiry: Time to expiry in years (``T``), positive.\n    discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.\n    tol: Absolute tolerance on the recovered volatility, positive.\n    max_iter: Maximum Brent iterations, at least 1.\n    sigma_lower: Lower end of the Brent search bracket, positive and strictly\n        below ``sigma_upper`` (default ``1e-9``, matching the kernel's bracket).\n    sigma_upper: Upper end of the Brent search bracket, strictly above\n        ``sigma_lower`` (default ``10.0``).\n    tolerance_pct: ATM band half-width (percent of the forward) passed through to\n        :func:`classify_moneyness` for the reported moneyness (default 2.0).\n\nReturns:\n    An :class:`ImpliedVolResult` with the recovered vol, the moneyness of the\n    quote (at ``tolerance_pct``, default 2% ATM tolerance), the\n    objective-evaluation count, and ``converged=True``.\n\nRaises:\n    ValidationError: If any input violates its domain, or if ``market_premium``\n        lies outside the no-arbitrage bounds (no volatility can reproduce it).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/implied_vol.py",
          "line": 83
        },
        {
          "name": "mark_to_market",
          "module": "pricing",
          "qualified": "quantvolt.pricing.mark_to_market.mark_to_market",
          "kind": "function",
          "signature": "mark_to_market(positions: list[MtMPosition], market_date: date, settlement_prices: dict[tuple[str, DeliveryPeriod], float], forward_curve: ForwardCurve | None=None) -> MtMResult",
          "summary": "Mark each position to market and compute daily and cumulative P&L (Req 10).",
          "doc": "Mark each position to market and compute daily and cumulative P&L (Req 10).\n\n``market_date`` documents the as-of date of the marks: ``settlement_prices``\n(and ``forward_curve``, if given) are the caller's pricing data for that date.\nAll marks come solely from these inputs — the function reads no clock and keeps\nno state — so identical inputs always produce an identical result (Req 10.5).\n\nEach position's ``current_mark`` is resolved by ordered fallback: the\nsettlement price for ``(commodity_id, delivery_period)``; else the node of a\nsame-commodity ``forward_curve``, flagged ``\"estimated\"``; else\n:class:`NoPricingDataError`. P&L is then computed identically for settled and\nestimated marks (Req 10.1):\n\n- ``daily_pnl = (current_mark - prior_mark_price) * notional``\n- ``cumulative_pnl = (current_mark - trade_price) * notional``\n\nResults are returned in input order; ``estimated_count`` is the number of\npositions whose status is ``\"estimated\"``. An empty book yields an empty\nresult. Inputs are never mutated.\n\nRaises:\n    NoPricingDataError: If neither a settlement price nor a same-commodity\n        forward-curve node is available for a position's ``(commodity_id,\n        delivery_period)`` (Req 10.3).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/mark_to_market.py",
          "line": 90
        },
        {
          "name": "power_cap_payoff",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.power_cap_payoff",
          "kind": "function",
          "signature": "power_cap_payoff(spot_price: float, strike: float, volume_mwh: float) -> float",
          "summary": "Realised long-cap payoff ``max(spot - strike, 0) * volume``.",
          "doc": "Realised long-cap payoff ``max(spot - strike, 0) * volume``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 31
        },
        {
          "name": "power_floor_payoff",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.power_floor_payoff",
          "kind": "function",
          "signature": "power_floor_payoff(spot_price: float, strike: float, volume_mwh: float) -> float",
          "summary": "Realised long-floor payoff ``max(strike - spot, 0) * volume``.",
          "doc": "Realised long-floor payoff ``max(strike - spot, 0) * volume``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 39
        },
        {
          "name": "price_asian",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.price_asian",
          "kind": "function",
          "signature": "price_asian(request: AsianOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, time_bump: float=_TIME_BUMP, averaging_points: int=_MC_AVERAGING_POINTS) -> ExoticOptionResult",
          "summary": "Price an average-price Asian option on a forward (Req 6.1).",
          "doc": "Price an average-price Asian option on a forward (Req 6.1).\n\nMethod dispatch (Simple Factory): ``request.method`` if given, otherwise the\naveraging-type default — Turnbull-Wakeman for ``\"arithmetic\"``, Kemna-Vorst for\n``\"geometric\"``. Each closed form prices exactly one averaging type, so an explicit\nmethod that contradicts ``request.averaging`` is rejected rather than silently\nrepriced (fail loudly, coding-style.md §7). ``\"monte_carlo\"`` must be requested\nexplicitly and additionally requires ``seed`` and ``path_count >= 1000``.\n\nClosed forms return central finite-difference Greeks of the selected kernel; the\nMonte Carlo path returns ``Greeks.zero()`` (MC Greeks arrive with the Rust engine,\nTask 59) plus the kernel's ``standard_error``.\n\nArgs:\n    request: Fully specified Asian option; validated eagerly before any\n        computation (Req 6.4).\n    forward_bump_fraction: Relative forward bump used for the closed-form\n        delta/gamma finite differences, positive (default ``1e-4``). Unused\n        for ``method=\"monte_carlo\"``.\n    vol_bump: Absolute vol bump for the closed-form vega finite difference,\n        positive (default ``1e-4``). Unused for ``method=\"monte_carlo\"``.\n    time_bump: Absolute time bump for the closed-form theta finite\n        difference, positive (default ``1e-6``). Unused for\n        ``method=\"monte_carlo\"``.\n    averaging_points: Number of discrete fixings in the Monte Carlo averaging\n        schedule, at least 1 (default 252, one trading year of daily\n        fixings). Unused for the closed forms (continuous averaging).\n\nReturns:\n    Premium, Greeks, and — for Monte Carlo only — the standard error.\n\nRaises:\n    ValidationError: If ``forward``, ``strike``, ``sigma`` or ``time_to_expiry``\n        is not > 0, ``discount_factor`` is outside ``(0, 1]``, ``method``\n        contradicts ``averaging``, ``forward_bump_fraction``/``vol_bump``/\n        ``time_bump`` is not > 0, ``averaging_points`` < 1, or — for\n        ``method=\"monte_carlo\"`` — ``seed`` is missing or ``path_count`` < 1000.\n    NativeExtensionError: If ``method=\"monte_carlo\"`` is requested without a\n        built native Rust extension.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 301
        },
        {
          "name": "price_barrier",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.price_barrier",
          "kind": "function",
          "signature": "price_barrier(request: BarrierOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, time_bump: float=_TIME_BUMP) -> ExoticOptionResult",
          "summary": "Price a single-barrier option via the Reiner-Rubinstein closed form (Req 6.2).",
          "doc": "Price a single-barrier option via the Reiner-Rubinstein closed form (Req 6.2).\n\nBarrier-vs-forward consistency (Property 17): an *up* barrier must sit strictly\nabove the forward and a *down* barrier strictly below — a barrier on the wrong\nside (or exactly at the forward) is already breached at inception and is rejected\nbefore any computation. Greeks are central finite differences of the barrier\nkernel.\n\nArgs:\n    request: Fully specified barrier option; validated eagerly before any\n        computation (Req 6.4).\n    forward_bump_fraction: Relative forward bump for delta/gamma, positive\n        (default ``1e-4``).\n    vol_bump: Absolute vol bump for vega, positive (default ``1e-4``).\n    time_bump: Absolute time bump for theta, positive (default ``1e-6``).\n\nReturns:\n    Premium and Greeks (``standard_error`` is ``None`` for closed forms).\n\nRaises:\n    ValidationError: If ``forward``, ``strike``, ``barrier``, ``sigma`` or\n        ``time_to_expiry`` is not > 0, ``discount_factor`` is outside ``(0, 1]``,\n        ``forward_bump_fraction``/``vol_bump``/``time_bump`` is not > 0, or\n        ``barrier`` is on the wrong side of ``forward`` for ``barrier_type``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 372
        },
        {
          "name": "price_cap_floor",
          "module": "pricing",
          "qualified": "quantvolt.pricing.vanilla.price_cap_floor",
          "kind": "function",
          "signature": "price_cap_floor(request: CapFloorRequest, *, max_strip_periods: int=_MAX_STRIP_PERIODS) -> CapFloorResult",
          "summary": "Price a cap/floor as a strip of independently priced caplets/floorlets.",
          "doc": "Price a cap/floor as a strip of independently priced caplets/floorlets.\n\nComposite intent (Req 5.6, Property 16): each period is priced through\n:func:`price_vanilla_option` with its own forward, volatility,\ntime-to-expiry, discount factor and notional; the result carries both the\nper-period results and their plain sums (aggregate premium via ``sum``,\naggregate Greeks via ``Greeks.__add__`` from ``Greeks.zero()``), so the\naggregate equals the sum of the per-period values exactly.\n\nConsistency rule: each caplet's own ``option_type`` must price on the same\ncall/put side as the strip — ``\"call\"``/``\"cap\"`` labels inside a ``\"cap\"``\nstrip, ``\"put\"``/``\"floor\"`` inside a ``\"floor\"`` strip. A mismatched\ncaplet is rejected with a :class:`ValidationError` rather than silently\nrepriced as the strip side (fail loudly, coding-style.md §7).\n\nStrike/notional consistency (Req 5.6): a cap/floor strip has ONE strike\n(the cap/floor rate) and ONE notional; per Req 5.6 only ``forward``,\n``discount_factor`` and ``time_to_expiry`` vary caplet-by-caplet. Every\ncaplet's own ``strike`` and ``notional`` fields (each caplet is a full\n:class:`VanillaOptionRequest`, so it structurally carries them) must\ntherefore equal ``request.strike`` / ``request.notional`` exactly; a\ndivergent caplet is rejected with a :class:`ValidationError` naming the\ncaplet index rather than silently pricing on its own (ignored) values.\n\nArgs:\n    request: The strip; validated eagerly — including the strip-length\n        cap — before any pricing.\n    max_strip_periods: Maximum number of caplets/floorlets in the strip,\n        at least 1 (default 120, Req 5.6).\n\nReturns:\n    Aggregate premium/Greeks plus the per-period results, ordered as the\n    input caplets.\n\nRaises:\n    ValidationError: If ``strike`` or ``notional`` is not > 0,\n        ``max_strip_periods`` < 1, ``caplets`` is empty or exceeds\n        ``max_strip_periods``, a caplet's ``option_type`` is on the wrong\n        side for the strip, a caplet's ``strike``/``notional`` diverges\n        from the strip's (naming the caplet index), or any caplet fails\n        the :func:`price_vanilla_option` domain checks.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 117
        },
        {
          "name": "price_futures",
          "module": "pricing",
          "qualified": "quantvolt.pricing.futures.price_futures",
          "kind": "function",
          "signature": "price_futures(contract: FuturesContract | ForwardContract, forward_curve: ForwardCurve, valuation_date: date, discount_curve: DiscountCurve, *, settlement_lag_days: int=0) -> FuturesPricingResult",
          "summary": "Price a futures or forward contract against a forward curve (Req 3.1, 3.2).",
          "doc": "Price a futures or forward contract against a forward curve (Req 3.1, 3.2).\n\n``NPV = discount_factor(settlement_date) * (forward_price - contract_price) * notional``\nwith a positive notional meaning long; ``delta`` is :func:`futures_delta` at the\ndefault bump. ``settlement_date`` is the delivery period's last day plus\n``settlement_lag_days`` calendar days.\n\nArgs:\n    contract: The futures or forward contract to price.\n    forward_curve: Must have a node for ``contract.delivery_period``.\n    valuation_date: The date NPV is computed as of.\n    discount_curve: Must cover the settlement date.\n    settlement_lag_days: Calendar days added to the delivery period's last\n        day to get the settlement date used for the discount factor\n        (default 0, non-negative).\n\nRaises:\n    ValidationError: If ``settlement_lag_days`` is negative.\n    ExpiredContractError: If the delivery period ended strictly before\n        ``valuation_date`` (Req 3.3).\n    MissingTenorError: If ``forward_curve`` has no node for the delivery period\n        or ``discount_curve`` does not cover the settlement date (Req 3.4).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/futures.py",
          "line": 65
        },
        {
          "name": "price_lookback",
          "module": "pricing",
          "qualified": "quantvolt.pricing.exotic.price_lookback",
          "kind": "function",
          "signature": "price_lookback(request: LookbackOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, time_bump: float=_TIME_BUMP) -> ExoticOptionResult",
          "summary": "Price a lookback option on a forward (Req 6.3).",
          "doc": "Price a lookback option on a forward (Req 6.3).\n\nStrike-type dispatch: ``\"floating\"`` prices via Goldman-Sosin-Gatto and must carry\n``strike=None`` (the strike *is* the running extreme); ``\"fixed\"`` prices via\nConze-Viswanathan and requires a positive ``strike``. Greeks are central finite\ndifferences of the selected kernel.\n\nArgs:\n    request: Fully specified lookback option; validated eagerly before any\n        computation (Req 6.4).\n    forward_bump_fraction: Relative forward bump for delta/gamma, positive\n        (default ``1e-4``).\n    vol_bump: Absolute vol bump for vega, positive (default ``1e-4``).\n    time_bump: Absolute time bump for theta, positive (default ``1e-6``).\n\nReturns:\n    Premium and Greeks (``standard_error`` is ``None`` for closed forms).\n\nRaises:\n    ValidationError: If ``forward``, ``sigma`` or ``time_to_expiry`` is not > 0,\n        ``discount_factor`` is outside ``(0, 1]``,\n        ``forward_bump_fraction``/``vol_bump``/``time_bump`` is not > 0, a\n        floating-strike request carries a ``strike``, or a fixed-strike request\n        is missing a positive ``strike``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/exotic.py",
          "line": 500
        },
        {
          "name": "price_spark_spread_option",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spread_option.price_spark_spread_option",
          "kind": "function",
          "signature": "price_spark_spread_option(request: SpreadOptionRequest, heat_rate: float, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, correlation_bump: float=_CORRELATION_BUMP) -> SpreadOptionResult",
          "summary": "Price a spark spread: a call on ``F_power - heat_rate * F_gas - strike`` (Req 7.3).",
          "doc": "Price a spark spread: a call on ``F_power - heat_rate * F_gas - strike`` (Req 7.3).\n\n``request.forward1`` is the power forward and ``request.forward2`` the RAW gas\nforward. The gas-leg notional is ``notional_power x heat_rate``, realised by\ntransforming the request to ``forward2 * heat_rate`` (``sigma2`` unchanged: a\nconstant multiple of a lognormal forward keeps the same lognormal volatility)\nand delegating to :func:`price_spread_option`. ``forward_bump_fraction``/\n``vol_bump``/``correlation_bump`` are passed through unchanged.\n\n``delta2`` convention (Req 7.2): the transformed request's ``delta2`` is the\nsensitivity to the SCALED gas forward (``heat_rate x F_gas``); this function\nchain-rules it back onto the raw ``F_gas`` the caller passed\n(``delta2_raw = delta2_transformed x heat_rate``), so ``delta2`` always means\n\"sensitivity to the underlying commodity forward the caller supplied\" — the\nsame convention :mod:`quantvolt.pricing.tolling` uses for its fuel/EUA deltas.\n\nRaises:\n    ValidationError: If ``heat_rate`` is not > 0, or the (transformed)\n        request violates any :func:`price_spread_option` constraint.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 201
        },
        {
          "name": "price_spread_option",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spread_option.price_spread_option",
          "kind": "function",
          "signature": "price_spread_option(request: SpreadOptionRequest, *, forward_bump_fraction: float=_FORWARD_BUMP_FRACTION, vol_bump: float=_VOL_BUMP, correlation_bump: float=_CORRELATION_BUMP) -> SpreadOptionResult",
          "summary": "Price a spread call and its sensitivities (Req 7.1, 7.2).",
          "doc": "Price a spread call and its sensitivities (Req 7.1, 7.2).\n\n``strike == 0.0`` prices via Margrabe's exact formula, any other strike via\nKirk's approximation (Property 18). The premium is the kernel premium\nscaled by ``request.notional``; the five sensitivities are central finite\ndifferences of the same kernel, likewise notional-scaled (module docstring\nlists the bump sizes).\n\nArgs:\n    request: Fully specified spread-option request; validated eagerly\n        before any computation.\n    forward_bump_fraction: Relative forward bump for delta1/delta2,\n        positive (default ``1e-4``).\n    vol_bump: Absolute vol bump for vega1/vega2, positive (default\n        ``1e-4``).\n    correlation_bump: Absolute correlation bump for\n        ``correlation_sensitivity``, positive (default ``1e-4``); clamped\n        so ``correlation +/- bump`` stays strictly inside ``(-1, 1)``.\n\nRaises:\n    ValidationError: If ``correlation`` is outside ``(-1, 1)`` (Req 7.4),\n        any of ``forward1``, ``forward2``, ``sigma1``, ``sigma2``,\n        ``time_to_expiry``, ``notional`` is not > 0, ``strike`` < 0,\n        ``discount_factor`` is outside ``(0, 1]``, or\n        ``forward_bump_fraction``/``vol_bump``/``correlation_bump`` is not\n        > 0.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spread_option.py",
          "line": 119
        },
        {
          "name": "price_swap",
          "module": "pricing",
          "qualified": "quantvolt.pricing.swap.price_swap",
          "kind": "function",
          "signature": "price_swap(swap: SwapContract, forward_curve: ForwardCurve, discount_curve: DiscountCurve, *, day_count: Callable[[date, date], float]=actual_365, settlement_lag_days: int=0, rate_bump: float=_BASIS_POINT) -> SwapPricingResult",
          "summary": "Price a fixed-for-floating swap: NPV, per-period delta, and rho (Req 4.1-4.3).",
          "doc": "Price a fixed-for-floating swap: NPV, per-period delta, and rho (Req 4.1-4.3).\n\nSee the module docstring for the cash-flow (payer-of-fixed / receiver-of-floating)\nand rho (per-bp parallel shift of the continuously compounded zero rate) conventions.\n\nArgs:\n    swap: The swap contract to price.\n    forward_curve: Must cover every delivery period in ``swap.schedule``.\n    discount_curve: Must cover every period's settlement date.\n    day_count: Year-fraction convention used for the rho computation, taking\n        ``(start, end)`` and returning the fraction of a year (default\n        :func:`~quantvolt.numerics.daycount.actual_365`).\n    settlement_lag_days: Calendar days added to each period's last day to get\n        the settlement date used for both the discount-factor lookup and the\n        rho year fraction (default 0, non-negative).\n    rate_bump: The per-basis-point size used to scale rho — the NPV change\n        per this parallel shift of the continuously compounded zero rate\n        (default ``1e-4``, i.e. one basis point).\n\nValidation is eager and ordered, before any computation:\n\n1. ``swap.schedule.periods`` is non-empty;\n2. sort-and-scan overlap/duplicate detection, raising :class:`ValidationError`\n   identifying each offending pair (defensive — see\n   :func:`_require_no_overlapping_periods`);\n3. coverage: every delivery period on the forward curve, then every settlement\n   date within the discount curve's tenor range, raising\n   :class:`MissingTenorError` identifying the missing period(s).\n\nInputs are never mutated; identical inputs produce identical results.\n\nRaises:\n    ValidationError: If ``settlement_lag_days`` is negative or ``rate_bump``\n        is not > 0, in addition to the schedule/coverage errors above.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/swap.py",
          "line": 117
        },
        {
          "name": "price_tolling_agreement",
          "module": "pricing",
          "qualified": "quantvolt.pricing.tolling.price_tolling_agreement",
          "kind": "function",
          "signature": "price_tolling_agreement(plant: PlantConfig, power_curve: ForwardCurve, fuel_curve: ForwardCurve, eua_curve: ForwardCurve, vol_surface: VolatilitySurface, correlation_matrix: np.ndarray, schedule: DeliverySchedule, discount_curve: DiscountCurve, *, capacity: float=_UNIT_NOTIONAL, fuel_sigma: VolatilitySurface | None=None, matrix_tolerance: float=_MATRIX_TOLERANCE, day_count: Callable[[date, date], float]=actual_365, settlement_lag_days: int=0) -> TollingResult",
          "summary": "Value a tolling agreement as a strip of clean spread options (Req 8.1-8.5).",
          "doc": "Value a tolling agreement as a strip of clean spread options (Req 8.1-8.5).\n\nOne clean spark (gas) / clean dark (coal) spread option per delivery\nperiod — see the module docstring for the leg composition, unit chain,\nsingle-surface volatility, correlation-indexing and discounting\nconventions. Validation is eager and complete before any pricing:\nschedule length, correlation matrix, full forward-curve / vol-surface /\ndiscount-curve coverage of the schedule.\n\nArgs:\n    plant: Heat rate, variable O&M cost, emissions intensity, fuel type.\n    power_curve: Power forwards; must cover every schedule period.\n    fuel_curve: Gas or coal forwards; must cover every schedule period.\n    eua_curve: EUA forwards; must cover every schedule period.\n    vol_surface: Surface used for the power leg of every period (and the\n        fuel+carbon leg too, when ``fuel_sigma`` is ``None``).\n    correlation_matrix: At least 3x3, ordered ``[power, fuel, eua]``.\n    schedule: 1-1200 delivery periods.\n    discount_curve: Must cover every period's settlement date.\n    capacity: Per-period notional in MWh, positive (default 1.0 —\n        unit-capacity; the historical behaviour). Scales every per-period\n        spread-option notional and the intrinsic-value payoff.\n    fuel_sigma: Optional separate volatility surface for the fuel+carbon\n        leg; must cover every schedule period. ``None`` (default) reuses\n        ``vol_surface`` for both legs, exactly as before.\n    matrix_tolerance: Absolute tolerance for the correlation matrix's\n        symmetry / unit-diagonal checks (default ``1e-9``); must be > 0\n        (a non-positive or NaN tolerance would silently disable or\n        misreport those checks).\n    day_count: Year-fraction convention for each period's time-to-expiry,\n        taking ``(start, end)`` (default\n        :func:`~quantvolt.numerics.daycount.actual_365`).\n    settlement_lag_days: Calendar days added to each period's last day to\n        get the settlement date used for the discount-factor lookup\n        (default 0, non-negative). Does NOT affect the option's\n        ``time_to_expiry``, which is always ``day_count`` from\n        ``discount_curve.reference_date`` to ``period.last_day`` — the\n        decision horizon, not the payment date.\n\nReturns:\n    NPV, intrinsic/time value decomposition, per-period values, and\n    per-period plus aggregate deltas for ``\"power\"``/``\"fuel\"``/``\"eua\"``\n    (aggregate == sum of per-period exactly, Property 20).\n\nRaises:\n    ValidationError: If the schedule has more than 1200 periods; if the\n        correlation matrix is not a square ndarray of size >= 3x3,\n        symmetric with unit diagonal (within ``matrix_tolerance``) and\n        off-diagonals strictly inside (-1, 1) (Property 19); if\n        ``capacity`` is not > 0, ``settlement_lag_days`` is negative, or\n        ``matrix_tolerance`` is not > 0 (including ``NaN``); or\n        if any per-period spread-option input violates\n        :func:`price_spread_option`'s domain (e.g. a non-positive power or\n        fuel+carbon leg forward).\n    InsufficientDataError: If any forward curve misses any schedule period\n        (naming the commodity and the missing periods, Req 8.4), or the\n        vol surface (or ``fuel_sigma``) misses any tenor (naming them,\n        Req 8.5).\n    MissingTenorError: If the discount curve does not cover every\n        period's settlement date.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/tolling.py",
          "line": 231
        },
        {
          "name": "price_vanilla_option",
          "module": "pricing",
          "qualified": "quantvolt.pricing.vanilla.price_vanilla_option",
          "kind": "function",
          "signature": "price_vanilla_option(request: VanillaOptionRequest) -> VanillaOptionResult",
          "summary": "Price a single vanilla European option on a forward under Black-76.",
          "doc": "Price a single vanilla European option on a forward under Black-76.\n\n``\"cap\"`` and ``\"floor\"`` requests denote a single caplet/floorlet and are\npriced as the equivalent call/put on the floating (forward) price. Premium\nand Greeks are per-unit kernel outputs scaled by ``notional``.\n\nArgs:\n    request: Fully specified option; all domains are validated eagerly\n        before any computation (Req 5.4).\n\nReturns:\n    The notional-scaled premium and Greeks.\n\nRaises:\n    ValidationError: If ``forward``, ``strike``, ``sigma``,\n        ``time_to_expiry`` or ``notional`` is not > 0, or\n        ``discount_factor`` is outside ``(0, 1]``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/vanilla.py",
          "line": 71
        },
        {
          "name": "settle_power_hedge_interval",
          "module": "pricing",
          "qualified": "quantvolt.pricing.power_hedge.settle_power_hedge_interval",
          "kind": "function",
          "signature": "settle_power_hedge_interval(contract: PowerHedgeContract, interval: PowerDeliveryInterval, spot_price_per_mwh: float) -> PowerHedgeSettlement",
          "summary": "Settle one observed interval; this is realized payoff, not option valuation.",
          "doc": "Settle one observed interval; this is realized payoff, not option valuation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 45
        },
        {
          "name": "settle_power_hedges_frame",
          "module": "pricing",
          "qualified": "quantvolt.pricing.power_hedge.settle_power_hedges_frame",
          "kind": "function",
          "signature": "settle_power_hedges_frame(contracts: Sequence[PowerHedgeContract], data: pl.DataFrame, *, interval_start_column: str='interval_start_utc', interval_end_column: str='interval_end_utc', spot_price_column: str='spot_price_per_mwh', columns: PowerHedgeDataColumns | None=None) -> pl.DataFrame",
          "summary": "Settle hedges against caller data, returning one row per active hedge/interval.",
          "doc": "Settle hedges against caller data, returning one row per active hedge/interval.\n\nInput order is preserved. Intervals need not be contiguous because hedge books\nmay be evaluated on selected observations, but duplicate starts and unsorted\nobservations are rejected.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/power_hedge.py",
          "line": 82
        },
        {
          "name": "settle_ppa_frame",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.settle_ppa_frame",
          "kind": "function",
          "signature": "settle_ppa_frame(contract: PpaContract, data: pl.DataFrame, *, columns: PpaDataColumns | None=None, imbalance_policy: MissingImbalancePricePolicy=MissingImbalancePricePolicy.ERROR, require_contiguous: bool=True, hedges: Sequence[PowerHedgeContract]=()) -> pl.DataFrame",
          "summary": "Validate and settle caller-supplied interval data into a canonical ledger.",
          "doc": "Validate and settle caller-supplied interval data into a canonical ledger.\n\nInputs remain caller-owned and are never modified. Column names may be mapped\nwith ``PpaDataColumns``. By default physical PPAs require genuine shortfall and\nexcess prices: using spot as an imbalance proxy must be explicitly requested.\n\nThe result contains one row per input interval and every signed cash-flow\ncomponent used to reconstruct ``net_cashflow``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 135
        },
        {
          "name": "settle_ppa_interval",
          "module": "pricing",
          "qualified": "quantvolt.pricing.ppa.settle_ppa_interval",
          "kind": "function",
          "signature": "settle_ppa_interval(contract: PpaContract, interval: PowerDeliveryInterval, *, contracted_mwh: float, metered_generation_mwh: float, spot_price_per_mwh: float, shortfall_price_per_mwh: float | None=None, excess_price_per_mwh: float | None=None, hedge_cashflow: float=0.0, option_payoff: float=0.0, option_premium: float=0.0, variable_cost: float=0.0, transaction_cost: float=0.0) -> PpaIntervalSettlement",
          "summary": "Settle one PPA interval from a producer's perspective.",
          "doc": "Settle one PPA interval from a producer's perspective.\n\nFor a physical PPA, contracted energy earns the fixed price; own generation\nserves that obligation first, a shortfall is bought at ``shortfall_price``,\nand excess generation is sold at ``excess_price``. Missing imbalance prices\nexplicitly fall back to spot.\n\nFor a financial CfD, all metered generation is sold spot and the contracted\nvolume receives ``fixed - spot``. There is no physical delivery shortfall.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/ppa.py",
          "line": 278
        },
        {
          "name": "spark_spread",
          "module": "pricing",
          "qualified": "quantvolt.pricing.spreads.spark_spread",
          "kind": "function",
          "signature": "spark_spread(power_curve: ForwardCurve, fuel_curve: ForwardCurve, heat_rate: float, variable_cost: float, emissions_cost: float) -> SpreadResult",
          "summary": "Spark spread (gas-fired generation margin) per shared delivery period.",
          "doc": "Spark spread (gas-fired generation margin) per shared delivery period.\n\nFor each period in the intersection of ``power_curve`` and ``fuel_curve``:\n``power_price - heat_rate * fuel_price - variable_cost - emissions_cost``\n(Req 2.1, Property 6). Computing a spark spread never reads or writes any dark\nvalues: each call returns a new immutable :class:`SpreadResult` labelled\n``\"spark\"``, so any existing dark result remains untouched.\n\nRaises :class:`~quantvolt.exceptions.ValidationError` unless ``heat_rate > 0``,\n``variable_cost >= 0`` and ``emissions_cost >= 0``, and\n:class:`InsufficientDataError` when the curves share no delivery periods.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/spreads.py",
          "line": 205
        },
        {
          "name": "value_transport_right",
          "module": "pricing",
          "qualified": "quantvolt.pricing.transmission_right.value_transport_right",
          "kind": "function",
          "signature": "value_transport_right(right: TransportRight, curve_a: ForwardCurve, curve_b: ForwardCurve, discount_curve: DiscountCurve, *, vols: tuple[float, float] | None=None, correlation: float | None=None, day_count: Callable[[date, date], float]=actual_365, settlement_lag_days: int=0) -> TransportRightResult",
          "summary": "Value a transmission or pipeline right (Req 24.1-24.5, Properties 67-68).",
          "doc": "Value a transmission or pipeline right (Req 24.1-24.5, Properties 67-68).\n\n``curve_a`` is the origin (hub A) forward curve and ``curve_b`` the destination\n(hub B) curve; their commodity ids must match ``right.origin`` / ``right.destination``\nso curves cannot be silently swapped. Valuation covers the shared periods of both\ncurves within the right's schedule (Req 24.5). Each period's settlement is its\n``last_day`` plus ``settlement_lag_days`` (the swap/tolling convention): the\ndiscount factor is taken there. For the option path, ``time_to_expiry`` is\n``day_count`` (default actual/365) from ``discount_curve.reference_date`` to the\nperiod's ``last_day`` (the flow decision horizon) — ``settlement_lag_days`` never\nshifts the volatility horizon, only the discount-factor lookup date.\n\nIntrinsic value is ``Σ D · Q_delivered · max(P_B - P_A - T_AB, 0)``. Supplying\n``vols=(sigma_origin, sigma_destination)`` and ``correlation`` (both or neither,\nReq 24.2) adds the spread-option extrinsic value per period. A ``BIDIRECTIONAL``\nright commits each period to the best of A→B (tariff ``tariff``), B→A (tariff\n``reverse_tariff``, defaulting to ``tariff``) or no-flow, and is subadditive versus\ntwo one-way rights (Property 68).\n\nArgs:\n    right: The transmission or pipeline right to value.\n    curve_a: Origin (hub A) forward curve.\n    curve_b: Destination (hub B) forward curve.\n    discount_curve: Discount curve for settlement dates.\n    vols: Optional ``(sigma_origin, sigma_destination)`` pair (both or\n        neither with ``correlation``).\n    correlation: Optional origin/destination correlation (both or neither\n        with ``vols``).\n    day_count: Year-fraction convention for the option ``time_to_expiry``,\n        taking ``(start, end)`` (default\n        :func:`~quantvolt.numerics.daycount.actual_365`).\n    settlement_lag_days: Calendar days added to each period's last day to\n        get the settlement date used for the discount factor (default 0,\n        non-negative). Does NOT affect the option's ``time_to_expiry``,\n        which is always ``day_count`` to ``period.last_day``.\n\nRaises:\n    ValidationError: If ``vols``/``correlation`` are not supplied both-or-neither\n        (Req 24.2), if the curve commodity ids do not match ``right.origin`` /\n        ``right.destination``, if ``settlement_lag_days`` is negative, or if a\n        location forward is non-positive on the option path (from the\n        spread-option engine).\n    InsufficientDataError: If the two curves share no schedule period (Req 24.5).\n    MissingTenorError: If the discount curve does not cover a period's settlement.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/pricing/transmission_right.py",
          "line": 241
        }
      ]
    },
    {
      "name": "portfolio",
      "qualified": "quantvolt.portfolio",
      "description": "Portfolio assembly, valuation and realized settlement.",
      "symbols": [
        {
          "name": "MarketData",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.valuation.MarketData",
          "kind": "class",
          "signature": "MarketData(forward_curves: dict[str, ForwardCurve], discount_curve: DiscountCurve, valuation_date: date)",
          "summary": "The market inputs needed to value a portfolio (Req 13.2).",
          "doc": "The market inputs needed to value a portfolio (Req 13.2).\n\n``forward_curves`` is defensively copied into a fresh ``dict`` at construction\n(the ``object.__setattr__`` pattern used by ``PricedPosition``), so later mutation\nof the caller's mapping cannot reach into this frozen value object. The stored copy\nis treated as immutable by convention from then on — nothing in the library writes\nto it.",
          "methods": [
            {
              "name": "curve_for",
              "signature": "curve_for(self, commodity_id: str) -> ForwardCurve",
              "summary": "Return the forward curve for ``commodity_id``; raise if absent (Task 61)."
            }
          ],
          "fields": [
            {
              "name": "forward_curves",
              "type": "dict[str, ForwardCurve]",
              "default": null
            },
            {
              "name": "discount_curve",
              "type": "DiscountCurve",
              "default": null
            },
            {
              "name": "valuation_date",
              "type": "date",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/valuation.py",
          "line": 45
        },
        {
          "name": "Portfolio",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.model.Portfolio",
          "kind": "class",
          "signature": "Portfolio(positions: tuple[Position, ...], name: str | None = None)",
          "summary": "An immutable, iterable Composite of positions — one and many handled uniformly.",
          "doc": "An immutable, iterable Composite of positions — one and many handled uniformly.\n\nSatisfies Req 13.1: an ordered, immutable collection whose positions can be iterated\nand counted without mutation — ``__iter__`` delegates to the underlying tuple in\nconstruction order and ``__len__`` counts without side effects.",
          "methods": [],
          "fields": [
            {
              "name": "positions",
              "type": "tuple[Position, ...]",
              "default": null
            },
            {
              "name": "name",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 77
        },
        {
          "name": "PortfolioSettlement",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.settlement.PortfolioSettlement",
          "kind": "class",
          "signature": "PortfolioSettlement(total_cashflow: float, settled: tuple[SettledPortfolioPosition, ...], unsettled: tuple[Position, ...])",
          "summary": "Realized PPA/hedge cash flow plus positions not handled by this engine.",
          "doc": "Realized PPA/hedge cash flow plus positions not handled by this engine.",
          "methods": [],
          "fields": [
            {
              "name": "total_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "settled",
              "type": "tuple[SettledPortfolioPosition, ...]",
              "default": null
            },
            {
              "name": "unsettled",
              "type": "tuple[Position, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/settlement.py",
          "line": 35
        },
        {
          "name": "PortfolioValuation",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.valuation.PortfolioValuation",
          "kind": "class",
          "signature": "PortfolioValuation(total_npv: float, priced: tuple[PricedPosition, ...], unpriced: tuple[Position, ...])",
          "summary": "Aggregate NPV plus per-position results, in portfolio order (Req 13.2, 13.3).",
          "doc": "Aggregate NPV plus per-position results, in portfolio order (Req 13.2, 13.3).",
          "methods": [],
          "fields": [
            {
              "name": "total_npv",
              "type": "float",
              "default": null
            },
            {
              "name": "priced",
              "type": "tuple[PricedPosition, ...]",
              "default": null
            },
            {
              "name": "unpriced",
              "type": "tuple[Position, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/valuation.py",
          "line": 83
        },
        {
          "name": "Position",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.model.Position",
          "kind": "class",
          "signature": "Position(instrument: Instrument, position_id: str | None = None, tags: tuple[str, ...] = ())",
          "summary": "A single held instrument, plus optional identity/tags. Notional lives on the instrument.",
          "doc": "A single held instrument, plus optional identity/tags. Notional lives on the instrument.",
          "methods": [],
          "fields": [
            {
              "name": "instrument",
              "type": "Instrument",
              "default": null
            },
            {
              "name": "position_id",
              "type": "str | None",
              "default": "None"
            },
            {
              "name": "tags",
              "type": "tuple[str, ...]",
              "default": "()"
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 28
        },
        {
          "name": "PricedPosition",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.model.PricedPosition",
          "kind": "class",
          "signature": "PricedPosition(position: Position, npv: float, delta: dict[tuple[str, DeliveryPeriod], float] = field(default_factory=dict), greeks: Greeks | None = None, reference_prices: dict[tuple[str, DeliveryPeriod], float] = field(default_factory=dict))",
          "summary": "A position after valuation — exactly what RiskEngine and mark_to_market consume.",
          "doc": "A position after valuation — exactly what RiskEngine and mark_to_market consume.\n\nInvariants enforced at construction (eager boundary validation, ``coding-style.md`` §7):\n\n- ``npv`` must be finite. A NaN or ±inf NPV would silently poison every downstream\n  aggregate (portfolio NPV, VaR loss quantiles), so it is rejected here with a\n  :class:`~quantvolt.exceptions.ValidationError` naming ``npv``.\n- ``delta`` is defensively copied: the mapping is snapshot into a fresh ``dict`` at\n  construction, so later mutation of the caller's dict cannot reach into this frozen\n  value object. The stored copy is treated as immutable by convention from then on —\n  nothing in the library writes to it. (``object.__setattr__`` is the sanctioned way\n  to assign inside ``__post_init__`` of a frozen dataclass and works with ``slots``.)\n- ``reference_prices`` is defensively copied the same way. It optionally records the\n  forward price level ``value_portfolio`` observed for each ``delta`` entry's\n  ``(commodity_id, delivery period)`` key, in the same units as that commodity's\n  forward curve. ``RiskEngine.apply_scenario`` needs this to correctly scale a\n  *relative* (fractional) scenario shock into currency P&L\n  (``delta x reference_price x shock`` — see :mod:`quantvolt.risk.scenarios`); a key\n  absent from ``reference_prices`` (including an entirely empty mapping, the default)\n  falls back to a reference price of ``1.0``, preserving the legacy\n  ``delta x shock`` behaviour for hand-built positions that never populate it.",
          "methods": [],
          "fields": [
            {
              "name": "position",
              "type": "Position",
              "default": null
            },
            {
              "name": "npv",
              "type": "float",
              "default": null
            },
            {
              "name": "delta",
              "type": "dict[tuple[str, DeliveryPeriod], float]",
              "default": "field(default_factory=dict)"
            },
            {
              "name": "greeks",
              "type": "Greeks | None",
              "default": "None"
            },
            {
              "name": "reference_prices",
              "type": "dict[tuple[str, DeliveryPeriod], float]",
              "default": "field(default_factory=dict)"
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 37
        },
        {
          "name": "SettledPortfolioPosition",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.settlement.SettledPortfolioPosition",
          "kind": "class",
          "signature": "SettledPortfolioPosition(position: Position, ledger: pl.DataFrame, total_cashflow: float)",
          "summary": "One interval-settled position and its immutable aggregate result.",
          "doc": "One interval-settled position and its immutable aggregate result.",
          "methods": [],
          "fields": [
            {
              "name": "position",
              "type": "Position",
              "default": null
            },
            {
              "name": "ledger",
              "type": "pl.DataFrame",
              "default": null
            },
            {
              "name": "total_cashflow",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/portfolio/settlement.py",
          "line": 23
        },
        {
          "name": "settle_energy_portfolio",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.settlement.settle_energy_portfolio",
          "kind": "function",
          "signature": "settle_energy_portfolio(portfolio: Portfolio, interval_data: Mapping[str, pl.DataFrame], *, ppa_columns: Mapping[str, PpaDataColumns] | None=None, hedge_columns: Mapping[str, PowerHedgeDataColumns] | None=None, imbalance_policies: Mapping[str, MissingImbalancePricePolicy] | None=None) -> PortfolioSettlement",
          "summary": "Settle all PPA and typed power-hedge positions using caller-owned data.",
          "doc": "Settle all PPA and typed power-hedge positions using caller-owned data.\n\n``interval_data`` is keyed by ``Position.position_id``. Other financial\ninstruments remain in ``unsettled`` because their realized exchange/OTC\nsettlement conventions belong to their own engines. PPA hedges represented as\nseparate portfolio positions are not also embedded in the PPA ledger, preventing\ndouble counting at aggregation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/portfolio/settlement.py",
          "line": 51
        },
        {
          "name": "value_portfolio",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.valuation.value_portfolio",
          "kind": "function",
          "signature": "value_portfolio(portfolio: Portfolio, market_data: MarketData, pricers: Mapping[type[Any], Pricer] | None=None) -> PortfolioValuation",
          "summary": "Value every position via its registered pricer and aggregate the NPV (Req 13.2-13.6).",
          "doc": "Value every position via its registered pricer and aggregate the NPV (Req 13.2-13.6).\n\nThe dispatch registry is :data:`DEFAULT_PRICERS` merged with the caller-supplied\n``pricers`` (caller entries win) — the open/closed extension seam: new instrument\ntypes are registered, never edited in (Req 13.4). Positions are processed in\nportfolio order; a position whose instrument type has no registered pricer is\nreturned in ``unpriced`` rather than raising, so the rest of the book is still\nvalued, and ``total_npv`` sums the priced positions only (Req 13.3).\n\nPricing errors — :class:`~quantvolt.exceptions.ExpiredContractError`,\n:class:`~quantvolt.exceptions.MissingTenorError`, a missing forward curve from\n:meth:`MarketData.curve_for` — **propagate**: they are data errors on a position\nthe registry *does* know how to price, not registry misses, and silently skipping\nthem would hide a mispriced book.\n\nInputs are never mutated, and identical inputs produce identical results (Req 13.6).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/portfolio/valuation.py",
          "line": 196
        },
        {
          "name": "Instrument",
          "module": "portfolio",
          "qualified": "quantvolt.portfolio.model.Instrument",
          "kind": "constant",
          "signature": "Instrument",
          "summary": "Public type alias for the instrument variants that a Portfolio Position can hold..",
          "doc": "Public type alias for the instrument variants that a Portfolio Position can hold.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/portfolio/model.py",
          "line": 1
        }
      ]
    },
    {
      "name": "risk",
      "qualified": "quantvolt.risk",
      "description": "VaR, CFaR, stress scenarios, covariance and credit risk.",
      "symbols": [
        {
          "name": "CashflowStrategyComparison",
          "module": "risk",
          "qualified": "quantvolt.risk.cashflow_metrics.CashflowStrategyComparison",
          "kind": "class",
          "signature": "CashflowStrategyComparison(benchmark: str, confidence_level: float, metrics: tuple[CashflowStrategyMetrics, ...])",
          "summary": "Metrics in caller strategy order with an explicit benchmark identity.",
          "doc": "Metrics in caller strategy order with an explicit benchmark identity.",
          "methods": [
            {
              "name": "for_strategy",
              "signature": "for_strategy(self, strategy: str) -> CashflowStrategyMetrics",
              "summary": "Return one named result or fail loudly with available names."
            }
          ],
          "fields": [
            {
              "name": "benchmark",
              "type": "str",
              "default": null
            },
            {
              "name": "confidence_level",
              "type": "float",
              "default": null
            },
            {
              "name": "metrics",
              "type": "tuple[CashflowStrategyMetrics, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/cashflow_metrics.py",
          "line": 35
        },
        {
          "name": "CashflowStrategyMetrics",
          "module": "risk",
          "qualified": "quantvolt.risk.cashflow_metrics.CashflowStrategyMetrics",
          "kind": "class",
          "signature": "CashflowStrategyMetrics(strategy: str, observations: int, total_cashflow: float, mean_cashflow: float, sample_std_cashflow: float, lower_percentile_cashflow: float, minimum_cashflow: float, maximum_cashflow: float, cfar: float, negative_observations: int, total_difference_vs_benchmark: float, cfar_reduction_vs_benchmark: float, volatility_reduction_vs_benchmark: float)",
          "summary": "One strategy's realized cash-flow distribution and benchmark differences.",
          "doc": "One strategy's realized cash-flow distribution and benchmark differences.",
          "methods": [],
          "fields": [
            {
              "name": "strategy",
              "type": "str",
              "default": null
            },
            {
              "name": "observations",
              "type": "int",
              "default": null
            },
            {
              "name": "total_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "mean_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "sample_std_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "lower_percentile_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "minimum_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "maximum_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "cfar",
              "type": "float",
              "default": null
            },
            {
              "name": "negative_observations",
              "type": "int",
              "default": null
            },
            {
              "name": "total_difference_vs_benchmark",
              "type": "float",
              "default": null
            },
            {
              "name": "cfar_reduction_vs_benchmark",
              "type": "float",
              "default": null
            },
            {
              "name": "volatility_reduction_vs_benchmark",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/cashflow_metrics.py",
          "line": 16
        },
        {
          "name": "CFaRResult",
          "module": "risk",
          "qualified": "quantvolt.risk.cfar.CFaRResult",
          "kind": "class",
          "signature": "CFaRResult(cfar_95: float, expected: float, p5: float, p50: float, p95: float, horizon: int, seed: int, aggregate_cashflows: tuple[float, ...], consistency: Mapping[str, str] | None)",
          "summary": "Outcome of a :func:`cash_flow_at_risk` computation (Req 16.1).",
          "doc": "Outcome of a :func:`cash_flow_at_risk` computation (Req 16.1).\n\n``cfar_95`` is the shortfall below the expected aggregate cash flow at the\ncaller's ``confidence_level`` (95% by default; see the module docstring for the\nexact definition and sign convention); it is always ``>= 0``. ``expected`` is the\nmean and ``p5`` / ``p50`` / ``p95`` are percentiles of the aggregate cash-flow\ndistribution (``p5`` sits at ``confidence_level``'s complement — the 5th\npercentile at the default 95% confidence level; ``p50`` / ``p95`` are always the\n50th / 95th percentiles). ``aggregate_cashflows`` is the per-scenario aggregated\ncash flow in the input scenario order, exposing the full distribution. ``horizon``\nand ``seed`` are echoed for reproducibility, and ``consistency`` is the\ncaller-supplied market/operational consistency metadata carried verbatim.",
          "methods": [],
          "fields": [
            {
              "name": "cfar_95",
              "type": "float",
              "default": null
            },
            {
              "name": "expected",
              "type": "float",
              "default": null
            },
            {
              "name": "p5",
              "type": "float",
              "default": null
            },
            {
              "name": "p50",
              "type": "float",
              "default": null
            },
            {
              "name": "p95",
              "type": "float",
              "default": null
            },
            {
              "name": "horizon",
              "type": "int",
              "default": null
            },
            {
              "name": "seed",
              "type": "int",
              "default": null
            },
            {
              "name": "aggregate_cashflows",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "consistency",
              "type": "Mapping[str, str] | None",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/cfar.py",
          "line": 94
        },
        {
          "name": "CounterpartyCreditDetail",
          "module": "risk",
          "qualified": "quantvolt.risk.credit_var.CounterpartyCreditDetail",
          "kind": "class",
          "signature": "CounterpartyCreditDetail(counterparty: str, default_probability: float, exposure: float, lgd: float, expected_loss: float)",
          "summary": "Per-counterparty credit inputs and closed-form expected loss (Req 17.1).",
          "doc": "Per-counterparty credit inputs and closed-form expected loss (Req 17.1).\n\n``exposure`` is the exposure-at-default ``EAD = max(net exposure, 0)`` actually used in\nthe simulation; ``lgd`` is ``1 - recovery``; ``expected_loss`` is the analytic\n``default_probability * lgd * exposure`` (exact, independent of the Monte Carlo draw).",
          "methods": [],
          "fields": [
            {
              "name": "counterparty",
              "type": "str",
              "default": null
            },
            {
              "name": "default_probability",
              "type": "float",
              "default": null
            },
            {
              "name": "exposure",
              "type": "float",
              "default": null
            },
            {
              "name": "lgd",
              "type": "float",
              "default": null
            },
            {
              "name": "expected_loss",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/credit_var.py",
          "line": 115
        },
        {
          "name": "CreditVaRResult",
          "module": "risk",
          "qualified": "quantvolt.risk.credit_var.CreditVaRResult",
          "kind": "class",
          "signature": "CreditVaRResult(credit_var_95: float, credit_var_99: float, expected_credit_loss: float, per_counterparty: tuple[CounterpartyCreditDetail, ...], credit_risk_free: tuple[PricedPosition, ...], seed: int, path_count: int, asset_correlation: float)",
          "summary": "Outcome of a :func:`credit_var` computation (Req 17.1).",
          "doc": "Outcome of a :func:`credit_var` computation (Req 17.1).\n\n``credit_var_95`` / ``credit_var_99`` are the (95% / 99% by default) credit-loss\nquantiles and\n``expected_credit_loss`` the mean loss (see the module docstring for the exact\ndefinitions and sign convention); all three are ``>= 0`` and\n``credit_var_99 >= credit_var_95``. ``per_counterparty`` holds one\n:class:`CounterpartyCreditDetail` per credit-bearing counterparty, ordered by\ncounterparty id. ``credit_risk_free`` lists the positions carrying no counterparty,\nreported rather than dropped silently (Req 17.2). ``seed``, ``path_count`` and\n``asset_correlation`` are echoed for reproducibility.",
          "methods": [],
          "fields": [
            {
              "name": "credit_var_95",
              "type": "float",
              "default": null
            },
            {
              "name": "credit_var_99",
              "type": "float",
              "default": null
            },
            {
              "name": "expected_credit_loss",
              "type": "float",
              "default": null
            },
            {
              "name": "per_counterparty",
              "type": "tuple[CounterpartyCreditDetail, ...]",
              "default": null
            },
            {
              "name": "credit_risk_free",
              "type": "tuple[PricedPosition, ...]",
              "default": null
            },
            {
              "name": "seed",
              "type": "int",
              "default": null
            },
            {
              "name": "path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "asset_correlation",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/credit_var.py",
          "line": 131
        },
        {
          "name": "DeltaMatrix",
          "module": "risk",
          "qualified": "quantvolt.risk.aggregation.DeltaMatrix",
          "kind": "class",
          "signature": "DeltaMatrix(commodities: tuple[str, ...], periods: tuple[DeliveryPeriod, ...], values: tuple[tuple[float, ...], ...])",
          "summary": "Net delta exposure over the union grid of commodities x delivery periods.",
          "doc": "Net delta exposure over the union grid of commodities x delivery periods.\n\nRows (``commodities``) are sorted lexicographically; columns (``periods``) are\nsorted chronologically. The matrix is *dense* over that grid: every\n``(commodity, period)`` combination inside the grid has a cell (0.0 where no\nposition carries that exposure). Combinations outside the grid were never seen in\nany position, so :meth:`delta_at` answers 0.0 for them too — \"not held\" and \"held\nwith zero net delta\" are the same exposure. The shape invariant (one row per\ncommodity, one column per period) is validated at construction, mirroring how\n``DeliverySchedule`` validates its own consistency.",
          "methods": [
            {
              "name": "delta_at",
              "signature": "delta_at(self, commodity_id: str, period: DeliveryPeriod) -> float",
              "summary": "Net delta for one cell; 0.0 for a combination absent from the grid."
            }
          ],
          "fields": [
            {
              "name": "commodities",
              "type": "tuple[str, ...]",
              "default": null
            },
            {
              "name": "periods",
              "type": "tuple[DeliveryPeriod, ...]",
              "default": null
            },
            {
              "name": "values",
              "type": "tuple[tuple[float, ...], ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/aggregation.py",
          "line": 19
        },
        {
          "name": "ExcludedPosition",
          "module": "risk",
          "qualified": "quantvolt.risk.engine.ExcludedPosition",
          "kind": "class",
          "signature": "ExcludedPosition(index: int, reason: Literal['missing_delta', 'missing_npv', 'unresolvable_instrument'])",
          "summary": "A portfolio position omitted from a risk calculation together with the actionable reason for exclusion..",
          "doc": "A portfolio position omitted from a risk calculation together with the actionable reason for exclusion.",
          "methods": [],
          "fields": [
            {
              "name": "index",
              "type": "int",
              "default": null
            },
            {
              "name": "reason",
              "type": "Literal['missing_delta', 'missing_npv', 'unresolvable_instrument']",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 79
        },
        {
          "name": "FactorModel",
          "module": "risk",
          "qualified": "quantvolt.risk.mc_var.FactorModel",
          "kind": "class",
          "signature": "FactorModel(market_data: MarketData, factors: tuple[FactorLabel, ...], sigma: npt.NDArray[np.float64], corr: npt.NDArray[np.float64])",
          "summary": "Base market state plus GBM dynamics over an ordered ``(commodity, period)`` grid.",
          "doc": "Base market state plus GBM dynamics over an ordered ``(commodity, period)`` grid.\n\nFields:\n    market_data: the current/base market state. Its ``forward_curves`` supply the\n        current forwards (``z0 = log F_0``) for every factor, and its\n        ``discount_curve`` / ``valuation_date`` provide the static revaluation context.\n    factors: ordered factor labels; strictly ascending by ``(commodity_id, period)``\n        (see the module docstring for the flattening convention). Factor ``i`` indexes\n        ``sigma[i]`` and row/column ``i`` of ``corr``.\n    sigma: per-factor instantaneous volatility (length ``D``); ``0`` marks an expired,\n        frozen factor (eq A.5). Deep numeric validation lives in ``build_covariance``.\n    corr: the ``(D, D)`` cross-factor correlation matrix ``R``.\n\n``sigma``/``corr`` are snapshot to contiguous ``float64`` at construction. Equality is\ndefined explicitly (``eq=False``) so the array fields compare by value to a single\n``bool`` rather than the element-wise array a generated ``__eq__`` would yield.",
          "methods": [
            {
              "name": "current_forwards",
              "signature": "current_forwards(self) -> npt.NDArray[np.float64]",
              "summary": "Current forward level ``F_0`` per factor, in factor order (length ``D``)."
            }
          ],
          "fields": [
            {
              "name": "market_data",
              "type": "MarketData",
              "default": null
            },
            {
              "name": "factors",
              "type": "tuple[FactorLabel, ...]",
              "default": null
            },
            {
              "name": "sigma",
              "type": "npt.NDArray[np.float64]",
              "default": null
            },
            {
              "name": "corr",
              "type": "npt.NDArray[np.float64]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/mc_var.py",
          "line": 146
        },
        {
          "name": "McVaRResult",
          "module": "risk",
          "qualified": "quantvolt.risk.mc_var.McVaRResult",
          "kind": "class",
          "signature": "McVaRResult(var_95: float, var_99: float, cvar_975: float, var_95_se: float, var_99_se: float, cvar_975_se: float, path_count: int, holding_period: float, seed: int)",
          "summary": "Full-revaluation Monte Carlo VaR outcome (Req 15.1, 15.4).",
          "doc": "Full-revaluation Monte Carlo VaR outcome (Req 15.1, 15.4).\n\n``var_95`` / ``var_99`` are the ``confidences`` percentiles (95th / 99th by default)\nof the loss distribution ``L = -ΔNPV``; ``cvar_975`` is the mean loss at or above the\n``cvar_confidence`` percentile (97.5th by default, inclusive tail, matching\n:class:`quantvolt.risk.engine.RiskEngine`). The field names are fixed regardless of\nthe levels supplied. Each carries a\nnonparametric bootstrap standard error (``*_se``). ``path_count`` is the number of\nsimulated paths the metrics are computed over, and ``holding_period`` / ``seed`` are\nechoed for reproducibility.",
          "methods": [],
          "fields": [
            {
              "name": "var_95",
              "type": "float",
              "default": null
            },
            {
              "name": "var_99",
              "type": "float",
              "default": null
            },
            {
              "name": "cvar_975",
              "type": "float",
              "default": null
            },
            {
              "name": "var_95_se",
              "type": "float",
              "default": null
            },
            {
              "name": "var_99_se",
              "type": "float",
              "default": null
            },
            {
              "name": "cvar_975_se",
              "type": "float",
              "default": null
            },
            {
              "name": "path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "holding_period",
              "type": "float",
              "default": null
            },
            {
              "name": "seed",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/mc_var.py",
          "line": 252
        },
        {
          "name": "ParametricVaRResult",
          "module": "risk",
          "qualified": "quantvolt.risk.parametric_var.ParametricVaRResult",
          "kind": "class",
          "signature": "ParametricVaRResult(confidences: tuple[float, ...], var_values: tuple[float, ...], method: str, pnl_mean: float, pnl_variance: float, pnl_skewness: float, n_factors: int)",
          "summary": "Outcome of a parametric-VaR computation (Req 14.1/14.2).",
          "doc": "Outcome of a parametric-VaR computation (Req 14.1/14.2).\n\n``confidences`` and ``var_values`` are parallel tuples in the caller's request order;\n``var_values[i]`` is the VaR (a loss, in the currency units of ``deltas``) at\n``confidences[i]`` — use :meth:`var_at` for a keyed lookup. ``method`` records the\nquantile method (``\"delta\"`` for :func:`parametric_var`; the delta-gamma method name,\ne.g. ``\"cornish_fisher\"``, for :func:`delta_gamma_var`) so the reported figure is\nself-documenting (Req 14.2).\n\n``pnl_mean`` / ``pnl_variance`` / ``pnl_skewness`` are the first three moments of the\nP&L (``ΔP``, not the loss) distribution under the model: for the linear case they are\n``(0.0, δᵀΣδ, 0.0)``; for the delta-gamma case they are the quadratic-form cumulants\n``(κ₁, κ₂, κ₃/κ₂^1.5)``. ``n_factors`` is the number of risk factors.",
          "methods": [
            {
              "name": "var_at",
              "signature": "var_at(self, confidence: float) -> float",
              "summary": "VaR at a computed ``confidence``; raise if that level was not requested."
            }
          ],
          "fields": [
            {
              "name": "confidences",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "var_values",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "method",
              "type": "str",
              "default": null
            },
            {
              "name": "pnl_mean",
              "type": "float",
              "default": null
            },
            {
              "name": "pnl_variance",
              "type": "float",
              "default": null
            },
            {
              "name": "pnl_skewness",
              "type": "float",
              "default": null
            },
            {
              "name": "n_factors",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/parametric_var.py",
          "line": 93
        },
        {
          "name": "RiskEngine",
          "module": "risk",
          "qualified": "quantvolt.risk.engine.RiskEngine",
          "kind": "class",
          "signature": "RiskEngine(catalogue: ScenarioCatalogue | None=None)",
          "summary": "Portfolio risk metrics: VaR / CVaR, delta aggregation, stress scenarios (Req 9).",
          "doc": "Portfolio risk metrics: VaR / CVaR, delta aggregation, stress scenarios (Req 9).\n\nA configured service, not a Singleton: it holds the scenario catalogue used to\nresolve named scenarios and nothing else. All methods are pure with respect to\ntheir inputs.",
          "methods": [
            {
              "name": "compute_risk",
              "signature": "compute_risk(self, positions: list[PricedPosition], scenario_matrix: npt.NDArray[np.float64], timeout_seconds: float=60.0, *, confidences: Sequence[float]=DEFAULT_VAR_CONFIDENCES, cvar_confidence: float=DEFAULT_CVAR_CONFIDENCE) -> RiskResult",
              "summary": "Historical-simulation VaR (95/99 by default) and CVaR (97.5 by default)."
            },
            {
              "name": "aggregate_delta",
              "signature": "aggregate_delta(self, positions: list[PricedPosition]) -> DeltaMatrix",
              "summary": "Net delta by commodity x delivery period (Req 9.3)."
            },
            {
              "name": "apply_scenario",
              "signature": "apply_scenario(self, positions: list[PricedPosition], scenario: str | ScenarioShock) -> ScenarioResult",
              "summary": "Apply a named or user-defined stress scenario to the book (Req 9.4)."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 176
        },
        {
          "name": "RiskResult",
          "module": "risk",
          "qualified": "quantvolt.risk.engine.RiskResult",
          "kind": "class",
          "signature": "RiskResult(var_95: float, var_99: float, cvar_975: float, delta_matrix: DeltaMatrix, exclusion_report: list[ExcludedPosition], partial: bool, unprocessed_indices: list[int])",
          "summary": "Portfolio tail-risk output containing VaR and CVaR levels, scenario P&L observations, factor ordering and excluded-position diagnostics..",
          "doc": "Portfolio tail-risk output containing VaR and CVaR levels, scenario P&L observations, factor ordering and excluded-position diagnostics.",
          "methods": [],
          "fields": [
            {
              "name": "var_95",
              "type": "float",
              "default": null
            },
            {
              "name": "var_99",
              "type": "float",
              "default": null
            },
            {
              "name": "cvar_975",
              "type": "float",
              "default": null
            },
            {
              "name": "delta_matrix",
              "type": "DeltaMatrix",
              "default": null
            },
            {
              "name": "exclusion_report",
              "type": "list[ExcludedPosition]",
              "default": null
            },
            {
              "name": "partial",
              "type": "bool",
              "default": null
            },
            {
              "name": "unprocessed_indices",
              "type": "list[int]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 85
        },
        {
          "name": "ScenarioCatalogue",
          "module": "risk",
          "qualified": "quantvolt.risk.scenarios.ScenarioCatalogue",
          "kind": "class",
          "signature": "ScenarioCatalogue(extra_scenarios: dict[str, ScenarioShock] | None=None)",
          "summary": "Resolves scenario names to :class:`ScenarioShock` vectors (Req 9.4, 9.7).",
          "doc": "Resolves scenario names to :class:`ScenarioShock` vectors (Req 9.4, 9.7).\n\nA config-holding service over :data:`BUILT_IN_SCENARIOS` — not a Singleton.\nCaller-supplied ``extra_scenarios`` are merged OVER the built-ins (caller\nwins on name collision); neither input dict is mutated, and later mutation\nof ``extra_scenarios`` by the caller does not affect the catalogue.",
          "methods": [
            {
              "name": "get",
              "signature": "get(self, name: str) -> ScenarioShock",
              "summary": "Return the scenario registered under ``name``."
            },
            {
              "name": "names",
              "signature": "names(self) -> list[str]",
              "summary": "All available scenario names, sorted."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/scenarios.py",
          "line": 183
        },
        {
          "name": "ScenarioResult",
          "module": "risk",
          "qualified": "quantvolt.risk.engine.ScenarioResult",
          "kind": "class",
          "signature": "ScenarioResult(scenario_name: str, total_pnl: float, per_position_pnl: tuple[float, ...])",
          "summary": "Outcome of applying one stress scenario to a book (Req 9.4).",
          "doc": "Outcome of applying one stress scenario to a book (Req 9.4).\n\n``per_position_pnl`` is ordered exactly like the input position list, and\n``total_pnl`` is the plain left-to-right sum of those contributions, so\n``total_pnl == sum(per_position_pnl)`` holds exactly (Property 23).",
          "methods": [],
          "fields": [
            {
              "name": "scenario_name",
              "type": "str",
              "default": null
            },
            {
              "name": "total_pnl",
              "type": "float",
              "default": null
            },
            {
              "name": "per_position_pnl",
              "type": "tuple[float, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/engine.py",
          "line": 96
        },
        {
          "name": "ScenarioShock",
          "module": "risk",
          "qualified": "quantvolt.risk.scenarios.ScenarioShock",
          "kind": "class",
          "signature": "ScenarioShock(name: str, shocks: dict[ShockKey, float])",
          "summary": "A named vector of relative price shocks.",
          "doc": "A named vector of relative price shocks.\n\n``shocks`` maps ``(commodity_id, period)`` to a relative fractional shock\n(see the module docstring for both conventions). ``period=None`` applies\nthe shock commodity-wide across all delivery periods.",
          "methods": [],
          "fields": [
            {
              "name": "name",
              "type": "str",
              "default": null
            },
            {
              "name": "shocks",
              "type": "dict[ShockKey, float]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/scenarios.py",
          "line": 46
        },
        {
          "name": "TaggedDrift",
          "module": "risk",
          "qualified": "quantvolt.risk.mc_var.TaggedDrift",
          "kind": "class",
          "signature": "TaggedDrift(values: npt.NDArray[np.float64], kind: DriftKind)",
          "summary": "A drift vector tagged with the probability measure it belongs to.",
          "doc": "A drift vector tagged with the probability measure it belongs to.\n\nUsed for the required ``physical_drift`` argument: routing the tag through\n:func:`~quantvolt.numerics.risk_adjustment.require_physical_drift` rejects a\n``RISK_NEUTRAL`` drift before any simulation runs (Req 15.2 / Property 59). ``values``\nare per-factor physical log-drift *rates* (per unit of the holding period's time\nunit). Snapshot to contiguous ``float64``; equality is value-based (``eq=False``).",
          "methods": [],
          "fields": [
            {
              "name": "values",
              "type": "npt.NDArray[np.float64]",
              "default": null
            },
            {
              "name": "kind",
              "type": "DriftKind",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/risk/mc_var.py",
          "line": 224
        },
        {
          "name": "aggregate_delta",
          "module": "risk",
          "qualified": "quantvolt.risk.aggregation.aggregate_delta",
          "kind": "function",
          "signature": "aggregate_delta(positions: list[PricedPosition]) -> DeltaMatrix",
          "summary": "Net position-level delta by commodity (rows) x delivery period (cols) — Property 22.",
          "doc": "Net position-level delta by commodity (rows) x delivery period (cols) — Property 22.\n\nEach cell is the sum of that ``(commodity, period)`` delta across all positions.\nThe grid is the sorted union of the key sets of every position's ``delta`` mapping:\npositions with an empty ``delta`` contribute nothing, and an empty ``positions``\nlist yields the empty matrix (no rows, no columns). Inputs are never mutated —\ntotals accumulate in a fresh dict and the result is built from new tuples.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/aggregation.py",
          "line": 59
        },
        {
          "name": "cash_flow_at_risk",
          "module": "risk",
          "qualified": "quantvolt.risk.cfar.cash_flow_at_risk",
          "kind": "function",
          "signature": "cash_flow_at_risk(cashflow_model: CashFlowModel, scenarios: Sequence[Scenario], horizon: int, seed: int, consistency: Mapping[str, str] | None=None, *, confidence_level: float=0.95) -> CFaRResult",
          "summary": "Compute CFaR plus summary statistics over a factor scenario set (Req 16).",
          "doc": "Compute CFaR plus summary statistics over a factor scenario set (Req 16).\n\nFor every scenario the pure ``cashflow_model`` is called exactly once, its returned\nper-period vector is validated to have length ``horizon`` and aggregated (summed)\ninto one realised aggregate cash flow. Across scenarios this forms the distribution\nof aggregated cash flow, from which the mean, the percentiles, and the\nshortfall-below-expected at ``confidence_level`` are computed. See the module\ndocstring for the request surface, the exact CFaR definition, and the sign\nconvention.\n\nArgs:\n    cashflow_model: Pure callable mapping one scenario to a 1-D per-period\n        cash-flow vector of length ``horizon``. Called once per scenario; never\n        mutated.\n    scenarios: Non-empty exhaustive factor scenario set (market + operational\n        factors keyed by name).\n    horizon: Number of periods, ``>= 1``.\n    seed: Reproducibility seed, echoed on the result (Req 16.3).\n    consistency: Optional market/operational consistency metadata, carried through\n        to the result verbatim (Req 16.2).\n    confidence_level: Confidence level for the ``cfar_95`` / ``p5`` shortfall\n        measure; defaults to ``0.95``, reproducing the 5th-percentile shortfall\n        documented in the module docstring. Must be in ``[0, 1]``. ``p50`` / ``p95``\n        always report the 50th / 95th percentiles regardless of this parameter.\n\nReturns:\n    A :class:`CFaRResult`.\n\nRaises:\n    ValidationError: If ``horizon < 1``; if ``scenarios`` is empty; if\n        ``confidence_level`` is outside ``[0, 1]``; or if the model returns, for\n        any scenario, a vector whose shape is not ``(horizon,)`` — the message\n        names the returned shape, the horizon, and the scenario index (Req 16.4).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/cfar.py",
          "line": 120
        },
        {
          "name": "compare_cashflow_strategies",
          "module": "risk",
          "qualified": "quantvolt.risk.cashflow_metrics.compare_cashflow_strategies",
          "kind": "function",
          "signature": "compare_cashflow_strategies(data: pl.DataFrame, cashflow_columns: Mapping[str, str], *, benchmark: str, confidence_level: float=0.95) -> CashflowStrategyComparison",
          "summary": "Compare caller-supplied periodic cash flows using one consistent convention.",
          "doc": "Compare caller-supplied periodic cash flows using one consistent convention.\n\nCFaR is ``max(mean - lower percentile, 0)``. Positive reduction fields mean\nlower risk than the benchmark; positive total difference means more cash flow.\nNo annualization is performed because the function does not guess observation\nfrequency.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/cashflow_metrics.py",
          "line": 51
        },
        {
          "name": "credit_var",
          "module": "risk",
          "qualified": "quantvolt.risk.credit_var.credit_var",
          "kind": "function",
          "signature": "credit_var(positions: Sequence[PricedPosition], transition: Mapping[str, npt.ArrayLike], exposures: Mapping[str, float] | None=None, recovery: float | Mapping[str, float]=0.4, seed: int=0, *, path_count: int=100000, asset_correlation: float=0.2, confidences: Sequence[float]=DEFAULT_CONFIDENCES) -> CreditVaRResult",
          "summary": "Compute Credit VaR and expected credit loss over the priced book (Req 17).",
          "doc": "Compute Credit VaR and expected credit loss over the priced book (Req 17).\n\nCounterparty-less positions are set aside as credit-risk-free; every credit-bearing\ncounterparty's default event is drawn jointly with a shared systematic market factor\nvia a one-factor Gaussian copula, and the path loss is the sum of ``LGD * EAD`` over\nthat path's defaulted counterparties. See the module docstring for the request surface,\nthe copula construction, the EAD/LGD conventions, the sign convention, and the\nlimitations.\n\nArgs:\n    positions: The priced book; each position's counterparty is read from its\n        instrument (``ForwardContract.counterparty``; missing / ``None`` -> risk-free).\n    transition: Per-counterparty one-period migration row (last state = default;\n        entries in ``[0, 1]``; sums to ``1`` within ``1e-9``).\n    exposures: Optional per-counterparty exposure; where absent, exposure is the\n        net (summed) NPV of that counterparty's positions. EAD is floored at zero.\n    recovery: Recovery rate in ``[0, 1]``, scalar or per-counterparty. ``LGD = 1 - r``.\n    seed: RNG seed (``>= 0``); results are reproducible under it (Req 17.3).\n    path_count: Number of Monte Carlo paths (``>= 1``).\n    asset_correlation: Copula systematic-factor loading ``rho in [0, 1]``.\n    confidences: The two credit-VaR confidence levels (fractions in ``(0, 1)``,\n        matching :mod:`quantvolt.risk.parametric_var`'s convention) reported as\n        ``credit_var_95`` / ``credit_var_99``; defaults to ``(0.95, 0.99)``.\n\nReturns:\n    A :class:`CreditVaRResult`.\n\nRaises:\n    ValidationError: If ``seed < 0``, ``path_count < 1``, ``asset_correlation`` or any\n        recovery is outside ``[0, 1]``, a transition row has an out-of-range probability\n        or does not sum to 1 within ``1e-9`` (message names the counterparty), a\n        supplied exposure is non-finite, a credit-bearing counterparty has no\n        transition row (message names the counterparty) (Req 17.4), or\n        ``confidences`` does not contain exactly 2 strictly ascending levels in\n        ``(0, 1)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/credit_var.py",
          "line": 207
        },
        {
          "name": "delta_gamma_var",
          "module": "risk",
          "qualified": "quantvolt.risk.parametric_var.delta_gamma_var",
          "kind": "function",
          "signature": "delta_gamma_var(deltas: NDArray[np.float64], gamma: NDArray[np.float64], cov: NDArray[np.float64], confidences: Sequence[float]=DEFAULT_CONFIDENCES, method: str='cornish_fisher', *, psd_tol: float=_PSD_TOL, symmetry_rtol: float=_SYMMETRY_RTOL) -> ParametricVaRResult",
          "summary": "Second-order (delta-gamma) parametric VaR via moment matching (Req 14.2, Property 48).",
          "doc": "Second-order (delta-gamma) parametric VaR via moment matching (Req 14.2, Property 48).\n\nThe quadratic P&L ``ΔP = δᵀΔf + ½·Δfᵀ Γ Δf`` with ``Δf ~ N(0, Σ)`` has, writing\n``Θ = Γ Σ``, the standard delta-gamma-normal cumulants (Britten-Jones & Schaefer,\n\"Non-linear Value-at-Risk\", 1999, eqs. 6-8; Zangari, RiskMetrics Monitor 1996;\nverified here against Monte Carlo):\n\n* ``κ₁ = ½·tr(Θ)`` — mean;\n* ``κ₂ = δᵀΣδ + ½·tr(Θ²)`` — variance;\n* ``κ₃ = 3·δᵀΣΓΣδ + tr(Θ³)`` — third cumulant.\n\nThe loss ``L = -ΔP`` has mean ``-κ₁``, standard deviation ``√κ₂`` and skewness\n``-κ₃/κ₂^1.5``; its ``c``-quantile is ``VaR_c = -κ₁ + √κ₂ · w(z_c, -γ₁)`` where ``w``\nis the third-order Cornish-Fisher map ``w = z + (z²-1)/6·γ₁`` (dispatched by\n``method``). With ``Γ = 0`` all higher cumulants vanish and this collapses **exactly**\nto :func:`parametric_var` (Property 48).\n\nSign sanity: a long-gamma book (``Γ`` positive definite) has ``κ₁ > 0`` (the quadratic\nterm only ever adds to P&L) and positive P&L skewness, so both the mean shift and the\nskewness correction *reduce* VaR relative to the delta-only figure — the expected\ndirection.\n\nArgs:\n    deltas: Portfolio delta by risk factor, a 1-D vector of length ``n``.\n    gamma: The ``n x n`` gamma matrix ``Γ``; must be square, symmetric, and conformable\n        with ``deltas`` — but need **not** be PSD (a book may be long some gammas and\n        short others).\n    cov: The ``n x n`` factor covariance ``Σ`` (validated square/symmetric/PSD).\n    confidences: Confidence levels; defaults to ``(0.95, 0.99)``.\n    method: Delta-gamma quantile method; defaults to ``\"cornish_fisher\"``. Must be a\n        registered method (currently only ``\"cornish_fisher\"``).\n    psd_tol: Absolute tolerance on the smallest eigenvalue of ``Σ`` used by the PSD\n        check; defaults to ``1e-8``.\n    symmetry_rtol: Relative tolerance (against the matrix scale) for the symmetry\n        checks on ``Σ`` and ``Γ``; defaults to ``1e-8``.\n\nReturns:\n    A :class:`ParametricVaRResult` carrying ``method`` and the P&L cumulant moments\n    ``(κ₁, κ₂, κ₃/κ₂^1.5)``.\n\nRaises:\n    ValidationError: on any dimension, symmetry, PSD, confidence, or unknown-``method``\n        violation, naming the offending quantity.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/parametric_var.py",
          "line": 292
        },
        {
          "name": "ewma_covariance",
          "module": "risk",
          "qualified": "quantvolt.risk.covariance.ewma_covariance",
          "kind": "function",
          "signature": "ewma_covariance(returns: NDArray[np.float64], lam: float=0.94, *, psd_tol: float=_PSD_TOL) -> NDArray[np.float64]",
          "summary": "RiskMetrics exponentially-weighted covariance forecast (eq. U10.1).",
          "doc": "RiskMetrics exponentially-weighted covariance forecast (eq. U10.1).\n\nIterates the recursion ``Σ_t = λ·Σ_{t-1} + (1-λ)·r_t·r_tᵀ`` over the rows of\n``returns`` (oldest first) and returns the final ``Σ`` — the one-step-ahead covariance\nforecast. Following the RiskMetrics convention the returns are treated as zero-mean\ninnovations (no centring). The recursion is **initialised from the first observation's\nouter product** ``Σ_0 = r_0·r_0ᵀ``; because each update is a convex combination of\nrank-1 PSD outer products, every ``Σ_t`` — and hence the result — is PSD by\nconstruction.\n\nArgs:\n    returns: ``(n_obs, n_assets)`` array of periodic returns, oldest row first.\n    lam: RiskMetrics decay factor in the open interval ``(0, 1)``; the default\n        ``0.94`` is the RiskMetrics daily value.\n    psd_tol: Absolute tolerance on the smallest eigenvalue of the resulting\n        covariance forecast when asserting positive semidefiniteness; defaults to\n        ``1e-8``.\n\nReturns:\n    The symmetric PSD ``(n_assets, n_assets)`` covariance forecast.\n\nRaises:\n    ValidationError: if ``lam`` is not in ``(0, 1)``; if ``returns`` is not a 2-D\n        array with at least 2 observations and 1 asset; if it holds non-finite\n        values; or if the result fails the PSD check within ``psd_tol``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/covariance.py",
          "line": 112
        },
        {
          "name": "garch11_covariance",
          "module": "risk",
          "qualified": "quantvolt.risk.covariance.garch11_covariance",
          "kind": "function",
          "signature": "garch11_covariance(returns: NDArray[np.float64], *, psd_tol: float=_PSD_TOL) -> NDArray[np.float64]",
          "summary": "Diagonal GARCH(1,1) + constant-conditional-correlation covariance forecast.",
          "doc": "Diagonal GARCH(1,1) + constant-conditional-correlation covariance forecast.\n\nEstimator (Bollerslev 1990 CCC-GARCH), per the design §2.16 (eqs. U10.2-U10.3):\n\n1. **De-mean** each asset column to obtain innovations ``u_j``.\n2. **Fit** a univariate GARCH(1,1)\n   ``h_{j,t} = omega_j + alpha_j·u²_{j,t-1} + beta_j·h_{j,t-1}`` to each column by\n   Gaussian MLE (:func:`_fit_garch11`), enforcing ``omega_j > 0``, ``alpha_j >= 0``,\n   ``beta_j >= 0``, ``alpha_j + beta_j < 1``.\n3. **Standardise** the residuals ``e_{j,t} = u_{j,t} / √h_{j,t}`` and take their sample\n   correlation matrix ``R`` as the constant conditional correlation.\n4. **Forecast** each asset's one-step-ahead conditional variance\n   ``h_{j,T+1} = omega_j + alpha_j·u²_{j,T} + beta_j·h_{j,T}`` and assemble\n   ``Sigma = D·R·D`` with ``D = diag(√h_{j,T+1})``.\n\n``Σ`` is PSD because ``R`` (a sample correlation matrix) is PSD and ``D·R·D`` is a\ncongruence transform with a real diagonal.\n\nArgs:\n    returns: ``(n_obs, n_assets)`` array of periodic returns, oldest row first. A long\n        series is needed for a meaningful fit.\n    psd_tol: Absolute tolerance on the smallest eigenvalue of the resulting\n        covariance forecast when asserting positive semidefiniteness; defaults to\n        ``1e-8``.\n\nReturns:\n    The symmetric PSD ``(n_assets, n_assets)`` covariance forecast.\n\nRaises:\n    ValidationError: if ``returns`` is not a valid finite 2-D array with at least 2\n        observations; if any per-asset series is degenerate; if any GARCH fit fails\n        to converge or violates ``omega > 0, alpha >= 0, beta >= 0, alpha + beta < 1``\n        (the message names the offending asset and constraint); or if the result\n        fails the PSD check within ``psd_tol``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/covariance.py",
          "line": 234
        },
        {
          "name": "monte_carlo_var",
          "module": "risk",
          "qualified": "quantvolt.risk.mc_var.monte_carlo_var",
          "kind": "function",
          "signature": "monte_carlo_var(positions: Sequence[Position], factor_model: FactorModel, physical_drift: TaggedDrift, holding_period: float, path_count: int, seed: int, *, confidences: Sequence[float]=DEFAULT_CONFIDENCES, cvar_confidence: float=DEFAULT_CVAR_CONFIDENCE, antithetic: bool=_ANTITHETIC, bootstrap_replicates: int=_BOOTSTRAP_REPLICATES, min_path_count: int=_MIN_PATH_COUNT) -> McVaRResult",
          "summary": "Full-revaluation Monte Carlo VaR/CVaR over a holding period (Req 15).",
          "doc": "Full-revaluation Monte Carlo VaR/CVaR over a holding period (Req 15).\n\nSee the module docstring for the request surface, the factor flattening convention,\nthe simulation/revaluation mechanics, the sign convention, and the standard-error\nestimator. In short: simulate correlated GBM forward scenarios to the horizon under\nthe physical drift, fully revalue the book on each path, and take loss quantiles.\n\nArgs:\n    positions: raw held instruments (repriced from their definition each path).\n    factor_model: base market state + GBM dynamics over the factor grid.\n    physical_drift: required, measure-tagged per-factor log-drift rates.\n    holding_period: risk horizon (> 0), in ``sigma``'s time unit.\n    path_count: simulated paths (``>= min_path_count``).\n    seed: reproducibility seed.\n    confidences: The two VaR confidence levels (fractions in ``(0, 1)``, matching\n        :mod:`quantvolt.risk.parametric_var`'s convention) reported as ``var_95`` /\n        ``var_99``; defaults to ``(0.95, 0.99)``.\n    cvar_confidence: The CVaR confidence level (a fraction in ``(0, 1)``) reported\n        as ``cvar_975``; defaults to ``0.975``.\n    antithetic: Whether the simulation uses antithetic-variate path pairing;\n        defaults to ``False`` (iid paths). The bootstrap SE estimator resamples\n        individual paths when ``False`` and whole ``(+eps, -eps)`` pairs when\n        ``True``, so both modes yield consistent SE estimates — see the module\n        docstring.\n    bootstrap_replicates: Number of bootstrap resamples for the quantile standard\n        errors; defaults to ``500``. Must be an integer ``>= 2`` (a sample standard\n        deviation across replicates needs at least 2 of them).\n    min_path_count: Minimum accepted ``path_count`` (Req 15.5); defaults to\n        ``1000``.\n\nReturns:\n    A :class:`McVaRResult` with VaR/CVaR at the requested confidence levels\n    (reported as ``var_95``/``var_99``/``cvar_975`` regardless of the levels used)\n    and bootstrap SEs.\n\nRaises:\n    ValidationError: if ``path_count < min_path_count`` (raised *before* simulating,\n        Req 15.5); if ``holding_period <= 0``; if ``physical_drift`` is not tagged\n        physical (Req 15.2); if ``physical_drift.values`` does not match the factor\n        count; if any current forward is not strictly positive (GBM requires\n        ``F_0 > 0``); if ``confidences`` does not contain exactly 2 strictly\n        ascending levels in ``(0, 1)``; if ``cvar_confidence`` is not in ``(0, 1)``;\n        if ``bootstrap_replicates`` is not an integer ``>= 2`` (a standard deviation\n        needs at least 2 replicates); or if ``min_path_count`` is not ``>= 1``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/mc_var.py",
          "line": 362
        },
        {
          "name": "nearest_psd",
          "module": "risk",
          "qualified": "quantvolt.risk.covariance.nearest_psd",
          "kind": "function",
          "signature": "nearest_psd(matrix: NDArray[np.float64]) -> NDArray[np.float64]",
          "summary": "Return the nearest symmetric positive-semidefinite matrix (Higham-style repair).",
          "doc": "Return the nearest symmetric positive-semidefinite matrix (Higham-style repair).\n\nSymmetrises the input, then projects onto the PSD cone by clipping negative\neigenvalues to zero and reconstructing ``V·max(Λ, 0)·Vᵀ``. For a symmetric input this\nis exactly the nearest PSD matrix in the Frobenius norm (Higham 1988). Use it to repair\na covariance/correlation matrix that a Caller knows to be only marginally indefinite\n(e.g. from finite-precision estimation); it is *not* applied automatically by the\nestimators, which raise instead so the Caller stays in control.\n\nRaises:\n    ValidationError: if ``matrix`` is not a square 2-D array.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/covariance.py",
          "line": 89
        },
        {
          "name": "parametric_var",
          "module": "risk",
          "qualified": "quantvolt.risk.parametric_var.parametric_var",
          "kind": "function",
          "signature": "parametric_var(deltas: NDArray[np.float64], cov: NDArray[np.float64], confidences: Sequence[float]=DEFAULT_CONFIDENCES, *, psd_tol: float=_PSD_TOL, symmetry_rtol: float=_SYMMETRY_RTOL) -> ParametricVaRResult",
          "summary": "First-order (delta) parametric VaR ``VaR_c = z_c·√(δᵀΣδ)`` (Req 14.1, Property 47).",
          "doc": "First-order (delta) parametric VaR ``VaR_c = z_c·√(δᵀΣδ)`` (Req 14.1, Property 47).\n\nValidates all inputs before any arithmetic (Req 14.4): ``deltas`` is a finite 1-D\nvector; ``cov`` is square, symmetric (within ``symmetry_rtol``), conformable with\n``deltas`` (a mismatch names both dimensions), and positive semidefinite within\n``psd_tol`` (a violation names the offending smallest eigenvalue). See the module\ndocstring for the sign convention, the z-score policy, and the fast PSD test.\n\nArgs:\n    deltas: Portfolio delta by risk factor, a 1-D vector of length ``n``.\n    cov: The ``n x n`` factor covariance forecast ``Σ`` over the loss horizon\n        (e.g. from :mod:`quantvolt.risk.covariance`).\n    confidences: Confidence levels; defaults to ``(0.95, 0.99)``. Each must be in\n        ``(0, 1)``; ``0.95`` / ``0.99`` use the mandated constants ``1.645`` / ``2.326``.\n    psd_tol: Absolute tolerance on the smallest eigenvalue of ``Σ`` used by the PSD\n        check; defaults to ``1e-8`` (the design's documented tolerance, Req 14.4).\n    symmetry_rtol: Relative tolerance (against the matrix scale) for the symmetry\n        check on ``Σ``; defaults to ``1e-8``.\n\nReturns:\n    A :class:`ParametricVaRResult` with ``method=\"delta\"`` and a zero-mean,\n    zero-skew P&L description (``pnl_variance = δᵀΣδ``).\n\nRaises:\n    ValidationError: on any dimension, symmetry, PSD, or confidence violation, naming\n        the offending quantity.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/parametric_var.py",
          "line": 235
        },
        {
          "name": "BUILT_IN_SCENARIOS",
          "module": "risk",
          "qualified": "quantvolt.risk.scenarios.BUILT_IN_SCENARIOS",
          "kind": "constant",
          "signature": "BUILT_IN_SCENARIOS",
          "summary": "Registry of named historical and hypothetical energy stress scenarios supplied with RiskEngine..",
          "doc": "Registry of named historical and hypothetical energy stress scenarios supplied with RiskEngine.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/risk/scenarios.py",
          "line": 1
        }
      ]
    },
    {
      "name": "hedging",
      "qualified": "quantvolt.hedging",
      "description": "Variance-minimizing, cross-commodity and PPA hedging.",
      "symbols": [
        {
          "name": "PpaNominationCandidate",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationCandidate",
          "kind": "class",
          "signature": "PpaNominationCandidate(contracted_mwh: float, mean_cashflow: float, lower_percentile_cashflow: float, cfar: float, objective_value: float)",
          "summary": "Diagnostics for one candidate constant interval nomination.",
          "doc": "Diagnostics for one candidate constant interval nomination.",
          "methods": [],
          "fields": [
            {
              "name": "contracted_mwh",
              "type": "float",
              "default": null
            },
            {
              "name": "mean_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "lower_percentile_cashflow",
              "type": "float",
              "default": null
            },
            {
              "name": "cfar",
              "type": "float",
              "default": null
            },
            {
              "name": "objective_value",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 50
        },
        {
          "name": "PpaNominationColumns",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationColumns",
          "kind": "class",
          "signature": "PpaNominationColumns(interval_start_utc: str = 'interval_start_utc', interval_end_utc: str = 'interval_end_utc', metered_generation_mwh: str = 'metered_generation_mwh', shortfall_price_per_mwh: str = 'shortfall_price_per_mwh', excess_price_per_mwh: str = 'excess_price_per_mwh')",
          "summary": "Map caller-owned calibration columns to nomination inputs.",
          "doc": "Map caller-owned calibration columns to nomination inputs.",
          "methods": [],
          "fields": [
            {
              "name": "interval_start_utc",
              "type": "str",
              "default": "'interval_start_utc'"
            },
            {
              "name": "interval_end_utc",
              "type": "str",
              "default": "'interval_end_utc'"
            },
            {
              "name": "metered_generation_mwh",
              "type": "str",
              "default": "'metered_generation_mwh'"
            },
            {
              "name": "shortfall_price_per_mwh",
              "type": "str",
              "default": "'shortfall_price_per_mwh'"
            },
            {
              "name": "excess_price_per_mwh",
              "type": "str",
              "default": "'excess_price_per_mwh'"
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 32
        },
        {
          "name": "PpaNominationFit",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationFit",
          "kind": "class",
          "signature": "PpaNominationFit(contract_id: str, calibration_end_utc: datetime, calibration_rows: int, delivery_interval_minutes: int, capacity_mwh_per_interval: float, selected_mwh_per_interval: float, objective: PpaNominationObjective, risk_aversion: float, confidence_level: float, candidates: tuple[PpaNominationCandidate, ...])",
          "summary": "Fitted nomination plus its immutable calibration audit trail.",
          "doc": "Fitted nomination plus its immutable calibration audit trail.",
          "methods": [],
          "fields": [
            {
              "name": "contract_id",
              "type": "str",
              "default": null
            },
            {
              "name": "calibration_end_utc",
              "type": "datetime",
              "default": null
            },
            {
              "name": "calibration_rows",
              "type": "int",
              "default": null
            },
            {
              "name": "delivery_interval_minutes",
              "type": "int",
              "default": null
            },
            {
              "name": "capacity_mwh_per_interval",
              "type": "float",
              "default": null
            },
            {
              "name": "selected_mwh_per_interval",
              "type": "float",
              "default": null
            },
            {
              "name": "objective",
              "type": "PpaNominationObjective",
              "default": null
            },
            {
              "name": "risk_aversion",
              "type": "float",
              "default": null
            },
            {
              "name": "confidence_level",
              "type": "float",
              "default": null
            },
            {
              "name": "candidates",
              "type": "tuple[PpaNominationCandidate, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 61
        },
        {
          "name": "PpaNominationObjective",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_nomination.PpaNominationObjective",
          "kind": "class",
          "signature": "PpaNominationObjective()",
          "summary": "Transparent in-sample criterion used to select the nomination.",
          "doc": "Transparent in-sample criterion used to select the nomination.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "MAX_MEAN_CASHFLOW",
              "value": "'max_mean_cashflow'"
            },
            {
              "name": "MAX_MEAN_MINUS_CFAR",
              "value": "'max_mean_minus_cfar'"
            }
          ],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 24
        },
        {
          "name": "PpaWalkForwardResult",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_walk_forward.PpaWalkForwardResult",
          "kind": "class",
          "signature": "PpaWalkForwardResult(fits: tuple[PpaNominationFit, ...], evaluation: pl.DataFrame)",
          "summary": "All fitted windows and the row-level out-of-sample nomination trace.",
          "doc": "All fitted windows and the row-level out-of-sample nomination trace.",
          "methods": [],
          "fields": [
            {
              "name": "fits",
              "type": "tuple[PpaNominationFit, ...]",
              "default": null
            },
            {
              "name": "evaluation",
              "type": "pl.DataFrame",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_walk_forward.py",
          "line": 24
        },
        {
          "name": "apply_ppa_nomination",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_nomination.apply_ppa_nomination",
          "kind": "function",
          "signature": "apply_ppa_nomination(fit: PpaNominationFit, evaluation_data: pl.DataFrame, *, interval_start_column: str='interval_start_utc', interval_end_column: str='interval_end_utc', output_column: str='contracted_mwh') -> pl.DataFrame",
          "summary": "Add the fitted volume to strictly out-of-sample caller observations.",
          "doc": "Add the fitted volume to strictly out-of-sample caller observations.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 204
        },
        {
          "name": "calibrate_ppa_nomination",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_nomination.calibrate_ppa_nomination",
          "kind": "function",
          "signature": "calibrate_ppa_nomination(contract: PpaContract, calibration_data: pl.DataFrame, *, calibration_end_utc: datetime, capacity_mwh_per_interval: float, columns: PpaNominationColumns | None=None, objective: PpaNominationObjective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR, risk_aversion: float=1.0, confidence_level: float=0.95, grid_steps: int=100) -> PpaNominationFit",
          "summary": "Fit a constant baseload nomination using calibration observations only.",
          "doc": "Fit a constant baseload nomination using calibration observations only.\n\nCandidate physical cash flow is\n``q*fixed + max(g-q,0)*excess - max(q-g,0)*shortfall``.\nCFaR follows the package convention ``max(mean - lower_percentile, 0)``.\nTies resolve to the smaller nomination, avoiding accidental over-contracting.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_nomination.py",
          "line": 122
        },
        {
          "name": "decomposed_delta",
          "module": "hedging",
          "qualified": "quantvolt.hedging.variance_min.decomposed_delta",
          "kind": "function",
          "signature": "decomposed_delta(value_fn: Callable[[float, float], float], forward: float, basis_ra_expectation: float, bump: float, *, risk_adjustment: PriceOfRiskKind) -> float",
          "summary": "Incomplete-market delta ``∂Ṽ/∂F`` under a risk-adjusted basis expectation (eqs 10.15-10.18).",
          "doc": "Incomplete-market delta ``∂Ṽ/∂F`` under a risk-adjusted basis expectation (eqs 10.15-10.18).\n\nFor a non-linear structure whose payoff depends on a spot price decomposed\ninto a hedgeable component and an *uncorrelated* unhedgeable basis (eq 10.15),\nthe structure value is\n\n    ``Ṽ(F) = df · E*[ E^RA_ε[Payoff] ]``    (eq 10.16)\n\n-- a risk-neutral expectation over the hedgeable forward ``F`` of a\n*risk-adjusted* expectation over the basis ``ε``. Because the basis is\nindependent of ``F``, the local variance-minimizing hedge is simply\n\n    ``Δ̃_t = ∂Ṽ(F)/∂F``    (eq 10.17)\n\nwhich this function computes by central finite difference in ``F`` (via\n:func:`quantvolt.numerics.rootfind.finite_difference_bump`), holding the\nrisk-adjusted basis expectation fixed under the bump (it does not co-move with\n``F``, by eq 10.15).\n\n**The Caller supplies the value function and the basis summary.** ``value_fn``\ntakes ``(forward, basis_ra_expectation)`` and returns the scalar structure\nvalue ``Ṽ`` -- it closes over the payoff, discounting, and the risk-neutral\nexpectation over ``F``. ``basis_ra_expectation`` is the *already-computed*\nrisk-adjusted expectation of the unhedgeable basis (a scalar summary such as\nits risk-adjusted mean); passing the risk-adjusted expectation itself makes\nthe corporate risk adjustment explicit at the call site.\n\n**Divergence from the complete-market delta (Req 18.6 / eq 10.18).** The\ncomplete-market delta ``Δ_t = ∂V/∂F`` (eq 10.14) is taken on the fully\nhedgeable value ``V = df · E*[Payoff]`` (eq 10.13), which knows nothing of the\nbasis. The forms of eqs 10.14 and 10.17 are *identical*, but their values\ndiffer because eqs 10.13 and 10.16 differ whenever the basis has a non-zero\nmean or variance -- hence in general ``Δ̃_t ≠ Δ_t`` (eq 10.18, Property 55).\nOnly for a *zero* basis (zero mean and variance) does ``E^RA_ε[Payoff] =\nPayoff``, so ``Ṽ = V`` and the two deltas coincide. For a *linear* product the\nbasis enters ``Ṽ`` only as an additive constant in ``F``, so it drops out of\nthe derivative and ``Δ̃_t`` reduces to ``rho·sigma_t/sigma_h`` regardless of the risk\nadjustment (Example 10.2, eq 10.25); for a non-linear product the basis\ncouples to ``F`` and the delta genuinely shifts.\n\n**Explicit corporate risk adjustment (Req 18.6).** ``risk_adjustment`` is a\nrequired keyword routed through the Task 63\n:class:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind` vocabulary. Only\n:attr:`PriceOfRiskKind.CORPORATE` is accepted: the unhedgeable basis is not\nspanned by traded instruments, so a market/risk-neutral price of risk cannot\nbe implied for it, and this function never silently assumes risk-neutrality.\n\nArgs:\n    value_fn: Callable ``(forward, basis_ra_expectation) -> Ṽ`` returning the\n        risk-adjusted structure value (eq 10.16).\n    forward: The hedgeable forward price ``F`` at which the delta is evaluated.\n    basis_ra_expectation: The risk-adjusted expectation of the unhedgeable\n        basis, held fixed while ``forward`` is bumped.\n    bump: Strictly positive central-difference step in ``forward``.\n    risk_adjustment: Provenance of the basis risk adjustment; must be\n        :attr:`PriceOfRiskKind.CORPORATE` (Req 18.6).\n\nReturns:\n    The incomplete-market delta ``∂Ṽ/∂F`` (eq 10.17).\n\nRaises:\n    ValidationError: If ``value_fn`` is not callable, ``bump`` is not strictly\n        positive, or ``risk_adjustment`` is not\n        :attr:`PriceOfRiskKind.CORPORATE`.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/variance_min.py",
          "line": 158
        },
        {
          "name": "global_mean_variance",
          "module": "hedging",
          "qualified": "quantvolt.hedging.mean_variance.global_mean_variance",
          "kind": "function",
          "signature": "global_mean_variance(cov_target_hedge: NDArray[np.float64], cov_hedge: NDArray[np.float64], *, condition_limit: float=_CONDITION_LIMIT) -> NDArray[np.float64]",
          "summary": "Global (total-horizon) mean-variance hedge ratios (Req 18.4, Property 56).",
          "doc": "Global (total-horizon) mean-variance hedge ratios (Req 18.4, Property 56).\n\nMinimises the *total* terminal variance ``Var(ΔV_total - gᵀ·ΔH)`` jointly over\nthe whole strategy vector ``g ∈ ℝⁿ`` (``ΔV_total = Σ_t ΔV_t``). The normal\nequations are\n\n    ``C·g = b``,   with ``b_t = Cov(ΔH_t, ΔV_total) = Σ_s M[s, t]``,\n\ni.e. ``b`` is the column-sum vector of ``cov_target_hedge`` and\n``g_global = C⁻¹·b``. Unlike the local hedge, the global optimum exists only\nwhen ``C`` is invertible; the system is solved with :func:`numpy.linalg.solve`\nafter an explicit conditioning check, and a singular / ill-conditioned ``C``\nraises rather than returning a pseudo-inverse solution.\n\nCoincides with :func:`local_mean_variance` exactly when both ``M`` and ``C``\nare diagonal (uncorrelated increments across periods) -- e.g. under\nindependent increments / a martingale hedge instrument, and in particular for\na linear product with constant correlation and volatilities, where the common\nratio is ``rho·sigma_target/sigma_hedge`` (eq 10.22, Property 56).\n\nArgs:\n    cov_target_hedge: The ``(n, n)`` cross-covariance matrix ``M`` with\n        ``M[s, t] = Cov(ΔV_s, ΔH_t)``. Its column sums form the right-hand\n        side ``b_t = Cov(ΔH_t, ΔV_total)``; it need not be symmetric.\n    cov_hedge: The ``(n, n)`` auto-covariance matrix ``C`` of the hedge\n        increments, ``C[s, t] = Cov(ΔH_s, ΔH_t)``. Must be square, symmetric,\n        finite and non-singular.\n    condition_limit: Upper bound on the 2-norm condition number of ``C`` before\n        it is treated as numerically singular; defaults to ``1/eps``, the point\n        past which the linear solve loses all significant digits.\n\nReturns:\n    The ``(n,)`` ``float64`` array of global (total-horizon) hedge ratios.\n\nRaises:\n    ValidationError: If the inputs are not conformable non-empty square finite\n        matrices, ``cov_hedge`` is not symmetric, ``condition_limit`` is not\n        strictly positive, or ``cov_hedge`` is singular / ill-conditioned (the\n        joint variance-minimising strategy then does not exist).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/mean_variance.py",
          "line": 172
        },
        {
          "name": "hybrid_deltas",
          "module": "hedging",
          "qualified": "quantvolt.hedging.hybrid.hybrid_deltas",
          "kind": "function",
          "signature": "hybrid_deltas(stack_fn: StackFn, drivers: Mapping[str, float], bump: float) -> dict[str, float]",
          "summary": "Chain-rule deltas of a hybrid power-price model to each tradable driver (eq 10.26, Req 18.5).",
          "doc": "Chain-rule deltas of a hybrid power-price model to each tradable driver (eq 10.26, Req 18.5).\n\nThe hybrid price is ``p = s^bid(drivers) + epsilon`` (eq 10.26). The local\nvariance-minimizing hedge to a tradable driver ``k`` is the partial derivative\nof the deterministic stack with respect to that driver, ``partial p / partial\ndriver_k`` (the residual ``epsilon`` is, by construction, independent of the\ndrivers and drops out of the derivative). Applying this to each driver gives,\nby the chain rule / Ito's lemma (source, after eq 10.28), the delta vector.\n\nWhen ``drivers`` are the tradable variables themselves -- or the tradable\nproxies through which the fundamental drivers are expressed (eqs 10.27-10.28,\ne.g. gas via its ``BOM`` / option contracts) -- each returned partial is\ndirectly the hedge ratio to that tradable. Each partial is one link of the\nchain rule; the total first-order price move is their sum,\n``dp = sum_k (partial p / partial driver_k) d(driver_k)`` (Property 57,\n\"chain-rule deltas sum consistently across drivers\").\n\nEach partial is estimated by a central finite difference (via\n:func:`quantvolt.numerics.rootfind.finite_difference_bump`): each driver is\nbumped by ``+/- bump`` while the others are held fixed. Choose ``bump`` small\nrelative to the driver's scale but large enough to avoid round-off; for an\nexactly linear stack the central difference is exact.\n\nThe caller's ``drivers`` mapping is never mutated: a fresh mapping is built for\nevery bumped evaluation.\n\nArgs:\n    stack_fn: The deterministic stack ``s^bid`` -- a pure callable mapping a\n        driver mapping ``{name: value}`` to the scalar power price (eq 10.26).\n    drivers: The current driver values ``{name: value}`` at which the deltas\n        are evaluated. Must be non-empty.\n    bump: Strictly positive central-difference step applied to each driver.\n\nReturns:\n    A ``dict`` with one entry per driver name, mapping it to\n    ``partial p / partial driver`` at ``drivers``.\n\nRaises:\n    ValidationError: If ``stack_fn`` is not callable, ``bump`` is not strictly\n        positive, or ``drivers`` is empty.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/hybrid.py",
          "line": 63
        },
        {
          "name": "linear_cross_hedge",
          "module": "hedging",
          "qualified": "quantvolt.hedging.variance_min.linear_cross_hedge",
          "kind": "function",
          "signature": "linear_cross_hedge(rho: float, sigma_target: float, sigma_hedge: float) -> float",
          "summary": "Linear two-asset cross-commodity hedge ratio ``rho·sigma_t/sigma_h`` (eq 10.22, Req 18.2).",
          "doc": "Linear two-asset cross-commodity hedge ratio ``rho·sigma_t/sigma_h`` (eq 10.22, Req 18.2).\n\nThe optimal local variance-minimizing hedge of one forward (the target, with\nvolatility ``sigma_t``) with another (the hedge instrument, volatility ``sigma_h``)\nwhen the two follow jointly arithmetic Brownian motions with correlation\n``rho`` (eq 10.21). For a linear product the hedge is constant in ``rho``, ``sigma_t``\nand ``sigma_h``. This is the one-instrument special case of\n:func:`variance_min_hedge`: with ``Σ_hh = [[sigma_h²]]`` and\n``Σ_ht = [rho·sigma_t·sigma_h]``, ``Σ_hh⁻¹ Σ_ht = rho·sigma_t/sigma_h``.\n\nArgs:\n    rho: Correlation between the target and hedge returns, in ``(-1, 1)``.\n    sigma_target: Volatility ``sigma_t`` of the target, strictly positive.\n    sigma_hedge: Volatility ``sigma_h`` of the hedge instrument, strictly positive.\n\nReturns:\n    The hedge ratio ``rho·sigma_t/sigma_h``.\n\nRaises:\n    ValidationError: If ``rho`` is not in ``(-1, 1)`` or either volatility is\n        not strictly positive.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/variance_min.py",
          "line": 129
        },
        {
          "name": "local_mean_variance",
          "module": "hedging",
          "qualified": "quantvolt.hedging.mean_variance.local_mean_variance",
          "kind": "function",
          "signature": "local_mean_variance(cov_target_hedge: NDArray[np.float64], cov_hedge: NDArray[np.float64]) -> NDArray[np.float64]",
          "summary": "Local (one-step) mean-variance hedge ratios -- the default (Req 18.4, Property 56).",
          "doc": "Local (one-step) mean-variance hedge ratios -- the default (Req 18.4, Property 56).\n\nMinimises each rebalancing period's one-step variance ``Var(ΔV_t - g·ΔH_t)``\nseparately (Föllmer-Sondermann, 1986), returning the per-period projection\ncoefficients\n\n    ``g_local_t = Cov(ΔV_t, ΔH_t) / Var(ΔH_t) = M[t, t] / C[t, t]``.\n\nOnly the *diagonals* of the two input matrices are used, so the local hedge\n**always exists** whenever every per-period hedge variance is strictly\npositive -- it requires no matrix inversion and is indifferent to cross-period\ncorrelations or to ``cov_hedge`` being singular. This is why it is the default\nof the two mean-variance formulations.\n\nArgs:\n    cov_target_hedge: The ``(n, n)`` cross-covariance matrix ``M`` with\n        ``M[s, t] = Cov(ΔV_s, ΔH_t)``. Only the diagonal ``M[t, t] =\n        Cov(ΔV_t, ΔH_t)`` is read; it need not be symmetric.\n    cov_hedge: The ``(n, n)`` auto-covariance matrix ``C`` of the hedge\n        increments, ``C[s, t] = Cov(ΔH_s, ΔH_t)``. Must be square, symmetric\n        and finite; only the diagonal ``C[t, t] = Var(ΔH_t)`` is read, and\n        each diagonal entry must be strictly positive.\n\nReturns:\n    The ``(n,)`` ``float64`` array of per-period local hedge ratios.\n\nRaises:\n    ValidationError: If the inputs are not conformable non-empty square finite\n        matrices, ``cov_hedge`` is not symmetric, or any per-period hedge\n        variance ``Var(ΔH_t) = cov_hedge[t, t]`` is not strictly positive.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/mean_variance.py",
          "line": 127
        },
        {
          "name": "residual_variance",
          "module": "hedging",
          "qualified": "quantvolt.hedging.hybrid.residual_variance",
          "kind": "function",
          "signature": "residual_variance(stack_fn: StackFn, drivers: Mapping[str, Sequence[float]], realized: Sequence[float]) -> float",
          "summary": "Hybrid hedge-quality metric: variance of the residual ``epsilon_t`` (eq 10.26, Req 18.5).",
          "doc": "Hybrid hedge-quality metric: variance of the residual ``epsilon_t`` (eq 10.26, Req 18.5).\n\nFrom ``p_t = s^bid(drivers_t) + epsilon_t`` (eq 10.26) the residual is\n``epsilon_t = p_t - s^bid(drivers_t)``. This applies the deterministic stack to\neach observation of the driver series, subtracts it from the realized power\nprice, and returns the (unbiased, ``ddof=1``) sample variance of the residual.\n\n**Smaller is better** (Property 57). The residual is the unhedgeable part of\nthe price; a representation that explains more of the price leaves a smaller\nresidual, and \"the smaller its variance, the better the representation\"\n(source text after eq 10.28). A zero residual variance means the price is\nfully spanned by the drivers and is completely hedgeable. This metric ranks\ncompeting hybrid representations of the *same* realized price series; pass the\nsame ``drivers`` / ``realized`` with different ``stack_fn`` transformations to\ncompare them.\n\nThis is a physical-measure (``P``) descriptive statistic and carries no risk\nadjustment (the risk-adjusted valuation of the unhedgeable residual lives in\n:func:`quantvolt.hedging.variance_min.decomposed_delta`, Req 18.6).\n\nThe caller's inputs are never mutated.\n\nArgs:\n    stack_fn: The deterministic stack ``s^bid`` -- a pure callable mapping a\n        per-observation driver mapping ``{name: value}`` to the scalar power\n        price (eq 10.26).\n    drivers: The driver series, column-oriented as ``{name: series}`` (the same\n        driver keys ``stack_fn`` reads, each carrying one value per\n        observation). Must be non-empty, and every series must have the same\n        length as ``realized``.\n    realized: The observed power prices ``p_t``, in observation order. At least\n        two observations are required.\n\nReturns:\n    The sample variance (``ddof=1``) of the residual\n    ``epsilon_t = realized_t - s^bid(drivers_t)``.\n\nRaises:\n    ValidationError: If ``stack_fn`` is not callable, ``drivers`` is empty,\n        ``realized`` is not 1-D, or any driver series length does not match\n        ``realized``.\n    InsufficientDataError: If fewer than two observations are supplied (the\n        ``n >= 2`` constraint required to estimate a sample variance).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/hybrid.py",
          "line": 125
        },
        {
          "name": "variance_min_hedge",
          "module": "hedging",
          "qualified": "quantvolt.hedging.variance_min.variance_min_hedge",
          "kind": "function",
          "signature": "variance_min_hedge(sigma_hh: NDArray[np.float64], sigma_ht: NDArray[np.float64], *, condition_limit: float=_CONDITION_LIMIT) -> NDArray[np.float64]",
          "summary": "Variance-minimizing hedge ratios ``h* = Σ_hh⁻¹ Σ_ht`` (Req 18.1, Property 54).",
          "doc": "Variance-minimizing hedge ratios ``h* = Σ_hh⁻¹ Σ_ht`` (Req 18.1, Property 54).\n\nGiven a target exposure and ``n`` hedge instruments described by their return\ncovariance with the target (``Σ_ht``) and with each other (``Σ_hh``), returns\nthe ratios ``h*`` that minimise the local variance of the hedged position.\n``h*`` solves the normal-equation system ``Σ_hh·h* = Σ_ht``.\n\nThe system is solved with :func:`numpy.linalg.solve` after an explicit\nconditioning check: a singular or ill-conditioned ``Σ_hh`` raises rather than\nsilently returning a pseudo-inverse solution (a pseudo-inverse would hide the\nfact that the hedge instruments are collinear and the ratios are not\nidentified).\n\nArgs:\n    sigma_hh: The ``(n, n)`` covariance matrix of the hedge instruments with\n        each other. Must be square, symmetric, finite and non-singular.\n    sigma_ht: The length-``n`` covariance vector of the hedge instruments with\n        the target exposure. Must be conformable with ``sigma_hh``.\n    condition_limit: Upper bound on the 2-norm condition number of ``sigma_hh``\n        before it is treated as numerically singular; defaults to ``1/eps``, the\n        point past which the linear solve loses all significant digits.\n\nReturns:\n    The ``(n,)`` ``float64`` array of variance-minimizing hedge ratios. For a\n    single instrument (``n == 1``) this collapses to\n    :func:`linear_cross_hedge`'s ``rho·sigma_t/sigma_h`` (Property 54).\n\nRaises:\n    ValidationError: If ``sigma_hh`` is not a non-empty square 2-D matrix, is\n        not symmetric, contains non-finite values, is singular or\n        ill-conditioned; if ``condition_limit`` is not strictly positive; or if\n        ``sigma_ht`` is not a finite 1-D vector conformable with ``sigma_hh``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/variance_min.py",
          "line": 50
        },
        {
          "name": "walk_forward_ppa_nomination",
          "module": "hedging",
          "qualified": "quantvolt.hedging.ppa_walk_forward.walk_forward_ppa_nomination",
          "kind": "function",
          "signature": "walk_forward_ppa_nomination(contract: PpaContract, data: pl.DataFrame, rebalance_utc: Sequence[datetime], *, evaluation_end_utc: datetime, capacity_mwh_per_interval: float, columns: PpaNominationColumns | None=None, lookback: timedelta | None=None, objective: PpaNominationObjective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR, risk_aversion: float=1.0, confidence_level: float=0.95, grid_steps: int=100) -> PpaWalkForwardResult",
          "summary": "Refit at each cutoff and apply only until the next cutoff.",
          "doc": "Refit at each cutoff and apply only until the next cutoff.\n\n``lookback=None`` uses an expanding window. A positive ``lookback`` uses a\nrolling window. Intervals crossing a rebalance boundary are rejected rather\nthan assigned partly in-sample and partly out-of-sample.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/hedging/ppa_walk_forward.py",
          "line": 34
        }
      ]
    },
    {
      "name": "assets",
      "qualified": "quantvolt.assets",
      "description": "Thermal dispatch, storage and long-dated asset valuation.",
      "symbols": [
        {
          "name": "BangBangHedgeWarning",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_approx.BangBangHedgeWarning",
          "kind": "class",
          "signature": "BangBangHedgeWarning()",
          "summary": "Advisory that bang-bang state aggregation biases hedges far more than values (Req 21.3).",
          "doc": "Advisory that bang-bang state aggregation biases hedges far more than values (Req 21.3).\n\nCollapsing the output grid to {0, c_max} pins the operating point to full load,\nso the plant value loses only the (often small) part-load optionality. The\n*sensitivities* — the deltas and critical-dispatch surfaces used to hedge — are\na different matter: they read the slope of value against price, and the\napproximation replaces the true, curved heat-rate response with a single kink\nat the on/off boundary. A hedge derived from a bang-bang model can therefore be\nbadly wrong even when the headline value looks reasonable. The approximation is\nnot rejected — for a sufficiently steep heat curve the value error is genuinely\nnegligible — but the caller is warned so the choice is deliberate.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 72
        },
        {
          "name": "BenchmarkResult",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.BenchmarkResult",
          "kind": "class",
          "signature": "BenchmarkResult(period: DeliveryPeriod, value: float, source: ValuationSource)",
          "summary": "A long-dated valuation with its provenance tag carried prominently.",
          "doc": "A long-dated valuation with its provenance tag carried prominently.\n\n``source`` is the load-bearing field: :attr:`ValuationSource.FORWARD` means the\nvalue is the liquid forward price (Req 23.1); :attr:`ValuationSource.PROJECTED`\nmeans it is a projected-spot value (Req 23.2) that carries much higher risk and\nfor which short-horizon VaR is inapplicable.",
          "methods": [
            {
              "name": "is_projected",
              "signature": "is_projected(self) -> bool",
              "summary": "``True`` iff this value came from projected spot rather than the forward curve."
            },
            {
              "name": "var_applicable",
              "signature": "var_applicable(self) -> bool",
              "summary": "``True`` iff short-horizon VaR is meaningful for a position at this benchmark."
            }
          ],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "value",
              "type": "float",
              "default": null
            },
            {
              "name": "source",
              "type": "ValuationSource",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 112
        },
        {
          "name": "CorporatePremium",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.CorporatePremium",
          "kind": "class",
          "signature": "CorporatePremium(premium: float, kind: PriceOfRiskKind)",
          "summary": "A projected-spot risk premium with an explicit price-of-risk provenance.",
          "doc": "A projected-spot risk premium with an explicit price-of-risk provenance.\n\n``kind`` has no default: the caller must state the provenance explicitly, so the\npremium is never applied silently (Req 19.3). :func:`valuation_benchmark` accepts\nonly a :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`\npremium; a market-tagged one reflects traded quotes, not the firm's own long-dated\nrisk appetite, and cannot stand in for it.\n\nAttributes:\n    premium: The additive corporate risk premium in the commodity's price unit,\n        applied as ``projected_spot = spot_model(period) + premium`` (Req 23.2).\n        May be negative.\n    kind: Provenance of the premium; must be\n        :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`.",
          "methods": [],
          "fields": [
            {
              "name": "premium",
              "type": "float",
              "default": null
            },
            {
              "name": "kind",
              "type": "PriceOfRiskKind",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 90
        },
        {
          "name": "DispatchDiagnostics",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.DispatchDiagnostics",
          "kind": "class",
          "signature": "DispatchDiagnostics(training_value: float, evaluation_standard_error: float, confidence_interval: tuple[float, float], training_path_count: int, evaluation_path_count: int, max_regression_condition: float)",
          "summary": "Sampling and regression evidence for an LSM dispatch value.",
          "doc": "Sampling and regression evidence for an LSM dispatch value.\n\nAttributes:\n    training_value: Mean realised value on the training paths (before the\n        independent policy-evaluation re-simulation).\n    evaluation_standard_error: Monte Carlo standard error of ``value`` (the\n        evaluation-path mean). Computed by :func:`_standard_error`, which accounts\n        for antithetic pairing when the evaluation paths use it (the default):\n        the estimator is ``std(pair_means, ddof=1) / sqrt(n_pairs)`` over the\n        antithetic pair means, not the naive iid formula over every path (which\n        would overstate the SE by ignoring the pairs' negative within-pair\n        correlation).\n    confidence_interval: Normal-approximation interval around ``value`` at\n        ``evaluation.confidence_level``, built from ``evaluation_standard_error``.\n    training_path_count: Number of training paths.\n    evaluation_path_count: Number of independent policy-evaluation paths.\n    max_regression_condition: Worst LSM regression design-matrix condition number\n        across periods (and, when a state's regression is masked to its finite\n        paths, across states within a period too).",
          "methods": [],
          "fields": [
            {
              "name": "training_value",
              "type": "float",
              "default": null
            },
            {
              "name": "evaluation_standard_error",
              "type": "float",
              "default": null
            },
            {
              "name": "confidence_interval",
              "type": "tuple[float, float]",
              "default": null
            },
            {
              "name": "training_path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "evaluation_path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "max_regression_condition",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 203
        },
        {
          "name": "DispatchFactorModel",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.DispatchFactorModel",
          "kind": "class",
          "signature": "DispatchFactorModel(log_forward0: Vector, drift: Vector, covariance: Vector, drift_kind: DriftKind, peak_kinds: tuple[PeakKind, ...], temperatures: tuple[float, ...], power_on_index: int = 0, power_off_index: int = 1, gas_index: int = 2, temperature_factor: PhysicalFactorMapping | None = None, availability_factor: PhysicalFactorMapping | None = None)",
          "summary": "Risk-adjusted factor dynamics driving stochastic dispatch (eqs. B.2-B.4).",
          "doc": "Risk-adjusted factor dynamics driving stochastic dispatch (eqs. B.2-B.4).\n\nThe stochastic factors are correlated log-forwards evolved by the Task-62\nengine ``ΔZ = mu + L·ε`` (GBM). At least a power and a gas coordinate are\nrequired; the on-peak / off-peak Markov split (eq. B.4) is expressed by naming\ntwo power coordinates (which may coincide) and a per-period peak label.\nTemperature is supplied deterministically (``temperatures``) -- it drives\n``HR`` and ``c_max`` but is not simulated here; a stochastic temperature factor\nwould simply be another simulated coordinate added to the basis.\n\nAttributes:\n    log_forward0: Initial log-forward vector ``z0 = log F(0, ·)`` over the\n        flattened factor state, dimension ``D`` (``>= 2``).\n    drift: Per-step drift ``mu`` (length ``D``). Must be the **risk-adjusted**\n        (pricing-measure) drift and is tagged by ``drift_kind``.\n    covariance: Per-step covariance ``C`` (``D x D``), assembled by\n        :func:`~quantvolt.numerics.monte_carlo.build_covariance`.\n    drift_kind: Measure tag on ``drift``; ``dispatch_value`` requires\n        :attr:`DriftKind.RISK_NEUTRAL` (Req 21.5).\n    peak_kinds: Per-period :class:`PeakKind` selecting the active power\n        coordinate; its length is the dispatch horizon ``H`` (``>= 1``).\n    temperatures: Per-period ambient temperature ``S_t`` (length ``H``).\n    power_on_index: Coordinate of ``z0`` used as the on-peak power spot.\n    power_off_index: Coordinate used as the off-peak power spot (may equal\n        ``power_on_index`` when the horizon is single-regime).\n    gas_index: Coordinate used as the gas / fuel price.",
          "methods": [
            {
              "name": "horizon",
              "signature": "horizon(self) -> int",
              "summary": "Number of dispatch periods ``H``."
            },
            {
              "name": "active_power_index",
              "signature": "active_power_index(self, period: int) -> int",
              "summary": "Power coordinate active in ``period`` (on-peak vs off-peak, eq. B.4)."
            },
            {
              "name": "simulate",
              "signature": "simulate(self, seed: int, path_count: int, *, antithetic: bool=True) -> Vector",
              "summary": "Simulate ``(n_paths, H + 1, D)`` log-forward paths (Task-62 engine)."
            }
          ],
          "fields": [
            {
              "name": "log_forward0",
              "type": "Vector",
              "default": null
            },
            {
              "name": "drift",
              "type": "Vector",
              "default": null
            },
            {
              "name": "covariance",
              "type": "Vector",
              "default": null
            },
            {
              "name": "drift_kind",
              "type": "DriftKind",
              "default": null
            },
            {
              "name": "peak_kinds",
              "type": "tuple[PeakKind, ...]",
              "default": null
            },
            {
              "name": "temperatures",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "power_on_index",
              "type": "int",
              "default": "0"
            },
            {
              "name": "power_off_index",
              "type": "int",
              "default": "1"
            },
            {
              "name": "gas_index",
              "type": "int",
              "default": "2"
            },
            {
              "name": "temperature_factor",
              "type": "PhysicalFactorMapping | None",
              "default": "None"
            },
            {
              "name": "availability_factor",
              "type": "PhysicalFactorMapping | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 234
        },
        {
          "name": "DispatchResult",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.DispatchResult",
          "kind": "class",
          "signature": "DispatchResult(value: float, start_surface: tuple[float, ...], shutdown_surface: tuple[float, ...], rampup_surface: tuple[float, ...], rampdown_surface: tuple[float, ...], diagnostics: DispatchDiagnostics | None = None)",
          "summary": "Stochastic dispatch value and the eq. B.5 critical exercise surfaces.",
          "doc": "Stochastic dispatch value and the eq. B.5 critical exercise surfaces.\n\nAttributes:\n    value: Risk-adjusted expected plant value (eq. B.3), a to-today NPV.\n    start_surface: Per-period critical spark spread above which starting up is\n        optimal (from a cold, restart-ready unit).\n    shutdown_surface: Per-period critical spark spread above which continuing\n        to run beats shutting down (a running unit shuts down below it).\n    rampup_surface: Per-period critical spark spread above which ramping up\n        from ``c_min`` beats holding.\n    rampdown_surface: Per-period critical spark spread above which holding the\n        top feasible level beats ramping down.\n\nEach surface is a length-``H`` tuple of EUR/MWh_power thresholds (measured at\n``c_min``); ``float('nan')`` marks a decision that does not arise in the period.",
          "methods": [],
          "fields": [
            {
              "name": "value",
              "type": "float",
              "default": null
            },
            {
              "name": "start_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "shutdown_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "rampup_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "rampdown_surface",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "diagnostics",
              "type": "DispatchDiagnostics | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 371
        },
        {
          "name": "DispatchSchedule",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_deterministic.DispatchSchedule",
          "kind": "class",
          "signature": "DispatchSchedule(outputs: tuple[float, ...], online: tuple[bool, ...], started: tuple[bool, ...], stopped: tuple[bool, ...], margins: tuple[float, ...], total_value: float)",
          "summary": "The perfect-foresight optimal dispatch (eq. B.1) over the horizon.",
          "doc": "The perfect-foresight optimal dispatch (eq. B.1) over the horizon.\n\nEvery tuple is in period order and has the horizon's length.\n\nAttributes:\n    outputs: Generation ``q_t`` per period (MW); ``0`` when not producing.\n    online: Whether the unit is producing in the period.\n    started: Whether a start-up is initiated in the period (start cost charged).\n    stopped: Whether the unit shuts down in the period.\n    margins: Per-period contribution to ``total_value`` (discounted cash\n        flow, net of any start cost); ``sum(margins) == total_value``.\n    total_value: The optimal total value — the perfect-foresight upper bound\n        (Property 62).",
          "methods": [],
          "fields": [
            {
              "name": "outputs",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "online",
              "type": "tuple[bool, ...]",
              "default": null
            },
            {
              "name": "started",
              "type": "tuple[bool, ...]",
              "default": null
            },
            {
              "name": "stopped",
              "type": "tuple[bool, ...]",
              "default": null
            },
            {
              "name": "margins",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "total_value",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_deterministic.py",
          "line": 103
        },
        {
          "name": "FactorTransform",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.FactorTransform",
          "kind": "class",
          "signature": "FactorTransform()",
          "summary": "Transform a simulated state coordinate into a physical observable.",
          "doc": "Transform a simulated state coordinate into a physical observable.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "IDENTITY",
              "value": "'identity'"
            },
            {
              "name": "EXP",
              "value": "'exp'"
            },
            {
              "name": "LOGISTIC",
              "value": "'logistic'"
            }
          ],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 139
        },
        {
          "name": "IntrinsicResult",
          "module": "assets",
          "qualified": "quantvolt.assets.storage.IntrinsicResult",
          "kind": "class",
          "signature": "IntrinsicResult(value: float, inventory: tuple[float, ...], injection: tuple[float, ...], withdrawal: tuple[float, ...], cashflow: tuple[float, ...])",
          "summary": "The optimal forward-locked injection/withdrawal schedule and its value (Req 22.1).",
          "doc": "The optimal forward-locked injection/withdrawal schedule and its value (Req 22.1).\n\nEvery per-period tuple is in delivery-period order with the horizon's length ``T``;\n``inventory`` has length ``T + 1`` (level entering each period, then the terminal level).\nBy construction the schedule respects the inventory bounds and ratchets at every step.\n\nAttributes:\n    value: The intrinsic value — the optimal forward-locked total cash flow (including\n        any terminal penalty).\n    inventory: Working-gas inventory path; ``inventory[0] == initial_inventory`` and\n        ``inventory[T] == terminal_inventory`` (hard target) or the optimal terminal level\n        (soft penalty).\n    injection: Working gas injected each period (``0`` when withdrawing/idle).\n    withdrawal: Working gas withdrawn each period (``0`` when injecting/idle).\n    cashflow: Market cash flow each period net of throughput and carry costs;\n        ``sum(cashflow) == value`` when the terminal condition is a hard target (its\n        penalty contribution is then zero), otherwise ``value == sum(cashflow) -\n        terminal_penalty · |inventory[T] - terminal_inventory|``.",
          "methods": [],
          "fields": [
            {
              "name": "value",
              "type": "float",
              "default": null
            },
            {
              "name": "inventory",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "injection",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "withdrawal",
              "type": "tuple[float, ...]",
              "default": null
            },
            {
              "name": "cashflow",
              "type": "tuple[float, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 169
        },
        {
          "name": "LowerBoundResult",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.LowerBoundResult",
          "kind": "class",
          "signature": "LowerBoundResult(period: DeliveryPeriod, lower_bound: float, furthest_forward_period: DeliveryPeriod)",
          "summary": "The furthest-forward lower bound for an illiquid later tenor (storable only).",
          "doc": "The furthest-forward lower bound for an illiquid later tenor (storable only).\n\nAttributes:\n    period: The illiquid tenor the bound is computed for.\n    lower_bound: The furthest visible forward price, used as a lower bound.\n    furthest_forward_period: The period the bound was read from (the curve's\n        furthest node), retained for auditability.",
          "methods": [],
          "fields": [
            {
              "name": "period",
              "type": "DeliveryPeriod",
              "default": null
            },
            {
              "name": "lower_bound",
              "type": "float",
              "default": null
            },
            {
              "name": "furthest_forward_period",
              "type": "DeliveryPeriod",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 154
        },
        {
          "name": "MonteCarloEvaluation",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.MonteCarloEvaluation",
          "kind": "class",
          "signature": "MonteCarloEvaluation(seed: int, path_count: int, confidence_level: float = 0.95)",
          "summary": "Independent policy-evaluation controls for dispatch LSM.",
          "doc": "Independent policy-evaluation controls for dispatch LSM.",
          "methods": [],
          "fields": [
            {
              "name": "seed",
              "type": "int",
              "default": null
            },
            {
              "name": "path_count",
              "type": "int",
              "default": null
            },
            {
              "name": "confidence_level",
              "type": "float",
              "default": "0.95"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 194
        },
        {
          "name": "PeakKind",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.PeakKind",
          "kind": "class",
          "signature": "PeakKind()",
          "summary": "Which power spot process is active in a period (the eq. B.4 Markov split).",
          "doc": "Which power spot process is active in a period (the eq. B.4 Markov split).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "ON_PEAK",
              "value": "'on_peak'"
            },
            {
              "name": "OFF_PEAK",
              "value": "'off_peak'"
            }
          ],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 132
        },
        {
          "name": "PhysicalFactorMapping",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.PhysicalFactorMapping",
          "kind": "class",
          "signature": "PhysicalFactorMapping(index: int, transform: FactorTransform = FactorTransform.IDENTITY, scale: float = 1.0, offset: float = 0.0)",
          "summary": "Map one simulated coordinate to temperature or availability.",
          "doc": "Map one simulated coordinate to temperature or availability.",
          "methods": [
            {
              "name": "values",
              "signature": "values(self, state: Vector) -> Vector",
              "summary": ""
            }
          ],
          "fields": [
            {
              "name": "index",
              "type": "int",
              "default": null
            },
            {
              "name": "transform",
              "type": "FactorTransform",
              "default": "FactorTransform.IDENTITY"
            },
            {
              "name": "scale",
              "type": "float",
              "default": "1.0"
            },
            {
              "name": "offset",
              "type": "float",
              "default": "0.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 167
        },
        {
          "name": "PlantModel",
          "module": "assets",
          "qualified": "quantvolt.assets.plant.PlantModel",
          "kind": "class",
          "signature": "PlantModel(heat_rate: HeatRateCurve, c_min: float, c_max: MaxCapacityCurve, variable_om_cost: float, start_costs: Mapping[StartState, StartCost], ramp_rate: float, d_min: int, d_shutdown: int, d_startup: int, outage_rate: float, hot_max_downtime: int, warm_max_downtime: int, representative_temperatures: tuple[float, ...] = ())",
          "summary": "Operating model of a dispatchable thermal unit (eq. B.1 parameters).",
          "doc": "Operating model of a dispatchable thermal unit (eq. B.1 parameters).\n\nDurations (``d_min``, ``d_shutdown``, ``d_startup``, the ``*_max_downtime``\nthresholds) are counted in dispatch periods — whatever resolution the\ncaller's price/temperature series use.\n\nAttributes:\n    heat_rate: Marginal heat-rate curve ``HR(q, temp)`` (MWh_fuel/MWh_power).\n    c_min: Minimum stable generation while online (MW), ``≥ 0``.\n    c_max: Temperature-dependent maximum capacity ``c_max(temp)`` (MW).\n    variable_om_cost: Variable O&M ``VOM`` per MWh, ``≥ 0``.\n    start_costs: One :class:`StartCost` per :class:`StartState`; all three\n        buckets required.\n    ramp_rate: Ramp rate ``RR`` (MW per period), ``> 0``.\n    d_min: Minimum-run duration (periods) once producing, ``≥ 0``.\n    d_shutdown: Minimum-down duration (periods) before a restart, ``≥ 0``.\n    d_startup: Start-up lag (periods) from the start decision to first\n        production, ``≥ 0``.\n    outage_rate: Forced-outage rate ``λ`` in ``[0, 1)`` (used by the\n        stochastic model; deterministic dispatch assumes full availability).\n    hot_max_downtime: Downtime ``≤`` this keys a ``HOT`` start.\n    warm_max_downtime: Downtime ``≤`` this (but ``>`` hot) keys a ``WARM``\n        start; anything longer keys a ``COLD`` start. Must be ``≥\n        hot_max_downtime``.\n    representative_temperatures: Optional smoke-test temperatures at which\n        ``c_max(temp) ≥ c_min`` and ``HR(c_min, temp) > 0`` are checked\n        eagerly. Empty by default (curve feasibility is then verified only\n        at dispatch time, against the temperatures actually supplied).",
          "methods": [
            {
              "name": "start_state_for_downtime",
              "signature": "start_state_for_downtime(self, downtime: int) -> StartState",
              "summary": "Classify a stopped unit's start-up state from elapsed downtime (periods)."
            },
            {
              "name": "start_cost",
              "signature": "start_cost(self, state: StartState, power_price: float, fuel_price: float) -> float",
              "summary": "Cash cost of one start in ``state``: ``SC + FSC·fuel + PSC·power`` (eq. B.1)."
            },
            {
              "name": "marginal_heat_rate",
              "signature": "marginal_heat_rate(self, output: float, temperature: float) -> float",
              "summary": "``HR(q, temp)`` — the plant's own curve, evaluated for the caller."
            },
            {
              "name": "max_capacity",
              "signature": "max_capacity(self, temperature: float) -> float",
              "summary": "``c_max(temp)`` — the plant's own temperature-dependent ceiling."
            }
          ],
          "fields": [
            {
              "name": "heat_rate",
              "type": "HeatRateCurve",
              "default": null
            },
            {
              "name": "c_min",
              "type": "float",
              "default": null
            },
            {
              "name": "c_max",
              "type": "MaxCapacityCurve",
              "default": null
            },
            {
              "name": "variable_om_cost",
              "type": "float",
              "default": null
            },
            {
              "name": "start_costs",
              "type": "Mapping[StartState, StartCost]",
              "default": null
            },
            {
              "name": "ramp_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "d_min",
              "type": "int",
              "default": null
            },
            {
              "name": "d_shutdown",
              "type": "int",
              "default": null
            },
            {
              "name": "d_startup",
              "type": "int",
              "default": null
            },
            {
              "name": "outage_rate",
              "type": "float",
              "default": null
            },
            {
              "name": "hot_max_downtime",
              "type": "int",
              "default": null
            },
            {
              "name": "warm_max_downtime",
              "type": "int",
              "default": null
            },
            {
              "name": "representative_temperatures",
              "type": "tuple[float, ...]",
              "default": "()"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/plant.py",
          "line": 86
        },
        {
          "name": "StartCost",
          "module": "assets",
          "qualified": "quantvolt.assets.plant.StartCost",
          "kind": "class",
          "signature": "StartCost(fixed: float, fuel: float, power: float)",
          "summary": "One start-up's cost components (the ``SC``/``FSC``/``PSC`` triple of eq. B.1).",
          "doc": "One start-up's cost components (the ``SC``/``FSC``/``PSC`` triple of eq. B.1).\n\n``fixed`` is the currency cost ``SC``; ``fuel`` is the fuel burned during the\nstart ``FSC`` (MWh_fuel, priced at that period's fuel price); ``power`` is the\ngrid power drawn during the start ``PSC`` (MWh, priced at that period's power\nprice). All three are non-negative — a start never earns money.",
          "methods": [],
          "fields": [
            {
              "name": "fixed",
              "type": "float",
              "default": null
            },
            {
              "name": "fuel",
              "type": "float",
              "default": null
            },
            {
              "name": "power",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/plant.py",
          "line": 66
        },
        {
          "name": "StartState",
          "module": "assets",
          "qualified": "quantvolt.assets.plant.StartState",
          "kind": "class",
          "signature": "StartState()",
          "summary": "Thermal state of a stopped unit, keying the start-up cost (eq. B.1).",
          "doc": "Thermal state of a stopped unit, keying the start-up cost (eq. B.1).\n\n``HOT`` follows a short shutdown (the boiler is still warm; cheapest start),\n``COLD`` a long one (most expensive), ``WARM`` in between. The mapping from\nelapsed downtime to a state is :meth:`PlantModel.start_state_for_downtime`.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "COLD",
              "value": "'cold'"
            },
            {
              "name": "WARM",
              "value": "'warm'"
            },
            {
              "name": "HOT",
              "value": "'hot'"
            }
          ],
          "source": "src/quantvolt/assets/plant.py",
          "line": 52
        },
        {
          "name": "StorageFactorModel",
          "module": "assets",
          "qualified": "quantvolt.assets.storage.StorageFactorModel",
          "kind": "class",
          "signature": "StorageFactorModel(volatility: float, dt: float, path_count: int = 4000)",
          "summary": "Single-factor forward-consistent spot model for the extrinsic (LSM) leg (Req 20.5, 22.2).",
          "doc": "Single-factor forward-consistent spot model for the extrinsic (LSM) leg (Req 20.5, 22.2).\n\nA documented one-factor reduction of the correlated forward engine\n(:func:`quantvolt.numerics.monte_carlo.simulate_correlated_forwards`): a single Brownian\nlog-factor ``X`` drives the whole curve multiplicatively. The period-``t`` spot price on a\npath is ``F(0, t) · exp(X_t)`` where ``X`` is simulated as GBM with per-step variance\n``volatility**2 · dt`` under the risk-neutral drift ``-½·volatility**2·dt`` that makes\n``exp(X)`` a unit martingale. Consequences that the valuation relies on:\n\n* ``X_0 = 0`` deterministically, so the period-0 spot equals ``F(0, 0)`` on every path\n  (today's prompt price is known);\n* ``E[spot_t] = F(0, t)`` — the forward is the risk-neutral spot mean, so the deterministic\n  intrinsic schedule earns exactly the intrinsic value in expectation, which is what\n  guarantees ``extrinsic >= 0`` (Property 64).\n\nThe model is *structured to admit* mean-reverting/OU dynamics without touching the\nvaluation (only the simulated factor changes), per Req 20.5; GBM is the shipped default.\n\nAttributes:\n    volatility: Annualised log-volatility ``sigma`` of the driving factor (``> 0``).\n    dt: Step length in years between consecutive delivery periods (``> 0``).\n    path_count: Number of Monte Carlo paths (``>= 1``); antithetic pairing is used, so an\n        odd count rounds up.",
          "methods": [],
          "fields": [
            {
              "name": "volatility",
              "type": "float",
              "default": null
            },
            {
              "name": "dt",
              "type": "float",
              "default": null
            },
            {
              "name": "path_count",
              "type": "int",
              "default": "4000"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 198
        },
        {
          "name": "StorageModel",
          "module": "assets",
          "qualified": "quantvolt.assets.storage.StorageModel",
          "kind": "class",
          "signature": "StorageModel(min_inventory: float, max_inventory: float, initial_inventory: float, terminal_inventory: float, injection_rate: RateCurve, withdrawal_rate: RateCurve, injection_cost: float = 0.0, withdrawal_cost: float = 0.0, injection_loss: float = 0.0, withdrawal_loss: float = 0.0, carry_cost: float = 0.0, terminal_penalty: float | None = None)",
          "summary": "Physical + commercial parameters of a gas store (Req 22.1, 22.3).",
          "doc": "Physical + commercial parameters of a gas store (Req 22.1, 22.3).\n\nInventory bounds are time-invariant scalars — the lightest faithful representation;\ntime-varying bounds would be a strictly heavier model with no bearing on the Task-75\nproperties and are deferred until a requirement needs them. Ratchets carry the only\nstate-dependence that matters here, as callables of the current fill level.\n\nAll consistency constraints are validated eagerly in :meth:`__post_init__` (rate-curve\nnon-negativity, which cannot be checked over all inventories for an opaque callable, is\nchecked at every grid level when a valuation runs). Inconsistent bounds raise a\n:class:`~quantvolt.exceptions.ValidationError` naming the offending fields (Req 22.3).\n\nAttributes:\n    min_inventory: Minimum working-gas inventory (volume).\n    max_inventory: Maximum working-gas inventory (volume); must be ``>= min_inventory``.\n    initial_inventory: Inventory entering the horizon; must lie in the bounds and on the\n        grid.\n    terminal_inventory: Target inventory at the horizon end; must lie in the bounds and\n        on the grid.\n    injection_rate: Ratchet ``injection_rate(inventory) -> max working-gas injected this\n        period`` (``>= 0``).\n    withdrawal_rate: Ratchet ``withdrawal_rate(inventory) -> max working-gas withdrawn\n        this period`` (``>= 0``).\n    injection_cost: Variable cost per unit working gas injected (``>= 0``).\n    withdrawal_cost: Variable cost per unit working gas withdrawn (``>= 0``).\n    injection_loss: Fuel-in-kind fraction burned on injection, in ``[0, 1)``.\n    withdrawal_loss: Fuel-in-kind fraction burned on withdrawal, in ``[0, 1)``.\n    carry_cost: Carry/financing cost per unit inventory held per period (``>= 0``).\n    terminal_penalty: If ``None`` the terminal inventory is a hard constraint; otherwise a\n        per-unit penalty (``>= 0``) on the terminal deviation from ``terminal_inventory``.",
          "methods": [
            {
              "name": "working_capacity",
              "signature": "working_capacity(self) -> float",
              "summary": "The full working-gas volume ``max_inventory - min_inventory``."
            }
          ],
          "fields": [
            {
              "name": "min_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "max_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "initial_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "terminal_inventory",
              "type": "float",
              "default": null
            },
            {
              "name": "injection_rate",
              "type": "RateCurve",
              "default": null
            },
            {
              "name": "withdrawal_rate",
              "type": "RateCurve",
              "default": null
            },
            {
              "name": "injection_cost",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "withdrawal_cost",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "injection_loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "withdrawal_loss",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "carry_cost",
              "type": "float",
              "default": "0.0"
            },
            {
              "name": "terminal_penalty",
              "type": "float | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 88
        },
        {
          "name": "StorageValueResult",
          "module": "assets",
          "qualified": "quantvolt.assets.storage.StorageValueResult",
          "kind": "class",
          "signature": "StorageValueResult(total: float, intrinsic: float, extrinsic: float, standard_error: float)",
          "summary": "Total, intrinsic and extrinsic storage value with the MC standard error (Req 22.2).",
          "doc": "Total, intrinsic and extrinsic storage value with the MC standard error (Req 22.2).\n\n``total == intrinsic + extrinsic`` by construction (``total`` is anchored on the exact\nintrinsic value plus the control-variate extrinsic estimate). ``extrinsic`` is\ntheoretically non-negative (Property 64); it is reported honestly rather than clamped, and\n``standard_error`` — the Monte Carlo standard error of the extrinsic estimate — is the\nnatural yardstick for the ``extrinsic >= -epsilon`` tolerance floor (a few standard errors)\nwithin which a small negative sampling value is acceptable.\n\nAttributes:\n    total: The total (intrinsic + extrinsic) value; ``intrinsic + extrinsic``.\n    intrinsic: The forward-locked intrinsic value (see :func:`storage_intrinsic`).\n    extrinsic: The re-optimisation (time) value — the control-variate mean of the adaptive\n        minus fixed-schedule pathwise values; equals ``total - intrinsic``.\n    standard_error: Monte Carlo standard error of the ``extrinsic`` estimate, computed\n        by :func:`_standard_error` — pair-mean-aware when the simulated paths use\n        antithetic variates (the default), rather than the naive iid formula over\n        every path (which overstates the SE by ignoring the antithetic pairs'\n        negative within-pair correlation).",
          "methods": [],
          "fields": [
            {
              "name": "total",
              "type": "float",
              "default": null
            },
            {
              "name": "intrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "extrinsic",
              "type": "float",
              "default": null
            },
            {
              "name": "standard_error",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 236
        },
        {
          "name": "ValuationSource",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.ValuationSource",
          "kind": "class",
          "signature": "ValuationSource()",
          "summary": "Provenance of a long-dated valuation; the tag that separates the two regimes.",
          "doc": "Provenance of a long-dated valuation; the tag that separates the two regimes.\n\nThe string values double as the ``Position.tags`` markers a caller propagates so\nthat :func:`var_applicability_guard` (and any risk code) can tell a projected\nvalue apart from a forward-based one.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "FORWARD",
              "value": "'forward'"
            },
            {
              "name": "PROJECTED",
              "value": "'projected'"
            }
          ],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 77
        },
        {
          "name": "VarApplicabilityVerdict",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.VarApplicabilityVerdict",
          "kind": "class",
          "signature": "VarApplicabilityVerdict(applicable: bool, reason: str)",
          "summary": "Whether short-horizon VaR is applicable to a position, with the reason.",
          "doc": "Whether short-horizon VaR is applicable to a position, with the reason.\n\nA frozen verdict an MC-VaR / parametric-VaR caller can consult without this module\nreaching into the risk engines. ``applicable`` is ``False`` for projected-spot\npositions (Req 23.3); ``reason`` states why in human-readable form.",
          "methods": [],
          "fields": [
            {
              "name": "applicable",
              "type": "bool",
              "default": null
            },
            {
              "name": "reason",
              "type": "str",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 141
        },
        {
          "name": "bang_bang",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_approx.bang_bang",
          "kind": "function",
          "signature": "bang_bang(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Bang-bang state aggregation: run at full load or off, {0, c_max} (Req 21.3).",
          "doc": "Bang-bang state aggregation: run at full load or off, {0, c_max} (Req 21.3).\n\nCollapses the online output grid to a single full-load level so the unit is\neither off or running at ``c_max`` — the state aggregation Appendix B recommends\nfor a *sufficiently steep* heat-rate curve, where the optimal load is (almost)\nalways a corner. Implemented by solving the deterministic DP on a derived plant\nwhose ``c_min`` and ``c_max`` are both pinned to that full-load level; every\nother operating characteristic (heat-rate curve, start costs, ramp, durations)\nis unchanged. The input plant is **not** mutated — a new :class:`PlantModel` is\nderived.\n\nFull-load level. With a constant capacity the pinned level *is* ``c_max``. With a\ntemperature-dependent ``c_max(temp)`` the level is the horizon-minimum ``c_max``\n(the largest constant full-output level feasible in every period); a period\nwhose capacity falls below the plant's own ``c_min`` makes the plant infeasible\nthere and is rejected, mirroring the deterministic solver's curve check.\n\nExactness and bias. For a **linear** (constant-marginal) heat rate the per-MWh\nmargin is output-independent, so the exact optimum is a corner and bang-bang is\nexact. For a **steep** (rising-marginal) curve the exact optimum may run at an\nefficient part load that bang-bang cannot represent, so the value is a\n**downward-biased lower bound**: whenever the full-load level is reachable in one\nstep (ramp rate >= operating range) the bang-bang on/off policy set is a strict\nsubset of the exact one, and restricting the load choice can only lose value.\n\nWarning (Req 21.3). Emits :class:`BangBangHedgeWarning`: hedges (sensitivities\nand critical-dispatch surfaces) are far more sensitive than the value itself to\nthe heat-rate-curve approximation, because they read the *slope* of value\nagainst price, which the single on/off kink distorts even where the value error\nis negligible.\n\nArgs:\n    plant: The operating model; a full-load-pinned copy is derived from it.\n    power_prices: Power price ``P_t`` per period.\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period.\n    initial_online: Whether the unit is producing entering the horizon; an\n        online unit is treated as running at the full-load level.\n    initial_output: Ignored when ``initial_online`` (the unit is pinned to full\n        load); retained for signature parity with the deterministic solver.\n    initial_uptime: Producing periods already accrued (min-run).\n    initial_downtime: Offline periods already accrued (start bucket / min-down).\n    output_step: Output-grid spacing (MW); immaterial here (single online level)\n        but validated ``> 0`` by the solver; defaults to the ramp rate.\n    discount_factors: Per-period to-today discount factors (default all 1.0).\n\nReturns:\n    The bang-bang :class:`DispatchSchedule` (outputs are 0 or the full-load\n    level).\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a discount\n        factor or ``output_step`` is non-positive; if ``c_max`` falls below\n        ``c_min`` at some temperature; or if the initial condition admits no\n        feasible schedule (delegated to the deterministic solver).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 325
        },
        {
          "name": "dispatch_deterministic",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_deterministic.dispatch_deterministic",
          "kind": "function",
          "signature": "dispatch_deterministic(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Solve the perfect-foresight optimal dispatch of ``plant`` (eq. B.1).",
          "doc": "Solve the perfect-foresight optimal dispatch of ``plant`` (eq. B.1).\n\nExact backward-induction DP over a discretised commitment/output state (see\nthe module docstring for the objective, the state space, the discretisation\nand its exactness, and the unit-commitment conventions). All inputs are\nvalidated before any computation and never mutated.\n\nArgs:\n    plant: The operating model (heat-rate curve, capacities, start costs,\n        ramp rate, durations).\n    power_prices: Power price ``P_t`` per period (may be negative).\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period (drives ``HR`` and\n        ``c_max``).\n    initial_online: Whether the unit is producing entering the horizon.\n    initial_output: Output entering the horizon (MW); must be on the grid\n        when ``initial_online`` (ignored otherwise).\n    initial_uptime: Producing periods already accrued (min-run); defaults to\n        \"min-run already satisfied\". Only used when ``initial_online``.\n    initial_downtime: Periods already offline (keys the first start's bucket\n        and min-down); must be ``>= 1`` (a unit \"not online\" has been offline for\n        at least one period); defaults to a long, cold, restart-ready downtime.\n        Only used when not ``initial_online``.\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    discount_factors: Per-period discount factors (default all 1.0).\n\nReturns:\n    The optimal :class:`DispatchSchedule`; ``total_value`` is the\n    perfect-foresight upper bound of Property 62.\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a\n        discount factor or ``output_step`` is non-positive; if\n        ``c_max(temp) < c_min`` or ``heat_rate(q, temp) ≤ 0`` at a supplied\n        temperature; if ``initial_output`` is off-grid while online; if\n        ``initial_downtime < 1`` while offline; or if the supplied initial\n        condition admits no feasible schedule.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_deterministic.py",
          "line": 298
        },
        {
          "name": "dispatch_value",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_sdp.dispatch_value",
          "kind": "function",
          "signature": "dispatch_value(plant: PlantModel, factor_model: DispatchFactorModel, *, method: str='lsm', seed: int, path_count: int=4096, output_step: float | None=None, availability: Sequence[float] | None=None, discount_factors: Sequence[float] | None=None, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, evaluation: MonteCarloEvaluation | None=None, antithetic: bool=True, regression_basis_degree: int=2) -> DispatchResult",
          "summary": "Value ``plant`` under uncertainty by stochastic DP (eqs. B.2-B.3; Req 21.1-21.2).",
          "doc": "Value ``plant`` under uncertainty by stochastic DP (eqs. B.2-B.3; Req 21.1-21.2).\n\nSolves the Bellman recursion over the deterministic module's commitment state\nmachine, under the risk-adjusted expectation carried by ``factor_model``\n(Req 21.5). See the module docstring for the state machine, the on-peak /\noff-peak Markov split (Req 21.6), the risk-adjusted-drift requirement, the\nforced-outage seam, and the critical-surface representation. All inputs are\nvalidated before any computation and never mutated.\n\nArgs:\n    plant: The operating model (heat-rate curve, capacities, start costs,\n        ramp rate, durations).\n    factor_model: Risk-adjusted factor dynamics and the per-period peak /\n        temperature context (also fixes the horizon ``H``).\n    method: ``\"lsm\"`` (least-squares Monte Carlo) or ``\"tree\"`` (recombining\n        lattice); selected via a dispatch table.\n    seed: Monte Carlo / lattice seed (Req 11.2 determinism); ``>= 0``.\n    path_count: Simulated paths for ``\"lsm\"`` (ignored by ``\"tree\"``); ``>= 1``.\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    availability: Optional per-period forced-outage multiplier ``M`` in\n        ``(0, 1]`` (length ``H``) derating ``c_max``; ``None`` = full\n        availability. A caller may source it from\n        :meth:`OutageDataset.forced_outage_multiplier`.\n    discount_factors: Per-period to-today discount factors (default all 1.0).\n    initial_online: Whether the unit is producing entering the horizon.\n    initial_output: Output entering the horizon (MW); on-grid when online.\n    initial_uptime: Producing periods already accrued (min-run).\n    initial_downtime: Periods already offline (start bucket / min-down); must be\n        ``>= 1`` when not ``initial_online`` (delegated to the reused\n        :func:`~quantvolt.assets.dispatch_deterministic._initial_state`).\n    evaluation: Independent LSM policy-evaluation sample. By default, the fitted\n        policy is evaluated on ``path_count`` fresh paths using ``seed + 1``.\n    antithetic: Whether ``\"lsm\"``'s simulated paths use antithetic variates\n        (default ``True``, matching prior behaviour); ignored by ``\"tree\"``\n        (the lattice has no simulation). Also selects the pair-mean-aware\n        standard-error estimator used for ``evaluation_standard_error``\n        (:class:`DispatchDiagnostics`).\n    regression_basis_degree: Degree of the polynomial regression basis used by\n        ``\"lsm\"``'s continuation-value fit (default ``2``: intercept, linears,\n        squares, pairwise cross terms -- the historical basis); ignored by\n        ``\"tree\"``. Must be ``>= 1``.\n\nReturns:\n    The :class:`DispatchResult` (value + eq. B.5 critical surfaces).\n\nRaises:\n    ValidationError: If ``method`` is unknown; if ``factor_model.drift`` is not\n        risk-adjusted (Req 21.5); if ``path_count`` / ``seed`` /\n        ``discount_factors`` / ``availability`` / ``regression_basis_degree`` are\n        out of range or mis-sized; if a plant curve is infeasible at a supplied\n        temperature; if ``initial_downtime < 1`` while offline; or if the initial\n        condition admits no feasible schedule.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_sdp.py",
          "line": 1120
        },
        {
          "name": "furthest_forward_lower_bound",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.furthest_forward_lower_bound",
          "kind": "function",
          "signature": "furthest_forward_lower_bound(forward_curve: ForwardCurve, period: DeliveryPeriod, *, storable: bool) -> LowerBoundResult",
          "summary": "Use the furthest visible forward as a lower bound for an illiquid later tenor.",
          "doc": "Use the furthest visible forward as a lower bound for an illiquid later tenor.\n\nFor a **storable** commodity the cash-and-carry / no-arbitrage relationship links\na later delivery to a nearer one, so the furthest liquid forward price is a valid\nlower bound for tenors beyond the curve (Req 23.4). This helper returns that bound\nfor ``period`` (which must be strictly later than the furthest liquid forward).\n\nFor a **non-storable** commodity such as power (``storable=False``) the bound is\nrefused: non-storability breaks the carry argument, so a nearer forward does not\nbound a later illiquid tenor and the furthest forward is not a valid lower bound\n(Req 23.4). Storability is caller-declared, never inferred from the commodity.\n\nArgs:\n    forward_curve: The liquid forward curve; its furthest node supplies the bound.\n    period: The illiquid tenor to bound; must be strictly later than the furthest\n        liquid forward.\n    storable: Caller's declaration that the commodity is storable. ``False``\n        (e.g. power) refuses the bound.\n\nReturns:\n    A :class:`LowerBoundResult` carrying the bound and the period it came from.\n\nRaises:\n    ValidationError: If ``storable`` is ``False`` (non-storable / power), or if\n        ``period`` is not strictly later than the furthest liquid forward.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 260
        },
        {
          "name": "horizon_divide",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_approx.horizon_divide",
          "kind": "function",
          "signature": "horizon_divide(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], sub_horizon: int, *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Horizon-division heuristic: solve independent sub-horizons and sum (Req 21.3).",
          "doc": "Horizon-division heuristic: solve independent sub-horizons and sum (Req 21.3).\n\nThe horizon is cut into consecutive sub-horizons of length ``sub_horizon`` (the\nlast may be shorter) that are solved *independently* by the deterministic DP and\nconcatenated; ``total_value`` is the sum of the sub-values. This is the weekly /\nmonthly sub-period heuristic that keeps each solve small.\n\nBoundary-state approximation. Only the **first** sub-horizon sees the caller's\ninitial condition; every later sub-horizon restarts from a cold, restart-ready\n*offline* state. Dropping the true carried-over commitment state is exactly what\ndecouples the subproblems — and is the approximation. It is **exact** when the\nperiods decouple (zero start costs and non-binding min-run / min-down / ramp),\nbecause the dispatch is then myopic and the start-up state is immaterial. It\n**typically understates** value otherwise (each boundary can pay a spurious\nrestart cost), but it *can* overstate value when a binding min-run / min-down\nconstraint that would span a boundary in the full solve is artificially relaxed\nby the cut.\n\nArgs:\n    plant: The operating model (unchanged; passed to each sub-solve).\n    power_prices: Power price ``P_t`` per period.\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period.\n    sub_horizon: Periods per sub-horizon; must be an integer ``>= 1``.\n    initial_online: Whether the unit is producing entering the *first*\n        sub-horizon.\n    initial_output: Output entering the first sub-horizon (MW); on the grid when\n        online.\n    initial_uptime: Producing periods already accrued entering the first\n        sub-horizon (min-run).\n    initial_downtime: Offline periods already accrued entering the first\n        sub-horizon (start bucket / min-down).\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    discount_factors: Per-period to-today discount factors (default all 1.0);\n        sliced per sub-horizon.\n\nReturns:\n    The concatenated full-horizon :class:`DispatchSchedule`; ``total_value`` is\n    the sum of the sub-horizon values.\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a discount\n        factor or ``output_step`` is non-positive; if ``sub_horizon`` is not an\n        integer ``>= 1``; or if any sub-problem is infeasible (delegated to the\n        deterministic solver).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 218
        },
        {
          "name": "storage_intrinsic",
          "module": "assets",
          "qualified": "quantvolt.assets.storage.storage_intrinsic",
          "kind": "function",
          "signature": "storage_intrinsic(model: StorageModel, forward_curve: ForwardCurve, *, inventory_step: float | None=None, grid_steps: int=_DEFAULT_GRID_STEPS) -> IntrinsicResult",
          "summary": "Optimal forward-locked injection/withdrawal schedule and its value (Req 22.1).",
          "doc": "Optimal forward-locked injection/withdrawal schedule and its value (Req 22.1).\n\nExact backward-induction dynamic program over the discretised inventory grid: with the\nforward curve's per-period prices known, it finds the injection/withdrawal schedule that\nmaximises total cash flow subject to the inventory bounds, the injection/withdrawal\nratchets and the terminal-inventory condition — all enforced at *every* step by the\nfeasible-transition set (Req 22.3). See the module docstring for the discretisation,\nthe cash-flow conventions and the exactness statement.\n\nArgs:\n    model: The storage parameters.\n    forward_curve: The forward curve whose node prices drive the schedule; nodes are taken\n        in chronological order, one delivery period per horizon step.\n    inventory_step: Inventory-grid spacing (volume); defaults to\n        ``working_capacity / grid_steps``. Must divide the distances from\n        ``min_inventory`` to ``initial_inventory`` and ``terminal_inventory``.\n    grid_steps: Number of inventory-grid intervals used to derive the default\n        ``inventory_step`` when it is not supplied (default ``50``). Ignored when\n        ``inventory_step`` is given explicitly. Must be ``>= 1``.\n\nReturns:\n    The optimal :class:`IntrinsicResult`.\n\nRaises:\n    ValidationError: If ``inventory_step`` is non-positive; if ``grid_steps < 1``; if the\n        initial/terminal inventory is off-grid; if a ratchet returns a negative rate at a\n        grid level; or if a hard terminal target is unreachable from the initial inventory\n        over the horizon.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 382
        },
        {
          "name": "storage_value",
          "module": "assets",
          "qualified": "quantvolt.assets.storage.storage_value",
          "kind": "function",
          "signature": "storage_value(model: StorageModel, forward_curve: ForwardCurve, factor_model: StorageFactorModel, seed: int, *, inventory_step: float | None=None, grid_steps: int=_DEFAULT_GRID_STEPS, lsm_basis_degree: int=_LSM_BASIS_DEGREE, antithetic: bool=True) -> StorageValueResult",
          "summary": "Total (intrinsic + extrinsic) storage value via Least-Squares Monte Carlo (Req 22.2).",
          "doc": "Total (intrinsic + extrinsic) storage value via Least-Squares Monte Carlo (Req 22.2).\n\nSimulates forward-consistent spot paths with ``factor_model`` (see\n:class:`StorageFactorModel`) and runs a backward induction over ``(time, inventory)`` that\nfinds the optimal *adaptive* injection/withdrawal policy. At each period and inventory\nlevel the decision maximises ``immediate cash flow + continuation value``, where the\ncontinuation value of each reachable next level is estimated by regressing the pathwise\nnext-period value on the polynomial basis ``[1, S, S**2]`` of the current spot ``S``\n(Longstaff-Schwartz). The regression is used only to choose the action; the value is then\naccumulated from the *realised* pathwise continuation to limit foldback bias. All the\ninventory-bound, ratchet and terminal constraints are enforced by the same\nfeasible-transition set as the intrinsic DP (Req 22.3).\n\nExtrinsic value via a control variate (Property 64)\n---------------------------------------------------\nThe extrinsic component is estimated as the mean pathwise difference between the adaptive\npolicy value and the *fixed intrinsic schedule* evaluated on the **same** simulated paths\n(common random numbers): ``extrinsic = mean_p[V_adaptive(p) - V_fixed(p)]``. Because the\nfixed forward-locked schedule is one feasible policy available to the optimal adaptive\npolicy, the difference is non-negative in expectation, and sharing the price paths cancels\nthe bulk of the sampling variance — so ``extrinsic >= 0`` holds robustly rather than being\nswamped by the (large) variance of ``total`` alone. ``total`` is anchored on the exact\nintrinsic value as ``intrinsic + extrinsic``, and ``extrinsic`` is reported honestly with\nits standard error rather than clamped (a small negative value within a few standard errors\nis Monte Carlo noise, per the Property-64 tolerance floor).\n\nArgs:\n    model: The storage parameters.\n    forward_curve: The forward curve (its node prices are the per-period forward means).\n    factor_model: The single-factor spot model and MC controls.\n    seed: RNG seed; identical inputs and seed give identical results (Req 11.2).\n    inventory_step: Inventory-grid spacing, shared with :func:`storage_intrinsic`.\n    grid_steps: Number of inventory-grid intervals used to derive the default\n        ``inventory_step`` when it is not supplied, shared with :func:`storage_intrinsic`\n        (default ``50``). Must be ``>= 1``.\n    lsm_basis_degree: Degree of the polynomial regression basis\n        ``[1, S, ..., S**lsm_basis_degree]`` used for the LSM continuation value (default\n        ``2``, i.e. ``[1, S, S**2]``). Must be ``>= 1``.\n    antithetic: Whether the simulated spot paths use antithetic variates (default\n        ``True``, matching prior behaviour). Also selects the pair-mean-aware\n        standard-error estimator used for ``standard_error`` (see\n        :func:`_standard_error`).\n\nReturns:\n    The :class:`StorageValueResult` with ``total``, ``intrinsic``, ``extrinsic`` and the\n    Monte Carlo ``standard_error`` of ``total``.\n\nRaises:\n    ValidationError: For the same grid/ratchet/terminal violations as\n        :func:`storage_intrinsic`, if ``seed`` is negative, or if ``lsm_basis_degree < 1``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/storage.py",
          "line": 553
        },
        {
          "name": "time_aggregate",
          "module": "assets",
          "qualified": "quantvolt.assets.dispatch_approx.time_aggregate",
          "kind": "function",
          "signature": "time_aggregate(plant: PlantModel, power_prices: Sequence[float], fuel_prices: Sequence[float], temperatures: Sequence[float], block_hours: int, *, initial_online: bool=False, initial_output: float=0.0, initial_uptime: int | None=None, initial_downtime: int | None=None, output_step: float | None=None, discount_factors: Sequence[float] | None=None) -> DispatchSchedule",
          "summary": "Time-aggregation heuristic: solve on ``block_hours``-hour blocks, rescale (Req 21.3).",
          "doc": "Time-aggregation heuristic: solve on ``block_hours``-hour blocks, rescale (Req 21.3).\n\nEach consecutive run of ``block_hours`` periods is averaged into one coarse\nperiod (power, fuel, temperature, and — if supplied — discount factor), the\ndeterministic dispatch is solved on the coarse series, and the coarse per-period\nresult is expanded back to the original resolution with each block's cash flow\nrecurring ``block_hours`` times (the rescaling). The returned\n:class:`DispatchSchedule` therefore has the original horizon's length and a\n``total_value`` equal to ``block_hours`` times the coarse value.\n\nExactness and bias. On **block-constant** prices (each series constant within\nevery block) the block average is lossless and, for a unit that incurs no start\nwithin the horizon, the rescaled value equals the full-resolution optimum\nexactly. When a start *is* incurred inside a block, the once-per-block start\ncost is replicated across the block's sub-periods, understating the value — a\ndocumented downward bias that shrinks with fewer/cheaper starts. Sub-block ramp\nand commitment freedom (and any intra-block discount-factor variation) are the\nother, generally small, sources of error. Duration/timer arguments are counted\nin *coarse* periods (blocks) inside the coarse solve; pass them accordingly.\n\nArgs:\n    plant: The operating model (unchanged; passed to the coarse solve).\n    power_prices: Power price ``P_t`` per (fine) period.\n    fuel_prices: Fuel price ``G_t`` per period.\n    temperatures: Ambient temperature ``S_t`` per period.\n    block_hours: Periods per aggregation block; must be an integer ``>= 1`` that\n        divides the horizon evenly.\n    initial_online: Whether the unit is producing entering the horizon.\n    initial_output: Output entering the horizon (MW); on the coarse grid when\n        online.\n    initial_uptime: Producing (coarse) periods already accrued (min-run).\n    initial_downtime: Offline (coarse) periods already accrued (start bucket /\n        min-down).\n    output_step: Output-grid spacing (MW); defaults to the ramp rate.\n    discount_factors: Per-period to-today discount factors (default all 1.0);\n        block-averaged before the coarse solve.\n\nReturns:\n    A full-resolution :class:`DispatchSchedule`; ``total_value`` is the rescaled\n    coarse value.\n\nRaises:\n    ValidationError: If the series are empty or of unequal length; if a discount\n        factor or ``output_step`` is non-positive; if ``block_hours`` is not an\n        integer ``>= 1`` or does not divide the horizon; or if the coarse problem\n        is itself infeasible (delegated to the deterministic solver).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/dispatch_approx.py",
          "line": 98
        },
        {
          "name": "valuation_benchmark",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.valuation_benchmark",
          "kind": "function",
          "signature": "valuation_benchmark(period: DeliveryPeriod, forward_curve: ForwardCurve, spot_model: SpotModel, corporate_premium: CorporatePremium) -> BenchmarkResult",
          "summary": "Value ``period`` off the forward curve where liquid, else off projected spot.",
          "doc": "Value ``period`` off the forward curve where liquid, else off projected spot.\n\nWhere the liquid ``forward_curve`` covers ``period``, the forward price is the\nvaluation benchmark and no projected-spot value is substituted (Req 23.1). A\nperiod present on the curve counts as forward-based whether its node is\n``observed`` or ``interpolated`` — both lie within the liquid forward span. Where\nthe curve does not cover ``period``, the value is projected as\n``spot_model(period) + corporate_premium.premium`` and tagged\n:attr:`ValuationSource.PROJECTED` (Req 23.2).\n\n``corporate_premium`` is validated eagerly (before the liquidity branch) so a\nmarket-tagged or untagged premium is rejected regardless of this period's\nliquidity — the corporate risk premium is never applied silently (Req 19.3).\n\nArgs:\n    period: The delivery period to value.\n    forward_curve: The liquid forward curve; membership of ``period`` decides the\n        regime.\n    spot_model: Pure callable ``DeliveryPeriod -> float`` giving the model spot\n        expectation used when no liquid forward exists. Never mutated.\n    corporate_premium: The additive corporate risk premium, explicitly tagged\n        :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`.\n\nReturns:\n    A :class:`BenchmarkResult` whose ``source`` tags the regime prominently.\n\nRaises:\n    ValidationError: If ``corporate_premium`` is not an explicitly corporate-tagged\n        :class:`CorporatePremium`.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 169
        },
        {
          "name": "var_applicability_guard",
          "module": "assets",
          "qualified": "quantvolt.assets.long_dated.var_applicability_guard",
          "kind": "function",
          "signature": "var_applicability_guard(position: PricedPosition, *, strict: bool=False) -> VarApplicabilityVerdict",
          "summary": "Flag short-horizon VaR as inapplicable for a projected-spot-valued position.",
          "doc": "Flag short-horizon VaR as inapplicable for a projected-spot-valued position.\n\nReads the position's provenance from ``position.position.tags``: a position\ncarrying the :attr:`ValuationSource.PROJECTED` tag was valued off projected spot,\nfor which short-horizon VaR is not meaningful — VaR is meaningful only in liquid\nmarkets (Chapter-10 caveat, Req 23.3). Absence of that tag is treated as\nforward-based / liquid and therefore VaR-applicable.\n\nDesigned to be *consulted* by MC-VaR / parametric-VaR callers: they inspect the\nreturned verdict and exclude the position (or switch to CFaR / scenario analysis)\nwithout this module modifying ``risk/``. With ``strict=True`` the guard instead\nraises for an inapplicable position, for callers that prefer to hard-fail.\n\nArgs:\n    position: The priced position to judge, as consumed by the risk engines.\n    strict: When ``True``, raise :class:`ValidationError` for a projected-spot\n        position instead of returning an ``applicable=False`` verdict.\n\nReturns:\n    A :class:`VarApplicabilityVerdict` with ``applicable`` and a ``reason``.\n\nRaises:\n    ValidationError: If ``strict`` is ``True`` and the position is projected-valued.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/assets/long_dated.py",
          "line": 213
        }
      ]
    },
    {
      "name": "curvemodels",
      "qualified": "quantvolt.curvemodels",
      "description": "Stochastic single- and multi-commodity forward models.",
      "symbols": [
        {
          "name": "CalibrationDiagnostics",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.schwartz_smith.CalibrationDiagnostics",
          "kind": "class",
          "signature": "CalibrationDiagnostics(converged: bool, optimizer_message: str, n_iterations: int, log_likelihood: float, gradient_norm: float, hessian_condition_number: float, param_std_errors: dict[str, float], measurement_sigma: float, filtered_initial_state: tuple[float, float], residual_rmse: float, initial_curve_max_abs_mismatch: float, fits_initial_curve: bool, lognormal_power_caveat: str)",
          "summary": "Fit diagnostics returned alongside calibrated :class:`SchwartzSmithParams` (Req 25.6).",
          "doc": "Fit diagnostics returned alongside calibrated :class:`SchwartzSmithParams` (Req 25.6).\n\n* ``converged`` / ``optimizer_message`` / ``n_iterations`` — MLE termination status.\n  ``n_iterations`` is ``result.nit`` when the chosen ``optimizer_method`` reports it;\n  methods that don't (e.g. COBYLA has no ``nit`` attribute at all) fall back to\n  ``result.nfev`` (the function-evaluation count) as the nearest available proxy for\n  how much optimizer work occurred before termination.\n* ``log_likelihood`` — maximised Gaussian log-likelihood (prediction-error decomposition).\n* ``gradient_norm`` — ``||grad NLL||`` at the optimum (near 0 at a good stationary point).\n* ``hessian_condition_number`` — condition number of the observed information; large values\n  warn of weakly identified parameters (typically the drift/risk-premium terms).\n* ``param_std_errors`` — asymptotic MLE standard errors keyed by parameter name (``nan``\n  where the information matrix is singular, i.e. the parameter is not identified).\n* ``measurement_sigma`` — fitted per-tenor log-price measurement-noise standard deviation.\n* ``filtered_initial_state`` — filtered ``(chi_0, xi_0)`` at the first observation date.\n* ``residual_rmse`` — RMSE of the log-price measurement residuals (filtered fit).\n* ``initial_curve_max_abs_mismatch`` — max ``|model - observed|`` log-forward at the first\n  date (Req 25.5 flag); ``fits_initial_curve`` is ``True`` only if it is within tolerance.\n* ``lognormal_power_caveat`` — the §31.3 suitability warning (Req 25.5).",
          "methods": [],
          "fields": [
            {
              "name": "converged",
              "type": "bool",
              "default": null
            },
            {
              "name": "optimizer_message",
              "type": "str",
              "default": null
            },
            {
              "name": "n_iterations",
              "type": "int",
              "default": null
            },
            {
              "name": "log_likelihood",
              "type": "float",
              "default": null
            },
            {
              "name": "gradient_norm",
              "type": "float",
              "default": null
            },
            {
              "name": "hessian_condition_number",
              "type": "float",
              "default": null
            },
            {
              "name": "param_std_errors",
              "type": "dict[str, float]",
              "default": null
            },
            {
              "name": "measurement_sigma",
              "type": "float",
              "default": null
            },
            {
              "name": "filtered_initial_state",
              "type": "tuple[float, float]",
              "default": null
            },
            {
              "name": "residual_rmse",
              "type": "float",
              "default": null
            },
            {
              "name": "initial_curve_max_abs_mismatch",
              "type": "float",
              "default": null
            },
            {
              "name": "fits_initial_curve",
              "type": "bool",
              "default": null
            },
            {
              "name": "lognormal_power_caveat",
              "type": "str",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 307
        },
        {
          "name": "LognormalPowerWarning",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.LognormalPowerWarning",
          "kind": "class",
          "signature": "LognormalPowerWarning()",
          "summary": "Advisory that a lognormal (``dF/F``) forward model is being used on power (Req 25.5).",
          "doc": "Advisory that a lognormal (``dF/F``) forward model is being used on power (Req 25.5).\n\nLognormal forward dynamics keep forwards strictly positive and impose Gaussian\nlog-returns; they cannot reproduce the price spikes, negative prices, and heavy tails\nof spot power. The model is not *rejected* -- it may be appropriate for smooth,\nfar-dated power forwards -- but callers are warned so the choice is deliberate.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 94
        },
        {
          "name": "MultifactorForwardModel",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.MultifactorForwardModel",
          "kind": "class",
          "signature": "MultifactorForwardModel(loadings: npt.NDArray[np.float64], dt: float = 1.0 / 12.0)",
          "summary": "Frozen config over factor loadings ``sigma_k(t, T)`` for the §32-33 forward model.",
          "doc": "Frozen config over factor loadings ``sigma_k(t, T)`` for the §32-33 forward model.\n\nAttributes:\n    loadings: ``(n_steps, n_factors, n_tenors)`` ``float64`` array; ``loadings[b, k, j]``\n        is ``sigma_k(t_b, T_j)``, the instantaneous loading of factor ``k`` on tenor\n        (or ``(commodity, month)``) ``j`` over time bucket ``b`` of width ``dt``. Copied\n        and made read-only at construction so the config is genuinely immutable.\n    dt: Uniform time-step ``Delta t`` in years over which each bucket's loadings hold.\n        Defaults to ``1/12`` (monthly, §33). Must be ``> 0``.\n\nThe initial curve ``F(0, T)`` is *not* stored: it is supplied to :func:`simulate_forwards`\nand matched by construction (the dynamics are a driftless-in-``F`` martingale from any\npositive ``F(0, T)``; Property 71). Validation is eager (Req 11.5): 3-D shape with every\naxis non-empty, all-finite loadings, and ``dt > 0``.",
          "methods": [
            {
              "name": "n_steps",
              "signature": "n_steps(self) -> int",
              "summary": "Number of discrete time buckets on the loading grid."
            },
            {
              "name": "n_factors",
              "signature": "n_factors(self) -> int",
              "summary": "Number of common Brownian factors ``K`` (``M`` in §33)."
            },
            {
              "name": "n_tenors",
              "signature": "n_tenors(self) -> int",
              "summary": "Size of the flattened forward state ``D`` (tenors, or ``(commodity, month)``)."
            },
            {
              "name": "from_target_correlation",
              "signature": "from_target_correlation(cls, target_corr: npt.ArrayLike, instantaneous_vols: npt.ArrayLike, *, n_steps: int=1, dt: float=1.0 / 12.0, symmetry_tol: float=_SYMMETRY_TOL, psd_eig_tol: float=_PSD_EIG_TOL, unit_diagonal_tol: float=_UNIT_DIAGONAL_TOL) -> MultifactorForwardModel",
              "summary": "Build loadings whose induced structure reproduces a target correlation (§33.4)."
            }
          ],
          "fields": [
            {
              "name": "loadings",
              "type": "npt.NDArray[np.float64]",
              "default": null
            },
            {
              "name": "dt",
              "type": "float",
              "default": "1.0 / 12.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 105
        },
        {
          "name": "SchwartzSmithParams",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.schwartz_smith.SchwartzSmithParams",
          "kind": "class",
          "signature": "SchwartzSmithParams(kappa: float, sigma_chi: float, sigma_xi: float, mu_xi: float, rho: float, lambda_chi: float, lambda_xi: float)",
          "summary": "Risk-neutral parameters of the two-factor Schwartz-Smith model (§31.1).",
          "doc": "Risk-neutral parameters of the two-factor Schwartz-Smith model (§31.1).\n\nFields match Req 25.1 / design ``SchwartzSmithParams``:\n\n* ``kappa`` — short-factor mean-reversion speed (``> 0``).\n* ``sigma_chi`` — short-factor volatility (``> 0``).\n* ``sigma_xi`` — long-factor volatility (``> 0``).\n* ``mu_xi`` — physical long-term drift of ``xi`` (unconstrained).\n* ``rho`` — instantaneous correlation of the two Brownian factors, ``in (-1, 1)``.\n* ``lambda_chi`` — short-factor risk premium (unconstrained).\n* ``lambda_xi`` — long-factor risk premium (unconstrained).\n\n:attr:`mu_xi_star` = ``mu_xi - lambda_xi`` is the risk-neutral long-term drift that\nenters the forward curve (§31.2).",
          "methods": [
            {
              "name": "mu_xi_star",
              "signature": "mu_xi_star(self) -> float",
              "summary": "Risk-neutral long-term drift ``mu_xi - lambda_xi`` (the drift entering ``A(tau)``)."
            }
          ],
          "fields": [
            {
              "name": "kappa",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma_chi",
              "type": "float",
              "default": null
            },
            {
              "name": "sigma_xi",
              "type": "float",
              "default": null
            },
            {
              "name": "mu_xi",
              "type": "float",
              "default": null
            },
            {
              "name": "rho",
              "type": "float",
              "default": null
            },
            {
              "name": "lambda_chi",
              "type": "float",
              "default": null
            },
            {
              "name": "lambda_xi",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 86
        },
        {
          "name": "calibrate",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.schwartz_smith.calibrate",
          "kind": "function",
          "signature": "calibrate(observed_forwards: npt.ArrayLike, time_to_maturity: npt.ArrayLike, dt: float, *, max_iter: int=500, initial_curve_tol: float=_INITIAL_CURVE_TOL, diffuse_prior_var: float=_DIFFUSE_VAR, optimizer_method: str='L-BFGS-B') -> tuple[SchwartzSmithParams, CalibrationDiagnostics]",
          "summary": "Calibrate the model from a history of observed forward curves (Req 25.2, 25.5, 25.6).",
          "doc": "Calibrate the model from a history of observed forward curves (Req 25.2, 25.5, 25.6).\n\nA linear-Gaussian Kalman filter (see :func:`_kalman_filter`) treats the latent\n``(chi, xi)`` as the state and the log-forward cross-sections as measurements, and its\nprediction-error decomposition is maximised by :func:`scipy.optimize.minimize`\n(``optimizer_method``, default L-BFGS-B, over an unconstrained transform of the\nparameters).\n\nArgs:\n    observed_forwards: History of observed forward **prices**, shape\n        ``(n_obs, n_tenors)`` — one row per observation date (chronological), one column\n        per constant time-to-maturity. Must be strictly positive (logs are taken).\n    time_to_maturity: 1-D array of the constant times-to-maturity ``tau`` (years) for the\n        columns; the same ``tau`` applies to every observation date (a constant-maturity\n        \"rolling\" curve history), so the measurement matrix is time-invariant.\n    dt: Time between consecutive observation dates (years, ``> 0``).\n    max_iter: Maximum optimiser iterations.\n    initial_curve_tol: Log-price tolerance below which the filtered initial\n        curve is deemed an exact match (``fits_initial_curve``), positive\n        (default ``1e-6``).\n    diffuse_prior_var: Diffuse prior variance for the non-stationary\n        long-term factor ``xi`` in the Kalman filter, positive (default\n        ``10.0``).\n    optimizer_method: :func:`scipy.optimize.minimize` method name, a\n        non-empty string (default ``\"L-BFGS-B\"``).\n\nReturns:\n    ``(params, diagnostics)`` — the fitted :class:`SchwartzSmithParams` and a\n    :class:`CalibrationDiagnostics`. The diagnostics flag any initial-curve mismatch\n    (Req 25.5) and report identifiability via standard errors / Hessian conditioning\n    (Req 25.6).\n\nRaises:\n    ValidationError: if ``dt <= 0``, ``initial_curve_tol <= 0``,\n        ``diffuse_prior_var <= 0``, ``optimizer_method`` is empty, shapes are\n        inconsistent, any ``tau`` is negative, any observed forward is\n        non-positive, or the MLE fails to converge.\n    InsufficientDataError: if fewer than three observation dates are supplied (the\n        transition dynamics cannot be identified from fewer).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 547
        },
        {
          "name": "cumulative_covariance",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.cumulative_covariance",
          "kind": "function",
          "signature": "cumulative_covariance(model: MultifactorForwardModel, upto_step: int | None=None) -> npt.NDArray[np.float64]",
          "summary": "Cumulative covariance ``Gamma`` over ``[0, T*]`` (§33 cumulative multi-commodity covariance).",
          "doc": "Cumulative covariance ``Gamma`` over ``[0, T*]`` (§33 cumulative multi-commodity covariance).\n\nReturns ``Gamma[i, j] = sum_{b < n} sum_k sigma_k(t_b, T_i)·sigma_k(t_b, T_j)·dt`` -- the\nRiemann sum of the induced covariance rate over the first ``n`` buckets, i.e. the discrete\n``integral_0^{T*} sum_k sigma_k(s, T_i) sigma_k(s, T_j) ds`` with ``T* = n·dt``. With\n``upto_step is None`` the whole horizon (all ``n_steps`` buckets) is used. As a sum of\nGram matrices scaled by ``dt > 0``, ``Gamma`` is symmetric and positive semidefinite by\nconstruction (Property 72).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 309
        },
        {
          "name": "forward_curve",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.schwartz_smith.forward_curve",
          "kind": "function",
          "signature": "forward_curve(params: SchwartzSmithParams, chi: float, xi: float, t: float, tenors: npt.ArrayLike) -> npt.NDArray[np.float64]",
          "summary": "Closed-form forward curve ``F(t, T) = exp[e^(-kappa*tau)*chi + xi + A(tau)]`` (§31.2).",
          "doc": "Closed-form forward curve ``F(t, T) = exp[e^(-kappa*tau)*chi + xi + A(tau)]`` (§31.2).\n\nThe lightest faithful surface (tasks.md wording): a ``float64`` array of forward prices\n``F(t, T)`` aligned with ``tenors``. No :class:`~quantvolt.models.ForwardCurve` is built\nbecause this signature carries no commodity/delivery-period context; the caller wraps the\nresult if a full curve object is wanted.\n\nSee :func:`log_forward_curve` for argument semantics (``tenors`` are maturities ``T``).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 201
        },
        {
          "name": "forward_matching_residual",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.forward_matching_residual",
          "kind": "function",
          "signature": "forward_matching_residual(initial_forwards: npt.ArrayLike, expected_forwards: npt.ArrayLike) -> npt.NDArray[np.float64]",
          "summary": "Residual of the §33.2 forward-matching condition ``E^Q[F(t)] - F(0)``.",
          "doc": "Residual of the §33.2 forward-matching condition ``E^Q[F(t)] - F(0)``.\n\nThe forward-matching condition (§33.2 \"Current Forward-Curve Matching Condition\") is\n``E^Q[F_(i,k)(t)] = F_(i,k)(0)``. This returns ``expected_forwards - initial_forwards``,\nwhich is zero in expectation for the martingale dynamics and should be ~0 for a\nsimulated Monte Carlo mean. At ``t = 0`` it is exactly zero by construction.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 375
        },
        {
          "name": "induced_correlation",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.induced_correlation",
          "kind": "function",
          "signature": "induced_correlation(model: MultifactorForwardModel, step: int) -> npt.NDArray[np.float64]",
          "summary": "Instantaneous induced correlation matrix at bucket ``step`` (§32.2, §33.4).",
          "doc": "Instantaneous induced correlation matrix at bucket ``step`` (§32.2, §33.4).\n\nNormalises :func:`induced_covariance` to correlations\n``rho[i, j] = Sigma[i, j] / (sqrt(Sigma[i, i])·sqrt(Sigma[j, j]))`` (\"Induced Forward\nCorrelation\", §32.2). By Cauchy-Schwarz on the Gram matrix ``rho in [-1, 1]`` with\n``rho[i, i] = 1`` for every tenor of non-zero variance; the result is clipped to\n``[-1, 1]`` to absorb float round-off, so the bound holds exactly (Property 72). A tenor\nwith zero instantaneous variance (expired, eq A.5) has an undefined off-diagonal\ncorrelation with every other tenor, so those entries are set to ``0``; its OWN diagonal\nentry, however, is set to ``1`` (a unit-diagonal convention, not a claim of unit\nvariance) rather than ``0``. This matters because ``sigma_i = 0`` already zeroes that\nrow/column of the *covariance* ``C = diag(sigma)·R·diag(sigma)`` regardless of\n``R[i, i]`` (:func:`~quantvolt.numerics.monte_carlo.build_covariance`, which the\nsimulator uses to hold expired tenors fixed) -- so a ``0`` diagonal here would only\nfail that function's own unit-diagonal validation without changing the covariance at\nall. Consumers other than :func:`mc_inputs`/:func:`simulate_forwards` should treat a\nzero-variance tenor's diagonal entry as \"undefined, not a correlation of 1\" and check\n:func:`induced_covariance`'s diagonal (or the model's per-tenor ``sigma``) directly if\nthey need to detect expiry.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 277
        },
        {
          "name": "induced_covariance",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.induced_covariance",
          "kind": "function",
          "signature": "induced_covariance(model: MultifactorForwardModel, step: int) -> npt.NDArray[np.float64]",
          "summary": "Instantaneous induced covariance-*rate* matrix at bucket ``step`` (§32.2, §33.4).",
          "doc": "Instantaneous induced covariance-*rate* matrix at bucket ``step`` (§32.2, §33.4).\n\nReturns the ``(D, D)`` matrix ``Sigma[i, j] = sum_k sigma_k(t_step, T_i)·sigma_k(t_step, T_j)``\n-- the coefficient of ``dt`` in ``d<ln F(·,T_i), ln F(·,T_j)>_t`` (§32.2 \"Induced Forward\nCovariance\"). It is the Gram matrix ``LᵀL`` of the loading slice ``L = loadings[step]``\n(shape ``(K, D)``) and is therefore symmetric and positive semidefinite **by\nconstruction**. Multiply by ``model.dt`` for the one-step covariance consumed by the MC\nengine (equivalently :func:`cumulative_covariance` over a single bucket).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 262
        },
        {
          "name": "log_forward_curve",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.schwartz_smith.log_forward_curve",
          "kind": "function",
          "signature": "log_forward_curve(params: SchwartzSmithParams, chi: float, xi: float, t: float, tenors: npt.ArrayLike) -> npt.NDArray[np.float64]",
          "summary": "Log-forward curve ``ln F(t, T) = e^(-kappa*tau)*chi + xi + A(tau)``, ``tau = T - t``.",
          "doc": "Log-forward curve ``ln F(t, T) = e^(-kappa*tau)*chi + xi + A(tau)``, ``tau = T - t``.\n\nThis is the measurement space of the model (linear in the latent factors), so the\nshort-factor loading ``e^(-kappa*tau)`` is exposed directly: as ``kappa*tau -> inf`` it\ndecays to 0 and the long-dated log-forward depends only on ``xi`` and ``A(tau)``\n(Property 70).\n\nArgs:\n    params: Risk-neutral model parameters.\n    chi: Short-term factor value ``chi_t`` at valuation time ``t``.\n    xi: Long-term factor value ``xi_t`` at valuation time ``t``.\n    t: Valuation time in years.\n    tenors: 1-D array of **maturities ``T``** (absolute times in years); ``tau = T - t``\n        must be non-negative for every entry.\n\nReturns:\n    A ``float64`` array of log-forward prices aligned with ``tenors``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 169
        },
        {
          "name": "matches_initial_curve",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.matches_initial_curve",
          "kind": "function",
          "signature": "matches_initial_curve(initial_forwards: npt.ArrayLike, expected_forwards: npt.ArrayLike, *, rtol: float=0.01, atol: float=1e-08) -> bool",
          "summary": "Check the §33.2 forward-matching condition ``E^Q[F(t)] == F(0)`` within tolerance.",
          "doc": "Check the §33.2 forward-matching condition ``E^Q[F(t)] == F(0)`` within tolerance.\n\nReturns ``True`` iff ``expected_forwards`` matches ``initial_forwards`` within\n``(rtol, atol)``. The default ``rtol`` accommodates a Monte Carlo mean; at ``t = 0`` the\nmatch is exact. ``rtol`` is applied against ``initial_forwards`` (comparing the two\ncurves directly), not against a residual, so a relative tolerance is meaningful.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 394
        },
        {
          "name": "matches_option_variance",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.matches_option_variance",
          "kind": "function",
          "signature": "matches_option_variance(model: MultifactorForwardModel, implied_vols: npt.ArrayLike, expiries: npt.ArrayLike, *, rtol: float=1e-09, atol: float=1e-12) -> bool",
          "summary": "Check the §33.3 option-variance-matching condition ``Gamma_ii(T) == sigma_impl^2·T``.",
          "doc": "Check the §33.3 option-variance-matching condition ``Gamma_ii(T) == sigma_impl^2·T``.\n\nCompares the model's cumulative per-tenor variance :func:`option_variance` (over the\nfull horizon) against the quoted Black total variance ``[sigma_impl]^2·(T_k)`` for each\ntenor. Because expired-tenor loadings are zero past expiry (eq A.5), the full-horizon\n``Gamma_ii`` equals the integral only up to each tenor's own expiry ``T_k``, so a single\nper-tenor ``expiries`` vector suffices. Returns ``True`` iff every tenor matches within\n``(rtol, atol)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 345
        },
        {
          "name": "mc_inputs",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.mc_inputs",
          "kind": "function",
          "signature": "mc_inputs(model: MultifactorForwardModel, step: int) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]",
          "summary": "Produce the ``(sigma, corr)`` structure for the correlated MC engine (§2.20, Task 62).",
          "doc": "Produce the ``(sigma, corr)`` structure for the correlated MC engine (§2.20, Task 62).\n\nDecomposes the bucket-``step`` induced covariance rate into the per-index instantaneous\nvolatility ``sigma_i = sqrt(Sigma[i, i])`` and the induced correlation ``R`` so the caller\ncan assemble the one-step covariance with\n``numerics.monte_carlo.build_covariance(sigma, corr, model.dt)`` -- which reproduces\n``induced_covariance(model, step)·dt`` exactly. ``sigma`` is non-negative and ``corr`` is\nsymmetric, unit-diagonal, and PSD, so it passes ``build_covariance``'s validation and the\nengine's Property-61 PSD gate. Expired tenors surface as ``sigma_i = 0`` (eq A.5).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 429
        },
        {
          "name": "option_variance",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.option_variance",
          "kind": "function",
          "signature": "option_variance(model: MultifactorForwardModel, upto_step: int | None=None) -> npt.NDArray[np.float64]",
          "summary": "Cumulative per-tenor variance ``Gamma_ii`` to horizon (§33.3 total-variance LHS).",
          "doc": "Cumulative per-tenor variance ``Gamma_ii`` to horizon (§33.3 total-variance LHS).\n\nReturns the diagonal of :func:`cumulative_covariance`,\n``Gamma_ii = sum_b sum_k sigma_k(t_b, T_i)^2·dt`` -- the left-hand side of the §33.3\noption-variance-matching condition ``integral sum_m sigma_(i,k,m)^2 ds =\n[sigma_impl]^2·(T - t)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 332
        },
        {
          "name": "risk_neutral_drift",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.risk_neutral_drift",
          "kind": "function",
          "signature": "risk_neutral_drift(cov: npt.ArrayLike) -> npt.NDArray[np.float64]",
          "summary": "Per-step risk-neutral log-drift ``mu = -1/2 · diag(C)`` (Q-measure, §32 integrated form).",
          "doc": "Per-step risk-neutral log-drift ``mu = -1/2 · diag(C)`` (Q-measure, §32 integrated form).\n\nThe integrated multifactor solution carries the Ito correction ``-1/2 integral sum_k\nsigma_k^2 ds`` in log space, so under ``Q`` the per-step drift of ``ln F`` is\n``-1/2·diag(C)`` where ``C`` is the one-step covariance. This drift makes the simulated\n``F = exp(Z)`` a martingale, ``E^Q[F(t, T)] = F(0, T)`` (Property 71). Feed it as the\n``drift`` argument of ``simulate_correlated_forwards``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 414
        },
        {
          "name": "simulate",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.schwartz_smith.simulate",
          "kind": "function",
          "signature": "simulate(params: SchwartzSmithParams, chi0: float, xi0: float, dt: float, steps: int, path_count: int, seed: int) -> npt.NDArray[np.float64]",
          "summary": "Simulate the joint (chi, xi) factor paths under Q by exact discretisation.",
          "doc": "Simulate the joint (chi, xi) factor paths under Q by exact discretisation.\n\nThe short factor is an Ornstein-Uhlenbeck process and the long factor an arithmetic\nBrownian motion; the **exact** joint transition over a step ``dt`` is::\n\n    chi_{n+1} = e^(-kappa*dt)*chi_n - (lambda_chi/kappa)*(1 - e^(-kappa*dt)) + eps_chi\n    xi_{n+1}  = xi_n + (mu_xi - lambda_xi)*dt + eps_xi\n    (eps_chi, eps_xi) ~ N(0, Q)     # Q from `_transition_covariance`\n\n**Why not the Task-62 correlated engine.** ``numerics.monte_carlo.simulate_correlated_\nforwards`` advances an additive random walk ``Z <- Z + mu + L*eps`` with a *constant*\nper-step drift and no dependence on the current state. That is exact for ``xi`` but not\nfor ``chi``: the OU exact step multiplies the *state* by ``e^(-kappa*dt)``, which the\nadditive kernel cannot represent, and the ``rho`` correlation couples the two factors so\nthey must be drawn jointly. A direct exact scheme is therefore used — it is unconditionally\nexact (no discretisation bias for any ``dt``) and stays deterministic under ``seed`` via\n:func:`numpy.random.default_rng` (Req 25.6, 11.2).\n\nArgs:\n    params: Risk-neutral model parameters.\n    chi0: Initial short-term factor value.\n    xi0: Initial long-term factor value.\n    dt: Step length in years (``> 0``).\n    steps: Number of steps (``>= 1``).\n    path_count: Number of paths (``>= 1``).\n    seed: Non-negative RNG seed; identical inputs give bit-identical paths.\n\nReturns:\n    A ``float64`` array of shape ``(path_count, steps + 1, 2)`` (matching the Task-62\n    convention). ``[:, :, 0]`` is ``chi``, ``[:, :, 1]`` is ``xi``; record 0 of every\n    path is ``(chi0, xi0)``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/schwartz_smith.py",
          "line": 237
        },
        {
          "name": "simulate_forwards",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.simulate_forwards",
          "kind": "function",
          "signature": "simulate_forwards(model: MultifactorForwardModel, initial_forwards: npt.ArrayLike, *, steps: int, path_count: int, seed: int, step: int=0, commodity_ids: Sequence[str] | None=None, antithetic: bool=True) -> npt.NDArray[np.float64]",
          "summary": "Simulate risk-neutral forward-price paths via the correlated MC engine (§2.20 bridge).",
          "doc": "Simulate risk-neutral forward-price paths via the correlated MC engine (§2.20 bridge).\n\nAssembles the one-step covariance ``C = build_covariance(*mc_inputs(model, step), dt)``,\nsets the martingale drift ``mu = -1/2·diag(C)`` (:func:`risk_neutral_drift`), and drives\n``numerics.monte_carlo.simulate_correlated_forwards`` from ``z0 = ln F(0, ·)``. Returns\n**forward prices** ``F = exp(Z)`` of shape ``(n_paths, steps + 1, D)``; record 0 of every\npath equals ``initial_forwards`` exactly (initial-curve match by construction, Property\n71). ``initial_forwards`` must be strictly positive (lognormal support). The bucket\n``step`` loading slice is held constant across all ``steps`` because the engine consumes a\nsingle covariance; for genuinely time-varying loadings the caller assembles a per-step\ncovariance itself. If ``commodity_ids`` is given, the lognormal-not-for-power advisory\n(:func:`warn_if_power_like`) fires first.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 475
        },
        {
          "name": "warn_if_power_like",
          "module": "curvemodels",
          "qualified": "quantvolt.curvemodels.multifactor.warn_if_power_like",
          "kind": "function",
          "signature": "warn_if_power_like(commodity_ids: Sequence[str]) -> tuple[str, ...]",
          "summary": "Emit the lognormal-not-for-power advisory for any power-like id (Req 25.5).",
          "doc": "Emit the lognormal-not-for-power advisory for any power-like id (Req 25.5).\n\nA lognormal ``dF/F`` forward model is *not automatically appropriate for spiky power\nprices*. This scans ``commodity_ids`` (against the built-in power ids and power-market\nsubstrings such as ``EPEX``/``PHELIX``/``POWER``) and, if any match, issues a\n:class:`LognormalPowerWarning` naming them. Returns the tuple of matched ids (possibly\nempty) so callers can branch or assert on the outcome.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/curvemodels/multifactor.py",
          "line": 448
        }
      ]
    },
    {
      "name": "stats",
      "qualified": "quantvolt.stats",
      "description": "Descriptive, stationarity, correlation and mean-reversion statistics.",
      "symbols": [
        {
          "name": "DescriptiveStats",
          "module": "stats",
          "qualified": "quantvolt.stats.descriptive.DescriptiveStats",
          "kind": "class",
          "signature": "DescriptiveStats(mean: float, std: float, skewness: float, kurtosis: float, n: int, t_statistic: float)",
          "summary": "Summary statistics of a price (or price-change) series.",
          "doc": "Summary statistics of a price (or price-change) series.\n\nAttributes:\n    mean: Arithmetic mean of the observations.\n    std: Sample standard deviation (unbiased, ``ddof=1``).\n    skewness: Fisher-Pearson coefficient of skewness (0 for a symmetric sample).\n    kurtosis: Excess kurtosis (Fisher definition, so a normal sample is ~0).\n    n: Number of non-null observations used.\n    t_statistic: t-statistic for the hypothesis ``mean == 0``, i.e.\n        ``mean / (std / sqrt(n))``. ``nan`` when the sample has zero dispersion.",
          "methods": [],
          "fields": [
            {
              "name": "mean",
              "type": "float",
              "default": null
            },
            {
              "name": "std",
              "type": "float",
              "default": null
            },
            {
              "name": "skewness",
              "type": "float",
              "default": null
            },
            {
              "name": "kurtosis",
              "type": "float",
              "default": null
            },
            {
              "name": "n",
              "type": "int",
              "default": null
            },
            {
              "name": "t_statistic",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/stats/descriptive.py",
          "line": 28
        },
        {
          "name": "MeanReversionParams",
          "module": "stats",
          "qualified": "quantvolt.stats.mean_reversion.MeanReversionParams",
          "kind": "class",
          "signature": "MeanReversionParams(long_run_mean: float, reversion_speed: float, volatility: float, half_life: float)",
          "summary": "Estimated Ornstein–Uhlenbeck parameters: mean-reversion speed, long-run level, diffusion volatility and derived half-life..",
          "doc": "Estimated Ornstein–Uhlenbeck parameters: mean-reversion speed, long-run level, diffusion volatility and derived half-life.",
          "methods": [],
          "fields": [
            {
              "name": "long_run_mean",
              "type": "float",
              "default": null
            },
            {
              "name": "reversion_speed",
              "type": "float",
              "default": null
            },
            {
              "name": "volatility",
              "type": "float",
              "default": null
            },
            {
              "name": "half_life",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/stats/mean_reversion.py",
          "line": 25
        },
        {
          "name": "NormalityTestResult",
          "module": "stats",
          "qualified": "quantvolt.stats.normality.NormalityTestResult",
          "kind": "class",
          "signature": "NormalityTestResult(test_type: NormalityTestType, statistic: float, p_value: float, is_normal: bool, acceptance_level: float)",
          "summary": "Result of one normality test, including test identity, statistic, p-value, sample size and reject/do-not-reject conclusion..",
          "doc": "Result of one normality test, including test identity, statistic, p-value, sample size and reject/do-not-reject conclusion.",
          "methods": [],
          "fields": [
            {
              "name": "test_type",
              "type": "NormalityTestType",
              "default": null
            },
            {
              "name": "statistic",
              "type": "float",
              "default": null
            },
            {
              "name": "p_value",
              "type": "float",
              "default": null
            },
            {
              "name": "is_normal",
              "type": "bool",
              "default": null
            },
            {
              "name": "acceptance_level",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/stats/normality.py",
          "line": 47
        },
        {
          "name": "NormalityTestType",
          "module": "stats",
          "qualified": "quantvolt.stats.normality.NormalityTestType",
          "kind": "class",
          "signature": "NormalityTestType()",
          "summary": "Enumeration of supported normality-test procedures and their serialized identifiers..",
          "doc": "Enumeration of supported normality-test procedures and their serialized identifiers.",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "JARQUE_BERA",
              "value": "'jarque_bera'"
            },
            {
              "name": "SHAPIRO_WILK",
              "value": "'shapiro_wilk'"
            },
            {
              "name": "DAGOSTINO_PEARSON",
              "value": "'dagostino'"
            },
            {
              "name": "ANDERSON_DARLING",
              "value": "'anderson'"
            }
          ],
          "source": "src/quantvolt/stats/normality.py",
          "line": 39
        },
        {
          "name": "StationarityResult",
          "module": "stats",
          "qualified": "quantvolt.stats.stationarity.StationarityResult",
          "kind": "class",
          "signature": "StationarityResult(adf_statistic: float, adf_p_value: float, kpss_statistic: float, kpss_p_value: float, is_stationary: bool, samuelson_effect_detected: bool)",
          "summary": "Stationarity-test output containing procedure, statistic, p-value, critical values, sample size and interpreted stationarity conclusion..",
          "doc": "Stationarity-test output containing procedure, statistic, p-value, critical values, sample size and interpreted stationarity conclusion.",
          "methods": [],
          "fields": [
            {
              "name": "adf_statistic",
              "type": "float",
              "default": null
            },
            {
              "name": "adf_p_value",
              "type": "float",
              "default": null
            },
            {
              "name": "kpss_statistic",
              "type": "float",
              "default": null
            },
            {
              "name": "kpss_p_value",
              "type": "float",
              "default": null
            },
            {
              "name": "is_stationary",
              "type": "bool",
              "default": null
            },
            {
              "name": "samuelson_effect_detected",
              "type": "bool",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/stats/stationarity.py",
          "line": 30
        },
        {
          "name": "correlation_matrix",
          "module": "stats",
          "qualified": "quantvolt.stats.correlation.correlation_matrix",
          "kind": "function",
          "signature": "correlation_matrix(price_data: pl.DataFrame, method: Literal['pearson', 'spearman', 'kendall']='pearson') -> pl.DataFrame",
          "summary": "Pairwise correlation across the DataFrame's columns (commodities).",
          "doc": "Pairwise correlation across the DataFrame's columns (commodities).\n\nEach input column is a variable and each row an observation (e.g. a date).\n``method`` selects the estimator by dispatch:\n\n- ``\"pearson\"``  — :func:`numpy.corrcoef` (linear correlation)\n- ``\"spearman\"`` — :func:`scipy.stats.spearmanr` (rank correlation)\n- ``\"kendall\"``  — :func:`scipy.stats.kendalltau` (pairwise rank concordance)\n\nShape convention: the result is the square ``n x n`` matrix returned as a\n:class:`polars.DataFrame` of shape ``(n_vars, n_vars + 1)`` — a leading\n``\"index\"`` string column holds the input column names as row labels, followed\nby one float column per input column (identical names and order). Row ``i`` (and\n``result[\"index\"][i]``) corresponds to input column ``i``. The matrix is\nsymmetric with an exact ``1.0`` diagonal. The input is never mutated.\n\nRaises:\n    ValidationError: if ``price_data`` has fewer than 2 columns or 2 rows, or\n        ``method`` is not one of ``pearson``/``spearman``/``kendall``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/correlation.py",
          "line": 66
        },
        {
          "name": "descriptive_stats",
          "module": "stats",
          "qualified": "quantvolt.stats.descriptive.descriptive_stats",
          "kind": "function",
          "signature": "descriptive_stats(prices: pl.Series) -> DescriptiveStats",
          "summary": "Compute summary statistics of ``prices``.",
          "doc": "Compute summary statistics of ``prices``.\n\nNulls are dropped before any computation; the input series is left unchanged.\n\nArgs:\n    prices: A Polars Series of prices or daily price changes.\n\nReturns:\n    A :class:`DescriptiveStats` with the mean, sample std (``ddof=1``), skewness,\n    excess kurtosis, observation count, and the mean-vs-zero t-statistic.\n\nRaises:\n    ValidationError: If ``prices`` is empty.\n    InsufficientDataError: If fewer than two non-null observations remain (the\n        ``n >= 2`` constraint required to estimate a sample standard deviation).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/descriptive.py",
          "line": 49
        },
        {
          "name": "fit_ou",
          "module": "stats",
          "qualified": "quantvolt.stats.mean_reversion.fit_ou",
          "kind": "function",
          "signature": "fit_ou(price_series: pl.Series, dt: float=1 / 252) -> MeanReversionParams",
          "summary": "Fit an Ornstein-Uhlenbeck process ``dX = kappa*(mu - X) dt + sigma dW`` by OLS.",
          "doc": "Fit an Ornstein-Uhlenbeck process ``dX = kappa*(mu - X) dt + sigma dW`` by OLS.\n\nThe OU SDE has the exact discrete-time solution of an AR(1) process, so regressing\neach observation on its predecessor, ``X_{t+1} = a + b*X_t + eps``, recovers the\ncontinuous-time parameters:\n\n* ``b`` (slope) and ``a`` (intercept) come from OLS of ``X_{t+1}`` on ``X_t``.\n* ``reversion_speed`` ``kappa = -ln(b) / dt`` — valid only for ``b`` in ``(0, 1)``;\n  outside that range the series does not mean-revert (``b <= 0`` has no real log,\n  ``b >= 1`` implies zero/negative reversion), so ``kappa`` cannot be estimated.\n* ``long_run_mean`` ``mu = a / (1 - b)``.\n* ``volatility`` ``sigma = std(residuals) * sqrt(2*kappa / (1 - b**2))``, the standard\n  discrete-time OU estimator that maps the fitted residual dispersion back to the\n  instantaneous diffusion. ``std(residuals)`` is the OLS residual standard error\n  (sum of squares divided by ``n - 2``, the two fitted parameters).\n* ``half_life`` ``= ln(2) / kappa`` — time for a deviation to decay by half.\n\nArgs:\n    price_series: Observed price/level path ``X_t``, in observation order.\n    dt: Time step between consecutive observations (years); defaults to one\n        trading day, ``1/252``.\n\nReturns:\n    The fitted :class:`MeanReversionParams`.\n\nRaises:\n    ValidationError: If ``dt <= 0``.\n    InsufficientDataError: If fewer than three observations are supplied, if the\n        series is constant (no variation to regress on), or if the fitted slope\n        lies outside ``(0, 1)`` so the series is not mean-reverting.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/mean_reversion.py",
          "line": 32
        },
        {
          "name": "moments",
          "module": "stats",
          "qualified": "quantvolt.stats.descriptive.moments",
          "kind": "function",
          "signature": "moments(data: pl.Series, order: int=4) -> dict[int, float]",
          "summary": "Compute central moments about the mean up to ``order``.",
          "doc": "Compute central moments about the mean up to ``order``.\n\nReturns central moments with the population (``1/n``) normalisation:\n``m_k = (1/n) * sum_i (x_i - mean)**k`` for ``k`` in ``1..order``. The first\ncentral moment is ~0 by construction and the second is the population variance.\nNulls are dropped first; the input series is left unchanged.\n\nArgs:\n    data: A Polars Series of observations.\n    order: Highest moment order to compute (default 4, i.e. up to kurtosis).\n\nReturns:\n    A dict mapping each order ``k`` (``1..order``, in ascending order) to its central\n    moment. The dict has exactly ``order`` entries.\n\nRaises:\n    ValidationError: If ``order`` is not >= 1, or if ``data`` is empty.\n    InsufficientDataError: If fewer than two non-null observations remain after\n        dropping nulls (mirroring :func:`descriptive_stats`'s ``n >= 2`` guard) — a\n        single observation gives a well-defined mean but every central moment\n        about it is trivially zero, which would silently look like a real result\n        rather than the near-absence of data it is.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/descriptive.py",
          "line": 92
        },
        {
          "name": "rolling_correlation",
          "module": "stats",
          "qualified": "quantvolt.stats.correlation.rolling_correlation",
          "kind": "function",
          "signature": "rolling_correlation(series_a: pl.Series, series_b: pl.Series, window: int=252) -> pl.Series",
          "summary": "Rolling Pearson correlation of two equal-length series over ``window``.",
          "doc": "Rolling Pearson correlation of two equal-length series over ``window``.\n\nThe window ending at row ``i`` spans rows ``i - window + 1 .. i`` inclusive, so\nthe leading ``window - 1`` entries are null. Returns a series named\n``\"rolling_correlation\"`` of the same length as the inputs. Neither input is\nmutated.\n\nRaises:\n    ValidationError: if the series differ in length, or ``window`` is < 2 or\n        greater than the series length.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/correlation.py",
          "line": 125
        },
        {
          "name": "test_normality",
          "module": "stats",
          "qualified": "quantvolt.stats.normality.test_normality",
          "kind": "function",
          "signature": "test_normality(data: pl.Series, test_type: NormalityTestType=NormalityTestType.JARQUE_BERA, acceptance_level: float=0.05) -> NormalityTestResult",
          "summary": "Test whether ``data`` follows a normal distribution at ``acceptance_level``.",
          "doc": "Test whether ``data`` follows a normal distribution at ``acceptance_level``.\n\nNulls are dropped before testing and the input is never mutated. The test is\nselected from :data:`_TESTS` by ``test_type`` (Strategy dispatch).\n\nArgs:\n    data: Sample to test (a Polars ``Series``); nulls are ignored.\n    test_type: Which normality test to run.\n    acceptance_level: Significance level in ``[0, 1]`` (e.g. ``0.05``).\n\nReturns:\n    A :class:`NormalityTestResult`. For the p-value tests ``is_normal`` is\n    ``p_value > acceptance_level``; for Anderson-Darling ``p_value`` is\n    ``nan`` and ``is_normal`` compares the statistic to the critical value at\n    the significance level closest to ``acceptance_level``.\n\nRaises:\n    ValidationError: If ``acceptance_level`` is outside ``[0, 1]`` or the\n        (null-dropped) sample is empty.\n    InsufficientDataError: If the sample is smaller than the chosen test's\n        minimum size.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/normality.py",
          "line": 133
        },
        {
          "name": "test_stationarity",
          "module": "stats",
          "qualified": "quantvolt.stats.stationarity.test_stationarity",
          "kind": "function",
          "signature": "test_stationarity(price_series: pl.Series, contract_expiry: date, observation_dates: list[date], *, min_observations: int=_MIN_OBSERVATIONS, adf_significance: float=_ADF_REJECT_LEVEL, kpss_significance: float=_KPSS_ACCEPT_LEVEL, adf_regression: str='c', adf_maxlag: int | None=None, adf_autolag: str | None='AIC', kpss_regression: str='c', kpss_nlags: str | int='auto') -> StationarityResult",
          "summary": "Test a price history for a unit root (ADF) and for stationarity (KPSS).",
          "doc": "Test a price history for a unit root (ADF) and for stationarity (KPSS).\n\nThe series is judged stationary only when the ADF test rejects the unit-root\nnull (``adf_p_value < adf_significance``) *and* the KPSS test fails to reject\nthe stationarity null (``kpss_p_value > kpss_significance``) — the two tests\nmust agree.\n\nThe Samuelson effect — return volatility rising as a futures contract nears\nexpiry — is detected by ordering the observations from furthest-from-expiry to\nnearest (using ``observation_dates`` relative to ``contract_expiry``) and\ncomparing the return volatility of the later (near-expiry) half against the\nearlier half; ``True`` when the near-expiry half is more volatile.\n\nArgs:\n    price_series: Observed prices, one per entry in ``observation_dates``.\n    contract_expiry: Expiry date of the contract being sampled; fixes which\n        observations sit closest to expiry.\n    observation_dates: Sampling date of each price, parallel to ``price_series``.\n    min_observations: Minimum number of prices required for ADF/KPSS testing;\n        defaults to ``30`` (below this the statsmodels estimators become\n        unstable).\n    adf_significance: Significance level below which the ADF p-value rejects\n        the unit-root null; defaults to ``0.05``. Must be in ``(0, 1)``.\n    kpss_significance: Significance level above which the KPSS p-value fails\n        to reject the stationarity null; defaults to ``0.05``. Must be in\n        ``(0, 1)``.\n    adf_regression: ``statsmodels.tsa.stattools.adfuller`` regression\n        (trend) specification; defaults to ``\"c\"`` (constant only).\n    adf_maxlag: ``adfuller`` maximum lag; defaults to ``None`` (statsmodels\n        picks a default based on sample size).\n    adf_autolag: ``adfuller`` lag-selection criterion; defaults to ``\"AIC\"``.\n    kpss_regression: ``statsmodels.tsa.stattools.kpss`` regression (trend)\n        specification; defaults to ``\"c\"`` (level stationarity).\n    kpss_nlags: ``kpss`` lag-truncation parameter; defaults to ``\"auto\"``.\n\nReturns:\n    A :class:`StationarityResult` with the ADF/KPSS statistics and p-values,\n    the combined stationarity verdict, and the Samuelson-effect flag.\n\nRaises:\n    ValidationError: If ``price_series`` is empty, its length does not match\n        ``observation_dates``, ``min_observations`` is not strictly positive,\n        or ``adf_significance`` / ``kpss_significance`` is not in ``(0, 1)``.\n    InsufficientDataError: If fewer than ``min_observations`` prices are given.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/stats/stationarity.py",
          "line": 39
        }
      ]
    },
    {
      "name": "market",
      "qualified": "quantvolt.market",
      "description": "Transmission, weather and generation reliability utilities.",
      "symbols": [
        {
          "name": "OutageDataset",
          "module": "market",
          "qualified": "quantvolt.market.outages.OutageDataset",
          "kind": "class",
          "signature": "OutageDataset(records: tuple[OutageRecord, ...])",
          "summary": "An immutable, iterable collection of :class:`OutageRecord` (§22, Req 26.1).",
          "doc": "An immutable, iterable collection of :class:`OutageRecord` (§22, Req 26.1).\n\nRecords are snapshot into a tuple at construction, so the dataset is immutable even\nif the caller passes a list and later mutates it. Each record self-validates, so a\nconstructed dataset holds only valid records. An empty dataset is valid: it denotes a\nperiod with no outages (fully available).\n\nKPI functions treat the dataset as a single reliability context — one unit, or an\naggregate the caller has already scoped to a common ``installed_capacity_mw`` and\n``period_hours``. Records are assumed non-overlapping in time; the factor KPIs clamp\nto ``[0, 1]`` so overlapping or over-period inputs still satisfy Property 73.",
          "methods": [
            {
              "name": "forced_outage_multiplier",
              "signature": "forced_outage_multiplier(self, period_hours: float, installed_capacity_mw: float) -> float",
              "summary": "Per-period available-capacity fraction attributable to forced outages ∈ ``[0, 1]``."
            }
          ],
          "fields": [
            {
              "name": "records",
              "type": "tuple[OutageRecord, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 196
        },
        {
          "name": "OutageRecord",
          "module": "market",
          "qualified": "quantvolt.market.outages.OutageRecord",
          "kind": "class",
          "signature": "OutageRecord(asset_id: str, unit_id: str, technology: str, market_zone: str, outage_id: str, outage_type: OutageType, status: OutageStatus, announcement_time: datetime, start_time: datetime, expected_end_time: datetime, installed_capacity_mw: float, unavailable_capacity_mw: float, available_capacity_mw: float, source: str, revision_number: int, actual_end_time: datetime | None = None, reason_code: str | None = None, reason_text: str | None = None)",
          "summary": "A single outage event — the §22.2 / Req 26.1 schema as an immutable value object.",
          "doc": "A single outage event — the §22.2 / Req 26.1 schema as an immutable value object.\n\nCapacity invariant (Req 26.2, Property 74), validated at construction:\n\n- ``0 <= unavailable_capacity_mw <= installed_capacity_mw``;\n- ``available_capacity_mw == installed_capacity_mw - unavailable_capacity_mw`` within\n  :data:`_CAPACITY_TOL`.\n\nViolations raise :class:`~quantvolt.exceptions.ValidationError` naming the offending\nfield. ``installed_capacity_mw`` must be strictly positive (a generating unit has\ncapacity; this also keeps the per-record derating fraction ``unavailable/installed``\nwell defined). End times must not precede ``start_time`` so :attr:`duration_hours`\nis non-negative.\n\n``is_partial`` and ``is_forced`` from the schema are exposed as derived properties\n(Tell-Don't-Ask) so they can never contradict the stored capacities/type.",
          "methods": [
            {
              "name": "effective_end_time",
              "signature": "effective_end_time(self) -> datetime",
              "summary": "Realised end when known (``actual_end_time``), else the ``expected_end_time``."
            },
            {
              "name": "duration_hours",
              "signature": "duration_hours(self) -> float",
              "summary": "Outage length in hours, ``effective_end_time - start_time``. Non-negative."
            },
            {
              "name": "is_full_outage",
              "signature": "is_full_outage(self) -> bool",
              "summary": "True when essentially all installed capacity is unavailable (full outage)."
            },
            {
              "name": "is_partial",
              "signature": "is_partial(self) -> bool",
              "summary": "True for a derating — some but not all capacity unavailable (§22.2 ``is_partial``)."
            },
            {
              "name": "is_forced",
              "signature": "is_forced(self) -> bool",
              "summary": "True iff this is a ``FORCED`` outage (§22.2 ``is_forced``); other categories (unplanned, planned, maintenance, service) are kept distinct."
            }
          ],
          "fields": [
            {
              "name": "asset_id",
              "type": "str",
              "default": null
            },
            {
              "name": "unit_id",
              "type": "str",
              "default": null
            },
            {
              "name": "technology",
              "type": "str",
              "default": null
            },
            {
              "name": "market_zone",
              "type": "str",
              "default": null
            },
            {
              "name": "outage_id",
              "type": "str",
              "default": null
            },
            {
              "name": "outage_type",
              "type": "OutageType",
              "default": null
            },
            {
              "name": "status",
              "type": "OutageStatus",
              "default": null
            },
            {
              "name": "announcement_time",
              "type": "datetime",
              "default": null
            },
            {
              "name": "start_time",
              "type": "datetime",
              "default": null
            },
            {
              "name": "expected_end_time",
              "type": "datetime",
              "default": null
            },
            {
              "name": "installed_capacity_mw",
              "type": "float",
              "default": null
            },
            {
              "name": "unavailable_capacity_mw",
              "type": "float",
              "default": null
            },
            {
              "name": "available_capacity_mw",
              "type": "float",
              "default": null
            },
            {
              "name": "source",
              "type": "str",
              "default": null
            },
            {
              "name": "revision_number",
              "type": "int",
              "default": null
            },
            {
              "name": "actual_end_time",
              "type": "datetime | None",
              "default": "None"
            },
            {
              "name": "reason_code",
              "type": "str | None",
              "default": "None"
            },
            {
              "name": "reason_text",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 95
        },
        {
          "name": "OutageStatus",
          "module": "market",
          "qualified": "quantvolt.market.outages.OutageStatus",
          "kind": "class",
          "signature": "OutageStatus()",
          "summary": "Outage lifecycle status (§22.2).",
          "doc": "Outage lifecycle status (§22.2).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "ANNOUNCED",
              "value": "'announced'"
            },
            {
              "name": "ACTIVE",
              "value": "'active'"
            },
            {
              "name": "REVISED",
              "value": "'revised'"
            },
            {
              "name": "CANCELLED",
              "value": "'cancelled'"
            },
            {
              "name": "COMPLETED",
              "value": "'completed'"
            }
          ],
          "source": "src/quantvolt/market/outages.py",
          "line": 84
        },
        {
          "name": "OutageType",
          "module": "market",
          "qualified": "quantvolt.market.outages.OutageType",
          "kind": "class",
          "signature": "OutageType()",
          "summary": "Outage category (§22.2). Planned, forced, unplanned, and service events stay distinct and are never silently merged (Req 26.2).",
          "doc": "Outage category (§22.2). Planned, forced, unplanned, and service events stay\ndistinct and are never silently merged (Req 26.2).",
          "methods": [],
          "fields": [],
          "members": [
            {
              "name": "PLANNED",
              "value": "'planned'"
            },
            {
              "name": "FORCED",
              "value": "'forced'"
            },
            {
              "name": "UNPLANNED",
              "value": "'unplanned'"
            },
            {
              "name": "MAINTENANCE",
              "value": "'maintenance'"
            },
            {
              "name": "SERVICE",
              "value": "'service'"
            }
          ],
          "source": "src/quantvolt/market/outages.py",
          "line": 73
        },
        {
          "name": "Pipeline",
          "module": "market",
          "qualified": "quantvolt.market.transmission.Pipeline",
          "kind": "class",
          "signature": "Pipeline(distance: float, tariff: float)",
          "summary": "Gas pipeline description used by transmission utilities, including route identity and capacity assumptions..",
          "doc": "Gas pipeline description used by transmission utilities, including route identity and capacity assumptions.",
          "methods": [],
          "fields": [
            {
              "name": "distance",
              "type": "float",
              "default": null
            },
            {
              "name": "tariff",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/market/transmission.py",
          "line": 16
        },
        {
          "name": "TemperatureData",
          "module": "market",
          "qualified": "quantvolt.market.weather.TemperatureData",
          "kind": "class",
          "signature": "TemperatureData(location: str, day: date, temp_celsius: float, temp_normal: float, base_celsius: float = 18.0)",
          "summary": "A single location/day temperature observation.",
          "doc": "A single location/day temperature observation.\n\n``base_celsius`` is the degree-day base temperature used by\n:attr:`heating_degree_days` / :attr:`cooling_degree_days` (default 18.0 °C, the\nsame default as :func:`degree_days`).",
          "methods": [
            {
              "name": "heating_degree_days",
              "signature": "heating_degree_days(self) -> float",
              "summary": ""
            },
            {
              "name": "cooling_degree_days",
              "signature": "cooling_degree_days(self) -> float",
              "summary": ""
            }
          ],
          "fields": [
            {
              "name": "location",
              "type": "str",
              "default": null
            },
            {
              "name": "day",
              "type": "date",
              "default": null
            },
            {
              "name": "temp_celsius",
              "type": "float",
              "default": null
            },
            {
              "name": "temp_normal",
              "type": "float",
              "default": null
            },
            {
              "name": "base_celsius",
              "type": "float",
              "default": "18.0"
            }
          ],
          "members": [],
          "source": "src/quantvolt/market/weather.py",
          "line": 28
        },
        {
          "name": "availability_factor",
          "module": "market",
          "qualified": "quantvolt.market.outages.availability_factor",
          "kind": "function",
          "signature": "availability_factor(dataset: OutageDataset, period_hours: float) -> float",
          "summary": "Availability Factor ``AF = available_hours / period_hours`` (§22.3, Req 26.3) ∈ ``[0, 1]``.",
          "doc": "Availability Factor ``AF = available_hours / period_hours`` (§22.3, Req 26.3) ∈ ``[0, 1]``.\n\n``available_hours = period_hours - full_outage_hours``, where ``full_outage_hours`` sums\nthe duration of every full outage (any type). Partial deratings leave the unit available\nand so do not reduce ``AF`` — the equivalent (capacity-weighted) loss is captured by\n:func:`equivalent_availability_factor`. Clamped to ``[0, 1]`` (Property 73). ``CANCELLED``\nrecords are excluded (§22.2 lifecycle: a cancelled outage never happened).\n\nRaises:\n    ValidationError: If ``period_hours <= 0``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 313
        },
        {
          "name": "degree_days",
          "module": "market",
          "qualified": "quantvolt.market.weather.degree_days",
          "kind": "function",
          "signature": "degree_days(temperatures: pl.DataFrame, base_celsius: float=18.0) -> pl.DataFrame",
          "summary": "Compute heating- and cooling-degree-days from caller-supplied temperature data.",
          "doc": "Compute heating- and cooling-degree-days from caller-supplied temperature data.\n\nThe library performs no fetching or I/O — temperature data is passed in. Degree days\nfeed load/seasonality analysis and stress-scenario generation downstream.\n\nArgs:\n    temperatures: Frame with columns ``location``, ``date``, ``temp_celsius``.\n    base_celsius: Degree-day base temperature (default 18.0 °C).\n\nReturns:\n    A new frame (input is never mutated) with the input columns plus\n    ``hdd = max(0, base_celsius - temp_celsius)`` and\n    ``cdd = max(0, temp_celsius - base_celsius)``.\n\nRaises:\n    ValidationError: If a required column is missing, or ``temperatures`` is empty.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/weather.py",
          "line": 51
        },
        {
          "name": "efor",
          "module": "market",
          "qualified": "quantvolt.market.outages.efor",
          "kind": "function",
          "signature": "efor(dataset: OutageDataset) -> float",
          "summary": "Equivalent Forced Outage Rate ∈ ``[0, 1]`` (IEEE 762; Req 26.4).",
          "doc": "Equivalent Forced Outage Rate ∈ ``[0, 1]`` (IEEE 762; Req 26.4).\n\nThe capacity-equivalent analog of :func:`forced_outage_rate`: full forced-outage hours\nare replaced by *equivalent* forced-outage hours (each forced event weighted by its\nunavailable fraction ``unavailable/installed``), so a partial (derated) forced outage\ncounts pro-rata rather than at full duration:\n\n    ``EFOR = forced_equiv_hours / (forced_equiv_hours + service_hours)``.\n\nBecause ``forced_equiv_hours <= forced_hours``, ``EFOR <= FOR``; it reduces to ``FOR``\nwhen every forced outage is a full outage. ``SERVICE`` events supply the denominator's\nservice hours (Req 26.3's convention), keeping categories distinct. ``CANCELLED`` records\nare excluded from both terms (§22.2 lifecycle). Returns ``0.0`` for the ``0/0`` case (no\nequivalent-forced and no service exposure).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 367
        },
        {
          "name": "equivalent_availability_factor",
          "module": "market",
          "qualified": "quantvolt.market.outages.equivalent_availability_factor",
          "kind": "function",
          "signature": "equivalent_availability_factor(dataset: OutageDataset, period_hours: float, installed_capacity_mw: float) -> float",
          "summary": "Equivalent Availability Factor (§22.3, Req 26.3) ∈ ``[0, 1]``.",
          "doc": "Equivalent Availability Factor (§22.3, Req 26.3) ∈ ``[0, 1]``.\n\n``EAF = 1 - equivalent_unavailable_capacity_hours / (installed_capacity * period_hours)``,\nwhere ``equivalent_unavailable_capacity_hours`` is :func:`unavailable_energy` (MWh). Unlike\n:func:`availability_factor` this credits partial deratings capacity-for-capacity. Clamped\nto ``[0, 1]`` (Property 73). ``CANCELLED`` records are excluded via :func:`unavailable_energy`\n(§22.2 lifecycle).\n\nRaises:\n    ValidationError: If ``period_hours <= 0`` or ``installed_capacity_mw <= 0``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 329
        },
        {
          "name": "forced_outage_rate",
          "module": "market",
          "qualified": "quantvolt.market.outages.forced_outage_rate",
          "kind": "function",
          "signature": "forced_outage_rate(dataset: OutageDataset) -> float",
          "summary": "Forced Outage Rate ``FOR = forced_hours / (forced_hours + service_hours)`` ∈ ``[0, 1]``.",
          "doc": "Forced Outage Rate ``FOR = forced_hours / (forced_hours + service_hours)`` ∈ ``[0, 1]``.\n\n§22.3 / Req 26.3 / Property 73. ``forced_hours`` sums the duration of ``FORCED`` outages;\n``service_hours`` sums the duration of ``SERVICE`` outages. Categories stay distinct: a\nplanned, unplanned, or maintenance outage never enters this KPI. ``CANCELLED`` records are\nexcluded from both sums (§22.2 lifecycle: a cancelled outage never happened). Returns\n``0.0`` when there is neither forced nor service exposure (documented convention for the\n``0/0`` case).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 349
        },
        {
          "name": "mtbf",
          "module": "market",
          "qualified": "quantvolt.market.outages.mtbf",
          "kind": "function",
          "signature": "mtbf(dataset: OutageDataset, period_hours: float) -> float",
          "summary": "Mean Time Between Failures, in hours (IEEE 762; Req 26.4).",
          "doc": "Mean Time Between Failures, in hours (IEEE 762; Req 26.4).\n\n``MTBF = period_hours / number_of_forced_outages`` — the reciprocal of the forced-outage\n(failure) rate ``λ``, i.e. the mean observation time per forced outage. ``CANCELLED``\nrecords never count as a forced outage (§22.2 lifecycle). Returns ``float('inf')`` when\nthere are no (non-cancelled) forced outages (infinitely long expected time between\nfailures). Consistent with :func:`outage_frequency`: ``outage_frequency = HOURS_PER_YEAR\n/ MTBF``.\n\nRaises:\n    ValidationError: If ``period_hours <= 0``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 405
        },
        {
          "name": "mttr",
          "module": "market",
          "qualified": "quantvolt.market.outages.mttr",
          "kind": "function",
          "signature": "mttr(dataset: OutageDataset) -> float",
          "summary": "Mean Time To Repair, in hours (IEEE 762; Req 26.4).",
          "doc": "Mean Time To Repair, in hours (IEEE 762; Req 26.4).\n\n``MTTR = forced_outage_hours / number_of_forced_outages`` — the average length of a\nforced outage. ``CANCELLED`` records are excluded from both the hours and the count\n(§22.2 lifecycle: a cancelled outage never happened). Returns ``0.0`` when there are no\n(non-cancelled) forced outages (no repair burden; documented convention).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 391
        },
        {
          "name": "outage_frequency",
          "module": "market",
          "qualified": "quantvolt.market.outages.outage_frequency",
          "kind": "function",
          "signature": "outage_frequency(dataset: OutageDataset, period_hours: float, *, hours_per_year: float=HOURS_PER_YEAR) -> float",
          "summary": "Forced-outage frequency, annualized to events per year (IEEE 762; Req 26.4).",
          "doc": "Forced-outage frequency, annualized to events per year (IEEE 762; Req 26.4).\n\n``f = number_of_forced_outages * hours_per_year / period_hours`` — the failure rate ``λ``\nexpressed per year. ``CANCELLED`` records never count as a forced outage (§22.2\nlifecycle). Zero when there are no (non-cancelled) forced outages. Consistent with\n:func:`mtbf`: ``f = hours_per_year / MTBF``.\n\nArgs:\n    dataset: The outage dataset.\n    period_hours: Length of the observation period in hours. Must be ``> 0``.\n    hours_per_year: Reference hours used to annualize the frequency (default\n        :data:`HOURS_PER_YEAR`, ``8760.0``, a non-leap year). Must be ``> 0``.\n\nRaises:\n    ValidationError: If ``period_hours <= 0`` or ``hours_per_year <= 0``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 425
        },
        {
          "name": "transmission_cost",
          "module": "market",
          "qualified": "quantvolt.market.transmission.transmission_cost",
          "kind": "function",
          "signature": "transmission_cost(pipeline: Pipeline, volume: float) -> float",
          "summary": "Total transmission cost = tariff * volume (Property 38: deterministic, non-negative).",
          "doc": "Total transmission cost = tariff * volume (Property 38: deterministic, non-negative).\n\nArgs:\n    pipeline: The pipeline whose tariff applies (validated at construction).\n    volume: Volume transported, in the tariff's volume unit (e.g. MWh).\n\nReturns:\n    The total cost, ``pipeline.tariff * volume``. Non-negative by construction.\n\nRaises:\n    ValidationError: If ``volume`` is negative.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/transmission.py",
          "line": 25
        },
        {
          "name": "unavailable_energy",
          "module": "market",
          "qualified": "quantvolt.market.outages.unavailable_energy",
          "kind": "function",
          "signature": "unavailable_energy(dataset: OutageDataset) -> float",
          "summary": "Unavailable energy in MWh (IEEE 762 equivalent unavailable capacity-hours; Req 26.4).",
          "doc": "Unavailable energy in MWh (IEEE 762 equivalent unavailable capacity-hours; Req 26.4).\n\n``Σ unavailable_capacity_mw * duration_hours`` over every non-``CANCELLED`` record\n(partial and full; §22.2 lifecycle — a cancelled outage never happened). This is the\n``equivalent_unavailable_capacity_hours`` term used by\n:func:`equivalent_availability_factor`. Non-negative.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/market/outages.py",
          "line": 449
        }
      ]
    },
    {
      "name": "workflow",
      "qualified": "quantvolt.workflow",
      "description": "Criteria-driven model selection for structured products.",
      "symbols": [
        {
          "name": "ConsistencyReport",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.ConsistencyReport",
          "kind": "class",
          "signature": "ConsistencyReport(consistent: bool, discrepancy_pct: float)",
          "summary": "Step 6 output: are the residual model and the static hedges consistent.",
          "doc": "Step 6 output: are the residual model and the static hedges consistent.",
          "methods": [],
          "fields": [
            {
              "name": "consistent",
              "type": "bool",
              "default": null
            },
            {
              "name": "discrepancy_pct",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 134
        },
        {
          "name": "DataSufficiencyReport",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.DataSufficiencyReport",
          "kind": "class",
          "signature": "DataSufficiencyReport(sufficient: bool, approximations: tuple[str, ...], trader_inputs_required: tuple[str, ...])",
          "summary": "Step 5 output: is the data good enough, and if not, what fills the gap.",
          "doc": "Step 5 output: is the data good enough, and if not, what fills the gap.",
          "methods": [],
          "fields": [
            {
              "name": "sufficient",
              "type": "bool",
              "default": null
            },
            {
              "name": "approximations",
              "type": "tuple[str, ...]",
              "default": null
            },
            {
              "name": "trader_inputs_required",
              "type": "tuple[str, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 125
        },
        {
          "name": "ModelingWorkflow",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.ModelingWorkflow",
          "kind": "class",
          "signature": "ModelingWorkflow()",
          "summary": "Steps run 1 -> 2 -> 3 -> 4 -> 5 -> (6 -> 3 loop) -> 7 (Property 40).",
          "doc": "Steps run 1 -> 2 -> 3 -> 4 -> 5 -> (6 -> 3 loop) -> 7 (Property 40).",
          "methods": [
            {
              "name": "run",
              "signature": "run(self, product: StructuredProduct, criteria: ModelSelectionCriteria | None=None, steps: WorkflowSteps | None=None, max_consistency_loops: int=3, tolerance: float=0.01) -> WorkflowResult",
              "summary": "Execute the fixed 7-step skeleton over the injected step callables."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 293
        },
        {
          "name": "ModelSelectionCriteria",
          "module": "workflow",
          "qualified": "quantvolt.workflow.criteria.ModelSelectionCriteria",
          "kind": "class",
          "signature": "ModelSelectionCriteria(min_observations: int = 252, max_missing_pct: float = 0.05, min_r_squared: float = 0.7, max_rmse_pct: float = 0.1, max_parameter_drift: float = 0.2, require_risk_factor_separation: bool = True)",
          "summary": "Thresholds the 7-step modeling workflow applies when accepting a residual model.",
          "doc": "Thresholds the 7-step modeling workflow applies when accepting a residual model.\n\nAttributes:\n    min_observations: Minimum history length (observations) a residual model must be\n        fitted on. Must be >= 1.\n    max_missing_pct: Maximum tolerated fraction of missing data, in [0, 1].\n    min_r_squared: Minimum acceptable model fit (R-squared), in [0, 1].\n    max_rmse_pct: Maximum acceptable RMSE as a fraction of price level, in [0, 1].\n    max_parameter_drift: Maximum tolerated parameter change over a rolling window,\n        as a fraction, in [0, 1].\n    require_risk_factor_separation: When True, ``ModelingWorkflow.run`` fails loudly\n        if any model-independent risk factor is left without a static hedge\n        (Property 41); when False the result merely records the failure.",
          "methods": [],
          "fields": [
            {
              "name": "min_observations",
              "type": "int",
              "default": "252"
            },
            {
              "name": "max_missing_pct",
              "type": "float",
              "default": "0.05"
            },
            {
              "name": "min_r_squared",
              "type": "float",
              "default": "0.7"
            },
            {
              "name": "max_rmse_pct",
              "type": "float",
              "default": "0.1"
            },
            {
              "name": "max_parameter_drift",
              "type": "float",
              "default": "0.2"
            },
            {
              "name": "require_risk_factor_separation",
              "type": "bool",
              "default": "True"
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/criteria.py",
          "line": 11
        },
        {
          "name": "QualitativeAnalysis",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.QualitativeAnalysis",
          "kind": "class",
          "signature": "QualitativeAnalysis(structural_features: tuple[str, ...], risk_factors: tuple[str, ...])",
          "summary": "Step 1 output: structural features and the product's risk factors.",
          "doc": "Step 1 output: structural features and the product's risk factors.",
          "methods": [],
          "fields": [
            {
              "name": "structural_features",
              "type": "tuple[str, ...]",
              "default": null
            },
            {
              "name": "risk_factors",
              "type": "tuple[str, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 78
        },
        {
          "name": "ResidualAnalysis",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.ResidualAnalysis",
          "kind": "class",
          "signature": "ResidualAnalysis(unhedged_risk_factors: tuple[str, ...], residual_variance_pct: float)",
          "summary": "Step 3 output: what remains after the static hedges.",
          "doc": "Step 3 output: what remains after the static hedges.",
          "methods": [],
          "fields": [
            {
              "name": "unhedged_risk_factors",
              "type": "tuple[str, ...]",
              "default": null
            },
            {
              "name": "residual_variance_pct",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 101
        },
        {
          "name": "ResidualModel",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.ResidualModel",
          "kind": "class",
          "signature": "ResidualModel(modelled_factors: tuple[str, ...], r_squared: float, observation_count: int)",
          "summary": "Step 4 output: the fitted model of the residual.",
          "doc": "Step 4 output: the fitted model of the residual.",
          "methods": [],
          "fields": [
            {
              "name": "modelled_factors",
              "type": "tuple[str, ...]",
              "default": null
            },
            {
              "name": "r_squared",
              "type": "float",
              "default": null
            },
            {
              "name": "observation_count",
              "type": "int",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 112
        },
        {
          "name": "StaticHedge",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.StaticHedge",
          "kind": "class",
          "signature": "StaticHedge(instrument_kind: str, risk_factor: str, hedge_ratio: float)",
          "summary": "Step 2 output: one model-independent hedge (forward/swap) per risk factor.",
          "doc": "Step 2 output: one model-independent hedge (forward/swap) per risk factor.",
          "methods": [],
          "fields": [
            {
              "name": "instrument_kind",
              "type": "str",
              "default": null
            },
            {
              "name": "risk_factor",
              "type": "str",
              "default": null
            },
            {
              "name": "hedge_ratio",
              "type": "float",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 86
        },
        {
          "name": "StructuredProduct",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.StructuredProduct",
          "kind": "class",
          "signature": "StructuredProduct(name: str, payoff_description: str, risk_factors: tuple[str, ...])",
          "summary": "The minimal product description the workflow needs.",
          "doc": "The minimal product description the workflow needs.",
          "methods": [],
          "fields": [
            {
              "name": "name",
              "type": "str",
              "default": null
            },
            {
              "name": "payoff_description",
              "type": "str",
              "default": null
            },
            {
              "name": "risk_factors",
              "type": "tuple[str, ...]",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 64
        },
        {
          "name": "WorkflowResult",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.WorkflowResult",
          "kind": "class",
          "signature": "WorkflowResult(price: float | None, hedges: tuple[StaticHedge, ...], residual_model: ResidualModel | None, data_report: DataSufficiencyReport, steps_executed: tuple[int, ...], risk_factor_separation_achieved: bool)",
          "summary": "Final output of :meth:`ModelingWorkflow.run`.",
          "doc": "Final output of :meth:`ModelingWorkflow.run`.\n\n``price`` and ``residual_model`` are None when step 5 reported insufficient data:\nthe workflow still completes with the static hedges in place, and the unmodelled\nresidual is left for trader judgment (Property 41).",
          "methods": [],
          "fields": [
            {
              "name": "price",
              "type": "float | None",
              "default": null
            },
            {
              "name": "hedges",
              "type": "tuple[StaticHedge, ...]",
              "default": null
            },
            {
              "name": "residual_model",
              "type": "ResidualModel | None",
              "default": null
            },
            {
              "name": "data_report",
              "type": "DataSufficiencyReport",
              "default": null
            },
            {
              "name": "steps_executed",
              "type": "tuple[int, ...]",
              "default": null
            },
            {
              "name": "risk_factor_separation_achieved",
              "type": "bool",
              "default": null
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 145
        },
        {
          "name": "WorkflowSteps",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.WorkflowSteps",
          "kind": "class",
          "signature": "WorkflowSteps(step1: Step1 = step1_qualitative_properties, step2: Step2 = step2_static_hedges, step3: Step3 = step3_residual_investigation, step4: Step4 = step4_model_residual, step5: Step5 = step5_data_check, step6: Step6 = step6_consistency_check, step7: Step7 = step7_price_and_hedge)",
          "summary": "The seven injected step callables (Template Method via injection, not inheritance).",
          "doc": "The seven injected step callables (Template Method via injection, not inheritance).\n\nEvery field defaults to the module-level default step, so ``WorkflowSteps()`` is the\nout-of-the-box process and ``WorkflowSteps(step5=my_check)`` overrides exactly one step.",
          "methods": [],
          "fields": [
            {
              "name": "step1",
              "type": "Step1",
              "default": "step1_qualitative_properties"
            },
            {
              "name": "step2",
              "type": "Step2",
              "default": "step2_static_hedges"
            },
            {
              "name": "step3",
              "type": "Step3",
              "default": "step3_residual_investigation"
            },
            {
              "name": "step4",
              "type": "Step4",
              "default": "step4_model_residual"
            },
            {
              "name": "step5",
              "type": "Step5",
              "default": "step5_data_check"
            },
            {
              "name": "step6",
              "type": "Step6",
              "default": "step6_consistency_check"
            },
            {
              "name": "step7",
              "type": "Step7",
              "default": "step7_price_and_hedge"
            }
          ],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 274
        },
        {
          "name": "DEFAULT_STEPS",
          "module": "workflow",
          "qualified": "quantvolt.workflow.modeling.DEFAULT_STEPS",
          "kind": "constant",
          "signature": "DEFAULT_STEPS",
          "summary": "Ordered seven-step model-selection workflow used when ModelingWorkflow is constructed without caller overrides..",
          "doc": "Ordered seven-step model-selection workflow used when ModelingWorkflow is constructed without caller overrides.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/workflow/modeling.py",
          "line": 1
        }
      ]
    },
    {
      "name": "data",
      "qualified": "quantvolt.data",
      "description": "Optional provider adapters and reproducible data snapshots.",
      "symbols": [
        {
          "name": "AuthenticationError",
          "module": "data",
          "qualified": "quantvolt.exceptions.AuthenticationError",
          "kind": "class",
          "signature": "AuthenticationError()",
          "summary": "Provider credential is missing or rejected (the value is never included).",
          "doc": "Provider credential is missing or rejected (the value is never included).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 59
        },
        {
          "name": "Credentials",
          "module": "data",
          "qualified": "quantvolt.data.base.Credentials",
          "kind": "class",
          "signature": "Credentials(token: str | None = None, api_key: str | None = None)",
          "summary": "Caller-owned API keys. Never persisted or logged; redacted in repr.",
          "doc": "Caller-owned API keys. Never persisted or logged; redacted in repr.\n\nResolution order (Req 12.3): an explicitly constructed ``Credentials`` object always wins;\n:meth:`from_env` is the documented environment-variable fallback. Credentials are read\nfrom nowhere else.",
          "methods": [
            {
              "name": "from_env",
              "signature": "from_env(cls, provider: str) -> Credentials",
              "summary": "Read ``QUANTVOLT_<PROVIDER>_TOKEN`` from the environment the caller set."
            },
            {
              "name": "require_token",
              "signature": "require_token(self, provider: str) -> str",
              "summary": "Return the configured secret (``token``, else ``api_key``) or raise."
            }
          ],
          "fields": [
            {
              "name": "token",
              "type": "str | None",
              "default": "None"
            },
            {
              "name": "api_key",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/data/base.py",
          "line": 55
        },
        {
          "name": "DataSource",
          "module": "data",
          "qualified": "quantvolt.data.base.DataSource",
          "kind": "class",
          "signature": "DataSource()",
          "summary": "An adapter implements only the methods its provider actually supports.",
          "doc": "An adapter implements only the methods its provider actually supports.\n\nFree adapters (ENTSO-E, ENTSOG, Open-Meteo) provide spot/day-ahead prices, fundamentals,\nand weather; ``forward_curve`` is implemented **only** by commercial adapters or replaced\nby caller-supplied curves (Req 12.8).",
          "methods": [
            {
              "name": "forward_curve",
              "signature": "forward_curve(self, commodity: CommodityConfig, market_date: date) -> ForwardCurve",
              "summary": ""
            },
            {
              "name": "price_series",
              "signature": "price_series(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series",
              "summary": ""
            },
            {
              "name": "temperatures",
              "signature": "temperatures(self, location: str, start: date, end: date) -> pl.DataFrame",
              "summary": ""
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/base.py",
          "line": 130
        },
        {
          "name": "DataSourceError",
          "module": "data",
          "qualified": "quantvolt.exceptions.DataSourceError",
          "kind": "class",
          "signature": "DataSourceError()",
          "summary": "A quantvolt[data] provider fetch failed.",
          "doc": "A quantvolt[data] provider fetch failed.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 55
        },
        {
          "name": "DataUnavailableError",
          "module": "data",
          "qualified": "quantvolt.exceptions.DataUnavailableError",
          "kind": "class",
          "signature": "DataUnavailableError()",
          "summary": "Provider returned no data for the requested query.",
          "doc": "Provider returned no data for the requested query.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 67
        },
        {
          "name": "EexSource",
          "module": "data",
          "qualified": "quantvolt.data.commercial.EexSource",
          "kind": "class",
          "signature": "EexSource()",
          "summary": "EEX Group market data: power/gas futures curves, EUA and settlement prices.",
          "doc": "EEX Group market data: power/gas futures curves, EUA and settlement prices.\n\nRequires a paid EEX Group data subscription. Configure ``Credentials(api_key=...)`` or\n``QUANTVOLT_EEX_TOKEN``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/commercial.py",
          "line": 68
        },
        {
          "name": "EntsoeSource",
          "module": "data",
          "qualified": "quantvolt.data.entsoe.EntsoeSource",
          "kind": "class",
          "signature": "EntsoeSource(credentials: Credentials | None=None, transport: httpx.BaseTransport | None=None, *, base_url: str=_BASE_URL, timeout_seconds: float=_TIMEOUT_SECONDS, max_retries: int=0, backoff_seconds: float=1.0, bidding_zone_overrides: Mapping[str, str] | None=None, timezone_overrides: Mapping[str, str] | None=None)",
          "summary": "Free-token ENTSO-E adapter: day-ahead prices, load, and generation as ``pl.Series``.",
          "doc": "Free-token ENTSO-E adapter: day-ahead prices, load, and generation as ``pl.Series``.\n\nNo ``forward_curve`` method — free sources are never forward-curve sources (Req 12.8).",
          "methods": [
            {
              "name": "price_series",
              "signature": "price_series(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series",
              "summary": "Day-ahead prices (document ``A44``) for ``[start, end)`` as a float series."
            },
            {
              "name": "price_frame",
              "signature": "price_frame(self, commodity: CommodityConfig, start: date, end: date) -> pl.DataFrame",
              "summary": "Day-ahead prices with exact UTC delivery starts, ends, and durations."
            },
            {
              "name": "load",
              "signature": "load(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series",
              "summary": "Actual total load (document ``A65``, process ``A16``) as a float series."
            },
            {
              "name": "load_frame",
              "signature": "load_frame(self, commodity: CommodityConfig, start: date, end: date) -> pl.DataFrame",
              "summary": "Actual total load with exact UTC delivery intervals."
            },
            {
              "name": "generation",
              "signature": "generation(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series",
              "summary": "Actual aggregated generation (document ``A75``, process ``A16``) as a float series."
            },
            {
              "name": "generation_frame",
              "signature": "generation_frame(self, commodity: CommodityConfig, start: date, end: date) -> pl.DataFrame",
              "summary": "Actual generation with intervals and source TimeSeries identity preserved."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/entsoe.py",
          "line": 290
        },
        {
          "name": "EntsogSource",
          "module": "data",
          "qualified": "quantvolt.data.entsog.EntsogSource",
          "kind": "class",
          "signature": "EntsogSource(credentials: Credentials | None=None, transport: httpx.BaseTransport | None=None, *, base_url: str=_BASE_URL, timeout_seconds: float=_TIMEOUT_SECONDS, max_retries: int=0, backoff_seconds: float=1.0)",
          "summary": "Keyless ENTSOG adapter: daily physical gas flows as a ``pl.DataFrame``.",
          "doc": "Keyless ENTSOG adapter: daily physical gas flows as a ``pl.DataFrame``.\n\nNo ``forward_curve`` method — free sources are never forward-curve sources (Req 12.8).",
          "methods": [
            {
              "name": "flows",
              "signature": "flows(self, point_key: str, start: date, end: date, direction: str='entry', *, period_type: str='day', indicator: str='Physical Flow', limit: int=-1) -> pl.DataFrame",
              "summary": "Daily physical flows at network point ``point_key`` over ``[start, end]``."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/entsog.py",
          "line": 37
        },
        {
          "name": "EpexSource",
          "module": "data",
          "qualified": "quantvolt.data.commercial.EpexSource",
          "kind": "class",
          "signature": "EpexSource()",
          "summary": "EPEX SPOT market data beyond the free transparency feeds.",
          "doc": "EPEX SPOT market data beyond the free transparency feeds.\n\nRequires a paid EPEX SPOT data agreement. Configure ``Credentials(api_key=...)`` or\n``QUANTVOLT_EPEX_TOKEN``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/commercial.py",
          "line": 90
        },
        {
          "name": "IceSource",
          "module": "data",
          "qualified": "quantvolt.data.commercial.IceSource",
          "kind": "class",
          "signature": "IceSource()",
          "summary": "ICE Endex market data: TTF/NBP gas futures curves, EUA and settlement prices.",
          "doc": "ICE Endex market data: TTF/NBP gas futures curves, EUA and settlement prices.\n\nRequires a paid ICE data licence. Configure ``Credentials(api_key=...)`` or\n``QUANTVOLT_ICE_TOKEN``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/commercial.py",
          "line": 79
        },
        {
          "name": "LsegSource",
          "module": "data",
          "qualified": "quantvolt.data.commercial.LsegSource",
          "kind": "class",
          "signature": "LsegSource()",
          "summary": "LSEG (Refinitiv) market data: broker forward curves and settlement prices.",
          "doc": "LSEG (Refinitiv) market data: broker forward curves and settlement prices.\n\nRequires a paid LSEG/Refinitiv subscription. Configure ``Credentials(api_key=...)`` or\n``QUANTVOLT_LSEG_TOKEN``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/commercial.py",
          "line": 112
        },
        {
          "name": "NetztransparenzSource",
          "module": "data",
          "qualified": "quantvolt.data.netztransparenz.NetztransparenzSource",
          "kind": "class",
          "signature": "NetztransparenzSource(credentials: OAuthClientCredentials | None=None, transport: httpx.BaseTransport | None=None, *, token_url: str=_TOKEN_URL, rebap_url: str=_REBAP_URL, timeout_seconds: float=30.0, max_retries: int=0, backoff_seconds: float=1.0)",
          "summary": "OAuth-authenticated source for quality-assured German reBAP prices.",
          "doc": "OAuth-authenticated source for quality-assured German reBAP prices.",
          "methods": [
            {
              "name": "rebap",
              "signature": "rebap(self, start: datetime, end: datetime) -> pl.DataFrame",
              "summary": "Fetch quality-assured reBAP intervals whose starts lie in ``[start, end)``."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/netztransparenz.py",
          "line": 175
        },
        {
          "name": "NordPoolSource",
          "module": "data",
          "qualified": "quantvolt.data.commercial.NordPoolSource",
          "kind": "class",
          "signature": "NordPoolSource()",
          "summary": "Nord Pool market data: Nordic/Baltic curves and settlement prices.",
          "doc": "Nord Pool market data: Nordic/Baltic curves and settlement prices.\n\nRequires a paid Nord Pool data licence. Configure ``Credentials(api_key=...)`` or\n``QUANTVOLT_NORDPOOL_TOKEN``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/commercial.py",
          "line": 101
        },
        {
          "name": "OAuthClientCredentials",
          "module": "data",
          "qualified": "quantvolt.data.base.OAuthClientCredentials",
          "kind": "class",
          "signature": "OAuthClientCredentials(client_id: str | None = None, client_secret: str | None = None)",
          "summary": "Caller-owned OAuth 2 client credentials, always redacted in text output.",
          "doc": "Caller-owned OAuth 2 client credentials, always redacted in text output.",
          "methods": [
            {
              "name": "from_env",
              "signature": "from_env(cls, provider: str) -> OAuthClientCredentials",
              "summary": "Read the provider's documented client-id and client-secret variables."
            },
            {
              "name": "require",
              "signature": "require(self, provider: str) -> tuple[str, str]",
              "summary": "Return both OAuth values or raise without exposing either value."
            }
          ],
          "fields": [
            {
              "name": "client_id",
              "type": "str | None",
              "default": "None"
            },
            {
              "name": "client_secret",
              "type": "str | None",
              "default": "None"
            }
          ],
          "members": [],
          "source": "src/quantvolt/data/base.py",
          "line": 96
        },
        {
          "name": "OpenMeteoSource",
          "module": "data",
          "qualified": "quantvolt.data.open_meteo.OpenMeteoSource",
          "kind": "class",
          "signature": "OpenMeteoSource(credentials: Credentials | None=None, transport: httpx.BaseTransport | None=None, *, base_url: str=_BASE_URL, timeout_seconds: float=_TIMEOUT_SECONDS, max_retries: int=0, backoff_seconds: float=1.0, daily_variable: str='temperature_2m_mean', timezone: str='UTC')",
          "summary": "Keyless Open-Meteo adapter: daily mean temperatures as a ``pl.DataFrame``.",
          "doc": "Keyless Open-Meteo adapter: daily mean temperatures as a ``pl.DataFrame``.\n\nNo ``forward_curve`` method — free sources are never forward-curve sources (Req 12.8).",
          "methods": [
            {
              "name": "temperatures",
              "signature": "temperatures(self, location: str, start: date, end: date) -> pl.DataFrame",
              "summary": "Daily mean temperatures for ``location`` (``\"lat,lon\"``) over ``[start, end]``."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/open_meteo.py",
          "line": 56
        },
        {
          "name": "RateLimitError",
          "module": "data",
          "qualified": "quantvolt.exceptions.RateLimitError",
          "kind": "class",
          "signature": "RateLimitError()",
          "summary": "Provider rate limit exceeded.",
          "doc": "Provider rate limit exceeded.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 63
        },
        {
          "name": "SmardResolution",
          "module": "data",
          "qualified": "quantvolt.data.smard.SmardResolution",
          "kind": "class",
          "signature": "SmardResolution()",
          "summary": "Resolutions used by the SMARD chart-data endpoint.",
          "doc": "Resolutions used by the SMARD chart-data endpoint.",
          "methods": [
            {
              "name": "minutes",
              "signature": "minutes(self) -> int",
              "summary": ""
            }
          ],
          "fields": [],
          "members": [
            {
              "name": "HOURLY",
              "value": "'hour'"
            },
            {
              "name": "QUARTER_HOURLY",
              "value": "'quarterhour'"
            }
          ],
          "source": "src/quantvolt/data/smard.py",
          "line": 33
        },
        {
          "name": "SmardSource",
          "module": "data",
          "qualified": "quantvolt.data.smard.SmardSource",
          "kind": "class",
          "signature": "SmardSource(transport: httpx.BaseTransport | None=None, *, base_url: str=_BASE_URL, bidding_zone: str=_DEFAULT_ZONE, timeout_seconds: float=30.0, max_retries: int=0, backoff_seconds: float=1.0)",
          "summary": "Public SMARD adapter for timestamped German day-ahead prices.",
          "doc": "Public SMARD adapter for timestamped German day-ahead prices.",
          "methods": [
            {
              "name": "prices",
              "signature": "prices(self, start: datetime, end: datetime, resolution: SmardResolution=SmardResolution.HOURLY) -> pl.DataFrame",
              "summary": "Return day-ahead prices overlapping ``[start, end)`` at one resolution."
            },
            {
              "name": "native_prices",
              "signature": "native_prices(self, start: datetime, end: datetime) -> pl.DataFrame",
              "summary": "Return native hourly then native quarter-hour products across the 2025 boundary."
            }
          ],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/smard.py",
          "line": 118
        },
        {
          "name": "attach_rebap_prices",
          "module": "data",
          "qualified": "quantvolt.data.netztransparenz.attach_rebap_prices",
          "kind": "function",
          "signature": "attach_rebap_prices(data: pl.DataFrame, rebap: pl.DataFrame, *, interval_start_column: str='interval_start_utc', interval_end_column: str='interval_end_utc') -> pl.DataFrame",
          "summary": "Attach reBAP prices by exact interval keys; reject every unpriced caller row.",
          "doc": "Attach reBAP prices by exact interval keys; reject every unpriced caller row.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/netztransparenz.py",
          "line": 136
        },
        {
          "name": "parse_rebap_csv",
          "module": "data",
          "qualified": "quantvolt.data.netztransparenz.parse_rebap_csv",
          "kind": "function",
          "signature": "parse_rebap_csv(text: str) -> pl.DataFrame",
          "summary": "Parse official Format 9 CSV into exact UTC quarter-hour settlement prices.",
          "doc": "Parse official Format 9 CSV into exact UTC quarter-hour settlement prices.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/netztransparenz.py",
          "line": 56
        },
        {
          "name": "restore",
          "module": "data",
          "qualified": "quantvolt.data.base.restore",
          "kind": "function",
          "signature": "restore(data: dict[str, Any]) -> ForwardCurve",
          "summary": "Rebuild a :class:`ForwardCurve` from a :func:`snapshot` dict (Req 12.7).",
          "doc": "Rebuild a :class:`ForwardCurve` from a :func:`snapshot` dict (Req 12.7).\n\n``restore(snapshot(curve)) == curve``, so re-running analytics from a stored snapshot\nreproduces identical results.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/base.py",
          "line": 160
        },
        {
          "name": "snapshot",
          "module": "data",
          "qualified": "quantvolt.data.base.snapshot",
          "kind": "function",
          "signature": "snapshot(obj: _SupportsToDict) -> dict[str, Any]",
          "summary": "Serialise a fetched value object to a JSON-friendly snapshot (Req 12.7).",
          "doc": "Serialise a fetched value object to a JSON-friendly snapshot (Req 12.7).\n\nThe fetch itself is non-deterministic (live data), but a persisted snapshot makes every\ndownstream analytic reproducible: :func:`restore` rebuilds an equal value object, and the\ncore's determinism (Req 11.2) guarantees identical results from identical inputs.\nSnapshots contain only market data — never credentials.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/data/base.py",
          "line": 149
        }
      ]
    },
    {
      "name": "exceptions",
      "qualified": "quantvolt.exceptions",
      "description": "Public exception hierarchy and actionable failure categories.",
      "symbols": [
        {
          "name": "ArbitrageError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.ArbitrageError",
          "kind": "class",
          "signature": "ArbitrageError()",
          "summary": "Curve contains arbitrage violations that cannot be identified.",
          "doc": "Curve contains arbitrage violations that cannot be identified.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 34
        },
        {
          "name": "AuthenticationError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.AuthenticationError",
          "kind": "class",
          "signature": "AuthenticationError()",
          "summary": "Provider credential is missing or rejected (the value is never included).",
          "doc": "Provider credential is missing or rejected (the value is never included).",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 59
        },
        {
          "name": "DataSourceError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.DataSourceError",
          "kind": "class",
          "signature": "DataSourceError()",
          "summary": "A quantvolt[data] provider fetch failed.",
          "doc": "A quantvolt[data] provider fetch failed.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 55
        },
        {
          "name": "DataUnavailableError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.DataUnavailableError",
          "kind": "class",
          "signature": "DataUnavailableError()",
          "summary": "Provider returned no data for the requested query.",
          "doc": "Provider returned no data for the requested query.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 67
        },
        {
          "name": "EnergyQuantError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.EnergyQuantError",
          "kind": "class",
          "signature": "EnergyQuantError()",
          "summary": "Base class for all library-raised exceptions.",
          "doc": "Base class for all library-raised exceptions.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 7
        },
        {
          "name": "ExpiredContractError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.ExpiredContractError",
          "kind": "class",
          "signature": "ExpiredContractError()",
          "summary": "Contract delivery period is entirely in the past.",
          "doc": "Contract delivery period is entirely in the past.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 42
        },
        {
          "name": "InsufficientDataError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.InsufficientDataError",
          "kind": "class",
          "signature": "InsufficientDataError()",
          "summary": "Input data does not satisfy minimum requirements for an operation.",
          "doc": "Input data does not satisfy minimum requirements for an operation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 30
        },
        {
          "name": "MissingTenorError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.MissingTenorError",
          "kind": "class",
          "signature": "MissingTenorError()",
          "summary": "Discount curve or volatility surface does not cover a required date.",
          "doc": "Discount curve or volatility surface does not cover a required date.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 46
        },
        {
          "name": "NativeExtensionError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.NativeExtensionError",
          "kind": "class",
          "signature": "NativeExtensionError()",
          "summary": "A requested native Monte Carlo kernel is unavailable in this installation.",
          "doc": "A requested native Monte Carlo kernel is unavailable in this installation.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 26
        },
        {
          "name": "NoPricingDataError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.NoPricingDataError",
          "kind": "class",
          "signature": "NoPricingDataError()",
          "summary": "Neither settlement price nor forward curve price is available.",
          "doc": "Neither settlement price nor forward curve price is available.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 38
        },
        {
          "name": "NumericalError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.NumericalError",
          "kind": "class",
          "signature": "NumericalError()",
          "summary": "A numerical kernel's mathematical precondition or convergence condition failed.",
          "doc": "A numerical kernel's mathematical precondition or convergence condition failed.\n\n``ValueError`` is retained as a secondary base for compatibility with callers that use\nthe low-level :mod:`quantvolt.numerics` API directly.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 18
        },
        {
          "name": "RateLimitError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.RateLimitError",
          "kind": "class",
          "signature": "RateLimitError()",
          "summary": "Provider rate limit exceeded.",
          "doc": "Provider rate limit exceeded.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 63
        },
        {
          "name": "ScenarioNotFoundError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.ScenarioNotFoundError",
          "kind": "class",
          "signature": "ScenarioNotFoundError()",
          "summary": "Named scenario is not in the built-in scenario catalogue.",
          "doc": "Named scenario is not in the built-in scenario catalogue.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 50
        },
        {
          "name": "ValidationError",
          "module": "exceptions",
          "qualified": "quantvolt.exceptions.ValidationError",
          "kind": "class",
          "signature": "ValidationError()",
          "summary": "Input parameter violates a documented constraint.",
          "doc": "Input parameter violates a documented constraint.\n\n``ValueError`` is retained as a secondary base for conventional Python compatibility.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/exceptions.py",
          "line": 11
        }
      ]
    },
    {
      "name": "testing",
      "qualified": "quantvolt.testing",
      "description": "Utilities for verifying QuantVolt's non-mutation contract.",
      "symbols": [
        {
          "name": "assert_input_unchanged",
          "module": "testing",
          "qualified": "quantvolt.testing.assert_input_unchanged",
          "kind": "function",
          "signature": "assert_input_unchanged(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R",
          "summary": "Call ``func`` and assert it did not mutate any of its inputs; return its result.",
          "doc": "Call ``func`` and assert it did not mutate any of its inputs; return its result.\n\nA deep copy of every positional and keyword argument is taken *before* ``func`` runs.\nAfter the call each original argument is compared (deep, value equality) against its\npre-call snapshot. Any difference means ``func`` mutated a caller-owned object. The\ncomparison handles ``np.ndarray`` and Polars ``Series`` / ``DataFrame`` inputs, not\nonly scalars and built-in containers.\n\nArgs:\n    func: The callable under test.\n    *args: Positional arguments forwarded to ``func``.\n    **kwargs: Keyword arguments forwarded to ``func``.\n\nReturns:\n    Whatever ``func`` returned, so callers can chain assertions on the output.\n\nRaises:\n    AssertionError: If any input differs from its pre-call deep copy. The message\n        names each mutated positional index / keyword and shows ``before -> after``.",
          "methods": [],
          "fields": [],
          "members": [],
          "source": "src/quantvolt/testing.py",
          "line": 48
        }
      ]
    }
  ],
  "symbolCount": 469
};
