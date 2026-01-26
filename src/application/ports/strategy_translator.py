"""
Port interface for AI-powered strategy translation.

This module defines the StrategyTranslator protocol and related exceptions
for translating natural language intents into complete strategy YAML.

Layer: Application
"""

from typing import Protocol


class StrategyTranslatorError(Exception):
    """Base exception for all strategy translator errors."""

    pass


class StrategyTranslatorTimeoutError(StrategyTranslatorError):
    """Raised when the translation request times out."""

    pass


class StrategyTranslatorAuthError(StrategyTranslatorError):
    """Raised when authentication fails (invalid/missing API key)."""

    pass


class StrategyTranslatorRateLimitError(StrategyTranslatorError):
    """Raised when rate limit is exceeded."""

    pass


class StrategyTranslator(Protocol):
    """Port for AI-powered strategy translation.

    Translates natural language descriptions of trading strategies into
    complete strategy YAML configurations that can be parsed by the
    YamlConfigLoader.

    Example:
        translator = StrategyTranslatorAdapter(provider="claude")
        result = translator.translate(
            intent="buy when RSI below 30, sell when RSI above 70",
            strategy_name="rsi_strategy",
            available_indicators={"RSI", "SMA", "EMA", "ATR"},
        )
        # Returns: valid YAML string or "UNSUPPORTED"

    The translator returns "UNSUPPORTED" when the intent cannot be
    expressed as a valid strategy (e.g., specific stock recommendations,
    price predictions, guaranteed outcomes).
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name for logging and attribution."""
        ...

    def translate(
        self,
        intent: str,
        strategy_name: str,
        available_indicators: set[str],
    ) -> str:
        """Translate natural language intent into strategy YAML.

        Args:
            intent: Natural language description of the strategy.
                   E.g., "buy when RSI below 30 and fast EMA crosses above slow EMA"
            strategy_name: Name for the generated strategy.
            available_indicators: Set of available indicator names (uppercase).
                                 E.g., {"RSI", "SMA", "EMA", "ATR", "MACD"}

        Returns:
            Valid YAML string for strategy.yaml OR "UNSUPPORTED"
            if the intent cannot be expressed as a strategy.

        Raises:
            StrategyTranslatorTimeoutError: If the request times out.
            StrategyTranslatorAuthError: If authentication fails.
            StrategyTranslatorRateLimitError: If rate limit is exceeded.
            StrategyTranslatorError: For other translation errors.
        """
        ...
