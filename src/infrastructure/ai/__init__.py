"""
AI infrastructure adapters for explanation and translation.

This module provides LLM-based adapters that implement AI ports
from the domain and application layers.

Usage:
    from src.infrastructure.ai import ExplainerFactory, FormulaTranslatorAdapter

    # Create explainer (reads AI_PROVIDER env var)
    explainer = ExplainerFactory.create()

    # Or specify provider explicitly
    explainer = ExplainerFactory.create(provider="ollama")

    # Generate explanation
    explanation = explainer.explain_assessment(ticker, assessment, snapshot)

    # Create formula translator
    translator = FormulaTranslatorAdapter(provider="mock")
    formula = translator.translate("14-day RSI", {"SMA", "EMA", "RSI"})
"""

from src.infrastructure.ai.factory import ExplainerFactory, RateLimitedExplainer
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.ai.mock_explainer import MockExplainer

__all__ = [
    "ExplainerFactory",
    "FormulaTranslatorAdapter",
    "MockExplainer",
    "RateLimitedExplainer",
]
