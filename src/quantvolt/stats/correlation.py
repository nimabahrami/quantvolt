"""Correlation analysis (Task 23).

Cross-commodity dependence for power/energy markets: a full pairwise correlation
matrix (Pearson / Spearman / Kendall) and a rolling Pearson correlation for
time-varying dependence.

The correlation *method* is chosen by dispatch (Strategy realised as functions,
selected via the :data:`_MATRIX_METHODS` dict) rather than an ``if/elif`` ladder
— see ``steering/coding-style.md``. Polars is imported at call time so the module
stays cheap to import; numpy/scipy are core kernels imported eagerly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

import numpy as np
from numpy.typing import NDArray
from scipy.stats import kendalltau, spearmanr  # type: ignore[import-untyped]

from ..exceptions import ValidationError

if TYPE_CHECKING:
    import polars as pl


def _pearson_matrix(data: NDArray[np.float64]) -> NDArray[np.float64]:
    """Linear correlation matrix via :func:`numpy.corrcoef` (columns = variables)."""
    return np.asarray(np.corrcoef(data, rowvar=False), dtype=np.float64)


def _spearman_matrix(data: NDArray[np.float64]) -> NDArray[np.float64]:
    """Rank-correlation matrix via :func:`scipy.stats.spearmanr`.

    scipy returns a scalar (not a matrix) when given exactly two variables, so
    that case is widened back to a 2x2 matrix here.
    """
    corr = np.asarray(spearmanr(data).statistic, dtype=np.float64)
    if corr.ndim == 0:
        rho = float(corr)
        return np.array([[1.0, rho], [rho, 1.0]], dtype=np.float64)
    return corr


def _kendall_matrix(data: NDArray[np.float64]) -> NDArray[np.float64]:
    """Kendall-tau concordance matrix, computed pairwise (scipy has no matrix form)."""
    n_vars = data.shape[1]
    corr = np.ones((n_vars, n_vars), dtype=np.float64)
    for i in range(n_vars):
        for j in range(i + 1, n_vars):
            tau = float(kendalltau(data[:, i], data[:, j]).statistic)
            corr[i, j] = tau
            corr[j, i] = tau
    return corr


#: method name -> estimator taking an (n_obs, n_vars) array, returning the (n_vars, n_vars) matrix.
_MATRIX_METHODS: dict[str, Callable[[NDArray[np.float64]], NDArray[np.float64]]] = {
    "pearson": _pearson_matrix,
    "spearman": _spearman_matrix,
    "kendall": _kendall_matrix,
}


def correlation_matrix(
    price_data: pl.DataFrame,
    method: Literal["pearson", "spearman", "kendall"] = "pearson",
) -> pl.DataFrame:
    """Pairwise correlation across the DataFrame's columns (commodities).

    Each input column is a variable and each row an observation (e.g. a date).
    ``method`` selects the estimator by dispatch:

    - ``"pearson"``  — :func:`numpy.corrcoef` (linear correlation)
    - ``"spearman"`` — :func:`scipy.stats.spearmanr` (rank correlation)
    - ``"kendall"``  — :func:`scipy.stats.kendalltau` (pairwise rank concordance)

    Shape convention: the result is the square ``n x n`` matrix returned as a
    :class:`polars.DataFrame` of shape ``(n_vars, n_vars + 1)`` — a leading
    ``"index"`` string column holds the input column names as row labels, followed
    by one float column per input column (identical names and order). Row ``i`` (and
    ``result["index"][i]``) corresponds to input column ``i``. The matrix is
    symmetric with an exact ``1.0`` diagonal. The input is never mutated.

    Raises:
        ValidationError: if ``price_data`` has fewer than 2 columns or 2 rows, or
            ``method`` is not one of ``pearson``/``spearman``/``kendall``.
    """
    import polars as pl

    columns = price_data.columns
    if len(columns) < 2:
        raise ValidationError(f"price_data must have >= 2 columns, got {len(columns)}")
    if price_data.height < 2:
        raise ValidationError(f"price_data must have >= 2 rows, got {price_data.height}")
    if method not in _MATRIX_METHODS:
        valid = ", ".join(_MATRIX_METHODS)
        raise ValidationError(f"method must be one of {{{valid}}}, got {method!r}")

    data = price_data.to_numpy().astype(np.float64)  # fresh copy — inputs untouched
    if not np.all(np.isfinite(data)):
        # polars nulls surface as NaN once converted to a float64 numpy array, so this
        # single finiteness check also catches nulls (coding-style.md section 7: fail
        # loudly rather than silently propagating NaN off-diagonals).
        bad_columns = [
            name
            for name, column in zip(columns, data.T, strict=True)
            if not np.all(np.isfinite(column))
        ]
        raise ValidationError(
            "price_data must not contain null or non-finite values; offending "
            f"column(s): {', '.join(repr(name) for name in bad_columns)}"
        )
    corr = _MATRIX_METHODS[method](data)

    # Pin the invariants exactly, independent of floating-point noise.
    corr = (corr + corr.T) / 2.0
    np.fill_diagonal(corr, 1.0)

    labels = pl.DataFrame({"index": columns})
    return labels.with_columns(pl.Series(name, corr[:, j]) for j, name in enumerate(columns))


def rolling_correlation(
    series_a: pl.Series,
    series_b: pl.Series,
    window: int = 252,
) -> pl.Series:
    """Rolling Pearson correlation of two equal-length series over ``window``.

    The window ending at row ``i`` spans rows ``i - window + 1 .. i`` inclusive, so
    the leading ``window - 1`` entries are null. Returns a series named
    ``"rolling_correlation"`` of the same length as the inputs. Neither input is
    mutated.

    Raises:
        ValidationError: if the series differ in length, or ``window`` is < 2 or
            greater than the series length.
    """
    import polars as pl

    n = len(series_a)
    if len(series_b) != n:
        raise ValidationError(
            f"series_a and series_b must have equal length, got {n} and {len(series_b)}"
        )
    if window < 2:
        raise ValidationError(f"window must be >= 2, got {window}")
    if window > n:
        raise ValidationError(f"window must be <= series length ({n}), got {window}")

    frame = pl.DataFrame({"a": series_a, "b": series_b})
    result = frame.select(
        pl.rolling_corr("a", "b", window_size=window).alias("rolling_correlation")
    )
    return result["rolling_correlation"]
