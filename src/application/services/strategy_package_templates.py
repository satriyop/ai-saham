"""
Templates for newly created strategy packages.

Layer: Application
"""

STRATEGY_TEMPLATE = """version: 1
name: "{name}"
description: "Strategy description goes here"

# ====================
# Indicator Definitions (optional)
# ====================
# Define custom indicator instances with specific periods.
# Built-in defaults (always available): RSI(14), SMA(20), EMA(20)

indicators:
  fast_ema:
    type: EMA
    period: 9

  slow_ema:
    type: EMA
    period: 21

# REQUIRED: Outcome when no rules match
default_outcome: MODERATE

# Optional: Map outcomes to trade actions for backtesting
signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  # EMA Crossover - bullish
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

  # EMA Crossover - bearish
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

  # RSI oversold
  - name: rsi_oversold
    priority: 20
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  # RSI overbought
  - name: rsi_overbought
    priority: 20
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
"""

README_TEMPLATE = """# {name}

{description}

## Usage

```bash
# Run backtest with this strategy
saham strategy backtest BBCA --strategy {name}

# Validate the strategy
saham strategy validate {name}
```

## Rules

This strategy uses the following rules:

1. **EMA Crossover**: Compares 9-period EMA vs 21-period EMA
2. **RSI Thresholds**: Standard overbought/oversold levels (70/30)

## Customization

Edit `strategy.yaml` to customize:
- Indicator periods
- Rule thresholds
- Signal mapping
"""
