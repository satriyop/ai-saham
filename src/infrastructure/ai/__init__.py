"""
AI infrastructure adapters for explanation generation.

This module provides LLM-based explanation adapters that implement
the AIExplainer port from the domain layer.

Usage:
    from src.infrastructure.ai import ExplainerFactory

    # Create explainer (reads AI_PROVIDER env var)
    explainer = ExplainerFactory.create()

    # Or specify provider explicitly
    explainer = ExplainerFactory.create(provider="ollama")

    # Generate explanation
    explanation = explainer.explain_assessment(ticker, assessment, snapshot)
"""

from src.infrastructure.ai.factory import ExplainerFactory, RateLimitedExplainer
from src.infrastructure.ai.mock_explainer import MockExplainer

__all__ = [
    "ExplainerFactory",
    "RateLimitedExplainer",
    "MockExplainer",
]
