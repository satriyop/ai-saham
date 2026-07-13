"""
IndicatorEvaluator port - interface for mapping an indicator snapshot to a reading.

This is a domain port (interface). The application-layer indicator evaluator
service satisfies this Protocol structurally — it does not need to inherit
from it.
"""

from typing import Protocol

from src.domain.indicators.indicator_context import IndicatorContext
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


class IndicatorEvaluator(Protocol):
    """Structural interface for evaluating an indicator snapshot."""

    def evaluate(self, snapshot: IndicatorSnapshot) -> IndicatorContext:
        """Map an IndicatorSnapshot to an IndicatorContext."""
        ...
