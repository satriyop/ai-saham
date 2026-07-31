"""Re-export plan swing candidate builder from shared composition."""

from src.adapters.composition.plan_swing_candidate_builder import (
    create_accumulation_candidate_builder,
)

__all__ = ["create_accumulation_candidate_builder"]
