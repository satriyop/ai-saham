"""
Port interface for AI-powered formula translation.

This module defines the FormulaTranslator protocol and related exceptions
for translating natural language intents into formula strings.

Layer: Application
"""

from typing import Protocol


class FormulaTranslatorError(Exception):
    """Base exception for all formula translator errors."""

    pass


class TranslatorTimeoutError(FormulaTranslatorError):
    """Raised when the translation request times out."""

    pass


class TranslatorAuthError(FormulaTranslatorError):
    """Raised when authentication fails (invalid/missing API key)."""

    pass


class TranslatorRateLimitError(FormulaTranslatorError):
    """Raised when rate limit is exceeded."""

    pass


class FormulaTranslator(Protocol):
    """Port for AI-powered formula translation.

    Translates natural language descriptions of indicators into
    formula strings that can be parsed by the formula engine.

    Example:
        translator = FormulaTranslatorAdapter(provider="claude")
        result = translator.translate(
            intent="smoothed RSI with 14-period and 10-day smoothing",
            available_functions={"SMA", "EMA", "RSI"},
        )
        # Returns: "SMA(RSI(14), 10)" or "UNSUPPORTED"

    The translator returns "UNSUPPORTED" when the intent cannot be
    expressed as a valid formula (e.g., trading advice, predictions).
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name for logging and attribution."""
        ...

    def translate(
        self,
        intent: str,
        available_functions: set[str],
        available_series: set[str] | None = None,
    ) -> str:
        """Translate natural language intent into a formula string.

        Args:
            intent: Natural language description of the indicator.
            available_functions: Set of available function names (uppercase).
                               E.g., {"SMA", "EMA", "RSI", "ATR"}
            available_series: Set of available series names. If None, defaults
                            to {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}.

        Returns:
            Formula string (e.g., "SMA(RSI(14), 10)") OR "UNSUPPORTED"
            if the intent cannot be expressed as a formula.

        Raises:
            TranslatorTimeoutError: If the request times out.
            TranslatorAuthError: If authentication fails.
            TranslatorRateLimitError: If rate limit is exceeded.
            FormulaTranslatorError: For other translation errors.
        """
        ...
