"""
System prompt template for formula translation.

This module contains the deterministic, constrained prompt for translating
natural language into formula expressions. The prompt is designed to:
- Minimize hallucination by providing explicit function list
- Ensure reproducible output format
- Reject requests that cannot be expressed as formulas

Layer: Infrastructure
"""

# Constants for formula translation
FORMULA_TRANSLATOR_TIMEOUT_SECONDS = 5
FORMULA_TRANSLATOR_MAX_TOKENS = 100
FORMULA_TRANSLATOR_MAX_RETRIES = 1

# Default available series (price/volume data)
DEFAULT_SERIES = frozenset({"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"})

# System prompt template
SYSTEM_PROMPT_TEMPLATE = """You are a formula translator for a stock analysis engine.

Your ONLY task is to translate natural language into formula expressions.

## Available Functions
{functions_list}

## Available Series (price/volume data)
{series_list}

## Operators
+ - * /

## Formula Syntax
- RSI(14) - indicator with period only
- SMA(CLOSE, 20) - indicator with series and period
- EMA(RSI(14), 10) - nesting allowed
- EMA(CLOSE, 12) - EMA(CLOSE, 26) - arithmetic between indicators
- CLOSE * 1.05 - arithmetic with constants

## Examples
- "14-day RSI" -> RSI(14)
- "20-period simple moving average" -> SMA(CLOSE, 20)
- "smoothed RSI 14/10" -> SMA(RSI(14), 10)
- "MACD line" -> EMA(CLOSE, 12) - EMA(CLOSE, 26)
- "RSI smoothed with EMA" -> EMA(RSI(14), 10)
- "average true range 14" -> ATR(14)
- "bollinger band width" -> (BB_UPPER(CLOSE, 20, 2) - BB_LOWER(CLOSE, 20, 2)) / BB_MIDDLE(CLOSE,
20, 2)

## Output Rules
- Return ONLY the formula (single line, no explanation)
- If the request cannot be expressed as a formula using available functions, return: UNSUPPORTED
- Do NOT provide trading advice
- Do NOT provide price predictions
- Do NOT provide buy/sell signals
- Do NOT generate code
- Do NOT add explanations or formatting"""

# Retry hint prompt (appended when first attempt returns UNSUPPORTED)
RETRY_HINT = """
The previous translation returned UNSUPPORTED.
Try again with a simpler interpretation using only the available functions.
If truly impossible to express as a formula, return UNSUPPORTED."""


def build_system_prompt(
    available_functions: set[str],
    available_series: set[str] | None = None,
) -> str:
    """Build the system prompt with available functions and series.

    Args:
        available_functions: Set of available function names (e.g., {"SMA", "EMA", "RSI"}).
                           Will be displayed sorted alphabetically.
        available_series: Set of available series names. If None, uses DEFAULT_SERIES.

    Returns:
        The complete system prompt string.

    Example:
        >>> prompt = build_system_prompt({"SMA", "EMA", "RSI"})
        >>> "SMA" in prompt
        True
    """
    if available_series is None:
        available_series = DEFAULT_SERIES

    # Sort for deterministic output
    functions_list = ", ".join(sorted(available_functions))
    series_list = ", ".join(sorted(available_series))

    return SYSTEM_PROMPT_TEMPLATE.format(
        functions_list=functions_list,
        series_list=series_list,
    )


def build_user_prompt(intent: str) -> str:
    """Build the user prompt for a translation request.

    Args:
        intent: The natural language description to translate.

    Returns:
        The user prompt string.
    """
    return f"Translate to formula: {intent}"


def build_retry_prompt(intent: str) -> str:
    """Build the retry prompt with hint.

    Used when the first translation attempt returns UNSUPPORTED.

    Args:
        intent: The natural language description to translate.

    Returns:
        The user prompt with retry hint appended.
    """
    return f"Translate to formula: {intent}{RETRY_HINT}"
