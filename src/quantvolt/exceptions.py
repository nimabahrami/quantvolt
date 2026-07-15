"""The `EnergyQuantError` hierarchy. Every exception the library raises is a subclass,
and messages name the offending parameter and the violated constraint (Req 11.5)."""

from __future__ import annotations


class EnergyQuantError(Exception):
    """Base class for all library-raised exceptions."""


class ValidationError(EnergyQuantError, ValueError):
    """Input parameter violates a documented constraint.

    ``ValueError`` is retained as a secondary base for conventional Python compatibility.
    """


class NumericalError(EnergyQuantError, ValueError):
    """A numerical kernel's mathematical precondition or convergence condition failed.

    ``ValueError`` is retained as a secondary base for compatibility with callers that use
    the low-level :mod:`quantvolt.numerics` API directly.
    """


class NativeExtensionError(EnergyQuantError):
    """A requested native Monte Carlo kernel is unavailable in this installation."""


class InsufficientDataError(EnergyQuantError):
    """Input data does not satisfy minimum requirements for an operation."""


class ArbitrageError(EnergyQuantError):
    """Curve contains arbitrage violations that cannot be identified."""


class NoPricingDataError(EnergyQuantError):
    """Neither settlement price nor forward curve price is available."""


class ExpiredContractError(EnergyQuantError):
    """Contract delivery period is entirely in the past."""


class MissingTenorError(EnergyQuantError):
    """Discount curve or volatility surface does not cover a required date."""


class ScenarioNotFoundError(EnergyQuantError):
    """Named scenario is not in the built-in scenario catalogue."""


# --- Raised only by the optional data-adapters layer (quantvolt.data) ---
class DataSourceError(EnergyQuantError):
    """A quantvolt[data] provider fetch failed."""


class AuthenticationError(DataSourceError):
    """Provider credential is missing or rejected (the value is never included)."""


class RateLimitError(DataSourceError):
    """Provider rate limit exceeded."""


class DataUnavailableError(DataSourceError):
    """Provider returned no data for the requested query."""
