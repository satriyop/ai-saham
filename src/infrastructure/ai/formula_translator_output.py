"""
Formula output canonicalization for formula translation.

Layer: Infrastructure
"""

import re

from src.infrastructure.ai.formula_translator_prompt import DEFAULT_SERIES

# Pattern for function names in formulas
FUNCTION_NAME_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def canonicalize_formula(raw: str) -> str:
    """Normalize formula output from LLM.

    - Strip leading/trailing whitespace
    - Remove markdown code blocks
    - Take first line only (ignore explanations)
    - Uppercase function names (SMA, EMA, RSI)
    - Normalize spacing around operators
    - Handle common LLM quirks

    Args:
        raw: Raw LLM output string.

    Returns:
        Canonicalized formula string or "UNSUPPORTED".

    Example:
        >>> canonicalize_formula("```\nsma(rsi(14), 10)\n```")
        'SMA(RSI(14), 10)'
        >>> canonicalize_formula("UNSUPPORTED - cannot translate")
        'UNSUPPORTED'
    """
    # Strip whitespace
    result = raw.strip()

    # Remove markdown code blocks
    result = re.sub(r"^```[a-z]*\n?", "", result)
    result = re.sub(r"\n?```$", "", result)
    result = result.strip()

    # Take first non-empty line only
    lines = result.split("\n")
    result = ""
    for line in lines:
        line = line.strip()
        if line:
            result = line
            break

    if not result:
        return "UNSUPPORTED"

    # Check for UNSUPPORTED (case-insensitive, with any suffix)
    if result.upper().startswith("UNSUPPORTED"):
        return "UNSUPPORTED"

    # Uppercase function names
    def uppercase_function(match: re.Match) -> str:
        return match.group(1).upper() + "("

    result = FUNCTION_NAME_PATTERN.sub(uppercase_function, result)

    # Uppercase series names
    for series in DEFAULT_SERIES:
        # Word boundary replacement for series names
        pattern = re.compile(rf"\b{series}\b", re.IGNORECASE)
        result = pattern.sub(series, result)

    # Normalize spacing around operators
    result = re.sub(r"\s*([+\-*/])\s*", r" \1 ", result)

    # Clean up multiple spaces
    result = re.sub(r"\s+", " ", result)
    result = result.strip()

    return result
