"""
Mock formula translator for testing without live AI providers.

Routes a user prompt to canned formula templates based on keyword matching,
so tests and offline development can exercise the translation flow without
network access or API keys.

Layer: Infrastructure
"""

# Keywords that indicate an intent the mock provider cannot translate.
UNSUPPORTED_KEYWORDS = ["predict", "buy", "sell", "signal", "advice", "recommend"]


def call_mock_formula_translator(user_prompt: str) -> str:
    """Return a mock translation response for testing.

    Args:
        user_prompt: The prompt text passed by the adapter.

    Returns:
        Mock formula string or "UNSUPPORTED".
    """
    # Extract intent from user prompt
    intent = user_prompt.replace("Translate to formula: ", "").strip()
    intent_lower = intent.lower()

    # Check for unsupported intents FIRST (before any indicator keywords)
    if any(kw in intent_lower for kw in UNSUPPORTED_KEYWORDS):
        return "UNSUPPORTED"

    # Mock translations based on keywords
    if "rsi" in intent_lower and "smooth" in intent_lower:
        return "SMA(RSI(14), 10)"
    if "macd" in intent_lower:
        return "EMA(CLOSE, 12) - EMA(CLOSE, 26)"
    if "rsi" in intent_lower:
        return "RSI(14)"
    if "sma" in intent_lower or "simple moving" in intent_lower:
        return "SMA(CLOSE, 20)"
    if "ema" in intent_lower or "exponential" in intent_lower:
        return "EMA(CLOSE, 20)"
    if "atr" in intent_lower or "true range" in intent_lower:
        return "ATR(14)"

    return "UNSUPPORTED"
