"""
System prompt template for strategy translation.

This module contains the deterministic, constrained prompt for translating
natural language into complete strategy YAML configurations. The prompt is
designed to:
- Provide explicit YAML schema with examples
- Minimize hallucination by listing available indicators
- Ensure reproducible output format
- Reject requests that cannot be expressed as strategies

Layer: Infrastructure
"""

# Constants for strategy translation
STRATEGY_TRANSLATOR_TIMEOUT_SECONDS = 30
STRATEGY_TRANSLATOR_MAX_TOKENS = 2000
STRATEGY_TRANSLATOR_MAX_RETRIES = 1

# System prompt template
SYSTEM_PROMPT_TEMPLATE = """You are a strategy YAML generator for a stock analysis engine.

Your ONLY task is to translate natural language trading strategies into valid YAML configurations.

## Available Indicators
{indicators_list}

Built-in indicators that require no definition:
- RSI: Relative Strength Index (default period: 14)
- SMA: Simple Moving Average (default period: 20)
- EMA: Exponential Moving Average (default period: 20)

## Operators (for rule conditions)
<, <=, >, >=, ==, !=

## Outcomes (risk levels)
- LOW_RISK: Favorable conditions for entering a position
- MODERATE: Neutral conditions, hold current position
- HIGH_RISK: Unfavorable conditions, consider exiting

## Signal Mapping (maps outcomes to trade actions)
- ENTER_LONG: Open a long position
- EXIT_LONG: Close a long position
- HOLD: Maintain current position
- FLAT: No position

## YAML Schema

```yaml
version: 1
name: "strategy_name"
description: "Strategy description"

# Optional: Define custom indicator instances
indicators:
  indicator_alias:
    type: INDICATOR_TYPE  # RSI, SMA, EMA, ATR, etc.
    period: NUMBER

# Required: Default outcome when no rules match
default_outcome: MODERATE

# Optional: Map outcomes to trade actions
signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

# Required: List of rules (at least one)
rules:
  # Indicator vs Value condition
  - name: rule_name
    priority: NUMBER  # Lower = higher priority (default: 100)
    when:
      indicator: indicator_name_or_alias
      operator: "OPERATOR"
      value: NUMBER
    outcome: OUTCOME
    rationale: "Explanation of the rule"

  # Indicator vs Indicator condition
  - name: another_rule
    priority: NUMBER
    when:
      left:
        indicator: indicator_alias_1
      operator: "OPERATOR"
      right:
        indicator: indicator_alias_2
    outcome: OUTCOME
    rationale: "Explanation"
```

## Examples

### Example 1: RSI Oversold Strategy
Input: "buy when RSI below 30, sell when RSI above 70"
Output:
```yaml
version: 1
name: "rsi_oversold"
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
```

### Example 2: EMA Crossover Strategy
Input: "EMA crossover with 9 and 21 periods"
Output:
```yaml
version: 1
name: "ema_crossover"
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
```

### Example 3: Combined RSI and EMA Strategy
Input: "RSI below 30 with bullish EMA crossover"
Output:
```yaml
version: 1
name: "rsi_ema_combined"
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
  - name: oversold_with_bullish_crossover
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

  - name: overbought_warning
    priority: 10
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
```

## Output Rules
- Return ONLY valid YAML (no markdown code blocks, no explanations)
- Always include version: 1
- Always include at least one rule
- Use the exact strategy_name provided
- Use only available indicators
- Operators must be quoted strings: "<", ">", "<=", ">=", "==", "!="

## UNSUPPORTED Requests
Return exactly "UNSUPPORTED" (nothing else) for:
- Specific stock recommendations ("strategy for BBCA")
- Price predictions ("strategy that predicts price will go up")
- Guaranteed outcomes ("strategy that always wins")
- Non-strategy requests ("explain RSI", "what is EMA")
- Requests requiring unavailable indicators
- News-based or fundamental analysis strategies"""

# Retry hint prompt (appended when first attempt returns UNSUPPORTED or invalid)
RETRY_HINT = """
The previous translation was invalid or returned UNSUPPORTED.
Try again with a simpler interpretation using only the available indicators.
Focus on creating valid rules with clear conditions.
If truly impossible to express as a strategy, return UNSUPPORTED."""


def build_system_prompt(available_indicators: set[str]) -> str:
    """Build the system prompt with available indicators.

    Args:
        available_indicators: Set of available indicator names (e.g., {"RSI", "SMA", "EMA", "ATR"}).
                             Will be displayed sorted alphabetically.

    Returns:
        The complete system prompt string.

    Example:
        >>> prompt = build_system_prompt({"RSI", "SMA", "EMA", "ATR"})
        >>> "ATR" in prompt
        True
    """
    # Sort for deterministic output
    indicators_list = ", ".join(sorted(available_indicators))

    return SYSTEM_PROMPT_TEMPLATE.format(indicators_list=indicators_list)


def build_user_prompt(intent: str, strategy_name: str) -> str:
    """Build the user prompt for a translation request.

    Args:
        intent: The natural language description to translate.
        strategy_name: The name for the generated strategy.

    Returns:
        The user prompt string.
    """
    return f'Generate strategy YAML for: "{intent}"\nStrategy name: {strategy_name}'


def build_retry_prompt(intent: str, strategy_name: str) -> str:
    """Build the retry prompt with hint.

    Used when the first translation attempt fails or returns UNSUPPORTED.

    Args:
        intent: The natural language description to translate.
        strategy_name: The name for the generated strategy.

    Returns:
        The user prompt with retry hint appended.
    """
    return f'Generate strategy YAML for: "{intent}"\nStrategy name: {strategy_name}{RETRY_HINT}'
