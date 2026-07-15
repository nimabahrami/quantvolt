"""Shared pytest fixtures. Hypothesis strategies live in ``tests/strategies.py``."""

from hypothesis import settings

# Default Hypothesis profile (design "Property Test Configuration"): every property
# runs >= 100 examples; no per-example deadline, since kernel warm-up (scipy/numpy)
# would make wall-clock deadlines flaky.
settings.register_profile("quantvolt", max_examples=100, deadline=None)
settings.load_profile("quantvolt")
