"""Unit tests for hedging/hybrid.py (Task 71): hybrid-model power-price hedging.

Validates Requirement 18.5 and Correctness Property 57 (hybrid hedge-quality
monotonicity): a hybrid price ``p_t = s^bid(drivers_t) + epsilon_t`` (eq 10.26)
is hedged by the chain-rule deltas of the deterministic stack to each tradable
driver, and a representation with a smaller residual variance is the better
hedge ("the smaller its variance, the better the representation", source text
after eq 10.28).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.hedging.hybrid import hybrid_deltas, residual_variance
from quantvolt.testing import assert_input_unchanged


class TestHybridDeltas:
    """Req 18.5 / Property 57: chain-rule deltas ``partial s^bid / partial driver``."""

    def test_linear_stack_yields_exact_coefficients(self) -> None:
        # p = 2*gas + 0.5*demand  =>  deltas are exactly the coefficients {gas: 2, demand: 0.5}.
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"]

        deltas = hybrid_deltas(stack, {"gas": 3.0, "demand": 40.0}, bump=1e-4)
        # Exact linear coefficients up to floating-point round-off in the central diff.
        assert set(deltas) == {"gas", "demand"}
        assert deltas["gas"] == pytest.approx(2.0, abs=1e-9)
        assert deltas["demand"] == pytest.approx(0.5, abs=1e-9)

    def test_multiplicative_stack_matches_analytic_partials(self) -> None:
        # Cobb-Douglas stack p = A * gas^alpha * demand^beta with non-integer alpha
        # so the central difference has a genuine (tiny) truncation error.
        #   partial p / partial gas    = alpha * p / gas
        #   partial p / partial demand = beta  * p / demand
        a, alpha, beta = 2.0, 1.5, 0.5

        def stack(d: Mapping[str, float]) -> float:
            return a * d["gas"] ** alpha * d["demand"] ** beta

        gas, demand = 4.0, 9.0
        price = stack({"gas": gas, "demand": demand})
        deltas = hybrid_deltas(stack, {"gas": gas, "demand": demand}, bump=1e-4)

        assert deltas["gas"] == pytest.approx(alpha * price / gas, rel=1e-6)
        assert deltas["demand"] == pytest.approx(beta * price / demand, rel=1e-6)

    def test_transcendental_stack_within_fd_tolerance(self) -> None:
        # p = exp(0.1*gas) * demand + 0.7*oil : exercises a truly non-polynomial partial.
        #   partial p / partial gas = 0.1 * exp(0.1*gas) * demand
        def stack(d: Mapping[str, float]) -> float:
            return math.exp(0.1 * d["gas"]) * d["demand"] + 0.7 * d["oil"]

        deltas = hybrid_deltas(stack, {"gas": 5.0, "demand": 30.0, "oil": 60.0}, bump=1e-4)
        assert deltas["gas"] == pytest.approx(0.1 * math.exp(0.5) * 30.0, rel=1e-6)
        assert deltas["demand"] == pytest.approx(math.exp(0.5), rel=1e-6)
        assert deltas["oil"] == pytest.approx(0.7, rel=1e-6)

    def test_chain_rule_deltas_sum_consistently_across_drivers(self) -> None:
        # Property 57: dp = sum_k (partial p / partial driver_k) * d(driver_k).
        # For a linear stack this first-order identity is exact.
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"] - 1.3 * d["oil"]

        base = {"gas": 3.0, "demand": 40.0, "oil": 55.0}
        deltas = hybrid_deltas(stack, base, bump=1e-4)

        moves = {"gas": 0.1, "demand": 0.2, "oil": -0.05}
        bumped = {k: base[k] + moves[k] for k in base}
        actual_change = stack(bumped) - stack(base)
        predicted_change = sum(deltas[k] * moves[k] for k in base)
        assert actual_change == pytest.approx(predicted_change, rel=1e-9, abs=1e-12)

    def test_only_supplied_drivers_appear_in_result(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 4.0 * d["gas"]

        deltas = hybrid_deltas(stack, {"gas": 2.0}, bump=1e-3)
        assert set(deltas) == {"gas"}
        assert deltas["gas"] == pytest.approx(4.0)

    def test_deterministic(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"] ** 2

        args = ({"gas": 3.0, "demand": 40.0}, 1e-4)
        assert hybrid_deltas(stack, *args) == hybrid_deltas(stack, *args)

    def test_does_not_mutate_drivers(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"]

        drivers = {"gas": 3.0, "demand": 40.0}
        assert_input_unchanged(hybrid_deltas, stack, drivers, 1e-4)

    def test_non_callable_stack_fn_raises_naming_param(self) -> None:
        with pytest.raises(ValidationError, match="stack_fn"):
            hybrid_deltas("not-callable", {"gas": 1.0}, 1e-4)  # type: ignore[arg-type]

    def test_non_positive_bump_raises_naming_param(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return d["gas"]

        with pytest.raises(ValidationError, match="bump"):
            hybrid_deltas(stack, {"gas": 1.0}, 0.0)
        with pytest.raises(ValidationError, match="bump"):
            hybrid_deltas(stack, {"gas": 1.0}, -1e-4)

    def test_empty_drivers_raises_naming_param(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 0.0

        with pytest.raises(ValidationError, match="drivers"):
            hybrid_deltas(stack, {}, 1e-4)


class TestResidualVariance:
    """Req 18.5 / Property 57: residual variance is the hedge-quality metric (smaller = better)."""

    def test_matches_manual_variance_of_residual(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"]

        drivers = {"gas": [1.0, 2.0, 3.0, 4.0]}
        realized = [2.5, 3.5, 6.5, 7.5]  # residual = realized - 2*gas
        expected = float(np.var(np.array([0.5, -0.5, 0.5, -0.5]), ddof=1))
        assert residual_variance(stack, drivers, realized) == pytest.approx(expected)

    def test_perfect_stack_has_zero_residual_variance(self) -> None:
        # Zero residual variance => the price is fully spanned/hedgeable (source, after eq 10.28).
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"]

        drivers = {"gas": [1.0, 2.0, 3.0], "demand": [10.0, 20.0, 30.0]}
        gas, demand = [1.0, 2.0, 3.0], [10.0, 20.0, 30.0]
        realized = [2.0 * g + 0.5 * dmd for g, dmd in zip(gas, demand, strict=True)]
        assert residual_variance(stack, drivers, realized) == pytest.approx(0.0, abs=1e-12)

    def test_monotonicity_better_specified_stack_has_smaller_residual(self) -> None:
        # Property 57 monotonicity. Data-generating process (fixed seed):
        #   p_t = 2*gas_t + 0.5*demand_t + small noise.
        # The better-specified stack uses BOTH drivers (matches the DGP) and leaves
        # only the noise as residual; the underspecified stack drops `demand`, whose
        # real variance then leaks into the residual => strictly larger variance.
        rng = np.random.default_rng(20260715)
        n = 500
        gas = rng.normal(20.0, 3.0, n)
        demand = rng.normal(40.0, 8.0, n)
        noise = rng.normal(0.0, 0.5, n)
        realized = 2.0 * gas + 0.5 * demand + noise
        drivers = {"gas": gas.tolist(), "demand": demand.tolist()}

        def good_stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"]

        def bad_stack(d: Mapping[str, float]) -> float:  # omits demand
            return 2.0 * d["gas"]

        good = residual_variance(good_stack, drivers, realized.tolist())
        bad = residual_variance(bad_stack, drivers, realized.tolist())

        assert good < bad  # smaller residual variance => better hedge (Property 57)
        # The good stack's residual is just the injected noise (variance ~ 0.5**2).
        assert good == pytest.approx(0.25, rel=0.15)
        # The bad stack additionally carries 0.5*demand (var = 0.25 * 8**2 = 16), so its
        # residual variance is far larger, dominated by the unexplained demand term.
        assert bad > 10.0

    def test_deterministic(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"]

        drivers = {"gas": [1.0, 2.0, 3.0]}
        realized = [2.1, 4.3, 5.8]
        assert residual_variance(stack, drivers, realized) == residual_variance(
            stack, drivers, realized
        )

    def test_does_not_mutate_inputs(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 2.0 * d["gas"] + 0.5 * d["demand"]

        drivers = {"gas": [1.0, 2.0, 3.0], "demand": [10.0, 20.0, 30.0]}
        realized = [12.0, 24.0, 36.0]
        assert_input_unchanged(residual_variance, stack, drivers, realized)

    def test_non_callable_stack_fn_raises_naming_param(self) -> None:
        with pytest.raises(ValidationError, match="stack_fn"):
            residual_variance("nope", {"gas": [1.0, 2.0]}, [1.0, 2.0])  # type: ignore[arg-type]

    def test_empty_drivers_raises_naming_param(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return 0.0

        with pytest.raises(ValidationError, match="drivers"):
            residual_variance(stack, {}, [1.0, 2.0])

    def test_fewer_than_two_observations_raises_insufficient_data(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return d["gas"]

        with pytest.raises(InsufficientDataError, match="n >= 2"):
            residual_variance(stack, {"gas": [1.0]}, [1.0])

    def test_mismatched_series_length_raises_naming_driver(self) -> None:
        def stack(d: Mapping[str, float]) -> float:
            return d["gas"]

        with pytest.raises(ValidationError, match="gas"):
            residual_variance(stack, {"gas": [1.0, 2.0, 3.0]}, [1.0, 2.0])
