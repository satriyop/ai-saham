"""
Mock strategy translator for testing without live AI providers.

Routes a user prompt to canned YAML templates based on keyword matching,
so tests and offline development can exercise the translation flow without
network access or API keys.

Layer: Infrastructure
"""

# Keywords that indicate an intent the mock provider cannot translate.
UNSUPPORTED_KEYWORDS = [
    "predict",
    "always win",
    "guaranteed",
    "for bbca",
    "for bbri",
    "specific stock",
    "explain",
    "what is",
]


def call_mock_strategy_translator(user_prompt: str) -> str:
    """Return a mock translation response for testing.

    Args:
        user_prompt: The user prompt as built by build_user_prompt/build_retry_prompt.

    Returns:
        Mock YAML string or "UNSUPPORTED".
    """
    # Extract strategy name and intent from user prompt
    lines = user_prompt.split("\n")
    intent_line = lines[0] if lines else ""
    name_line = lines[1] if len(lines) > 1 else ""

    # Parse intent
    intent = intent_line.replace('Generate strategy YAML for: "', "").rstrip('"')
    intent_lower = intent.lower()

    # Parse strategy name
    strategy_name = name_line.replace("Strategy name: ", "").strip()
    if not strategy_name:
        strategy_name = "mock_strategy"

    # Check for unsupported intents FIRST
    if any(kw in intent_lower for kw in UNSUPPORTED_KEYWORDS):
        return "UNSUPPORTED"

    # Mock translations based on keywords
    if "rsi" in intent_lower and ("ema" in intent_lower or "crossover" in intent_lower):
        return _mock_rsi_ema_combined(strategy_name)

    if "ema crossover" in intent_lower or ("ema" in intent_lower and "crossover" in intent_lower):
        return _mock_ema_crossover(strategy_name)

    if "rsi" in intent_lower:
        return _mock_rsi_strategy(strategy_name)

    if "sma" in intent_lower and "crossover" in intent_lower:
        return _mock_sma_crossover(strategy_name)

    if "atr" in intent_lower:
        return _mock_atr_strategy(strategy_name)

    if "conservative" in intent_lower:
        return _mock_conservative_strategy(strategy_name)

    if "momentum" in intent_lower:
        return _mock_momentum_strategy(strategy_name)

    # Default fallback for testing
    return _mock_rsi_strategy(strategy_name)


def _mock_rsi_strategy(name: str) -> str:
    """Generate mock RSI oversold/overbought strategy."""
    return f'''version: 1
name: "{name}"
description: "RSI oversold/overbought strategy"

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_oversold
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  - name: rsi_overbought
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
'''


def _mock_ema_crossover(name: str) -> str:
    """Generate mock EMA crossover strategy."""
    return f'''version: 1
name: "{name}"
description: "EMA 9/21 crossover strategy"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: bullish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "Fast EMA above slow EMA indicates bullish momentum"

  - name: bearish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: "<"
      right:
        indicator: slow_ema
    outcome: HIGH_RISK
    rationale: "Fast EMA below slow EMA indicates bearish momentum"
'''


def _mock_rsi_ema_combined(name: str) -> str:
    """Generate mock combined RSI and EMA strategy."""
    return f'''version: 1
name: "{name}"
description: "RSI oversold with EMA crossover confirmation"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_oversold
    priority: 5
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  - name: bullish_ema_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "Fast EMA above slow EMA confirms bullish momentum"

  - name: rsi_overbought
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
'''


def _mock_sma_crossover(name: str) -> str:
    """Generate mock SMA crossover strategy."""
    return f'''version: 1
name: "{name}"
description: "SMA 20/50 crossover strategy"

indicators:
  fast_sma:
    type: SMA
    period: 20
  slow_sma:
    type: SMA
    period: 50

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: golden_cross
    priority: 10
    when:
      left:
        indicator: fast_sma
      operator: ">"
      right:
        indicator: slow_sma
    outcome: LOW_RISK
    rationale: "Golden cross - fast SMA crosses above slow SMA"

  - name: death_cross
    priority: 10
    when:
      left:
        indicator: fast_sma
      operator: "<"
      right:
        indicator: slow_sma
    outcome: HIGH_RISK
    rationale: "Death cross - fast SMA crosses below slow SMA"
'''


def _mock_atr_strategy(name: str) -> str:
    """Generate mock ATR-based strategy."""
    return f'''version: 1
name: "{name}"
description: "ATR volatility-based strategy"

indicators:
  atr_14:
    type: ATR
    period: 14

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: low_volatility
    priority: 10
    when:
      indicator: atr_14
      operator: "<"
      value: 2.0
    outcome: LOW_RISK
    rationale: "Low volatility environment favorable for entries"

  - name: high_volatility
    priority: 10
    when:
      indicator: atr_14
      operator: ">"
      value: 5.0
    outcome: HIGH_RISK
    rationale: "High volatility indicates increased risk"
'''


def _mock_conservative_strategy(name: str) -> str:
    """Generate mock conservative RSI strategy."""
    return f'''version: 1
name: "{name}"
description: "Conservative RSI strategy with strict thresholds"

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: very_oversold
    priority: 5
    when:
      indicator: RSI
      operator: "<"
      value: 25
    outcome: LOW_RISK
    rationale: "RSI below 25 indicates extremely oversold conditions"

  - name: very_overbought
    priority: 5
    when:
      indicator: RSI
      operator: ">"
      value: 75
    outcome: HIGH_RISK
    rationale: "RSI above 75 indicates extremely overbought conditions"
'''


def _mock_momentum_strategy(name: str) -> str:
    """Generate mock momentum strategy."""
    return f'''version: 1
name: "{name}"
description: "Momentum strategy using RSI and EMA"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_momentum
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 40
    outcome: LOW_RISK
    rationale: "RSI below 40 shows potential upside momentum"

  - name: ema_confirmation
    priority: 15
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "EMA crossover confirms bullish momentum"

  - name: exit_signal
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 65
    outcome: HIGH_RISK
    rationale: "RSI above 65 indicates potential reversal"
'''
