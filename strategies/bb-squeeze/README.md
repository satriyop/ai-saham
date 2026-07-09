# Bollinger Band Squeeze Breakout Strategy

A volatility compression breakout strategy designed to capture the transition from range-bound consolidation to a new strong trend.

## Rules

This strategy uses a 20-period Bollinger Band:

1.  **Entry (Long)**: 
    *   The previous day's Bollinger Band Width (`BB_WIDTH_T1`) was compressed below **12%** (representing low volatility compression).
    *   The current close price breaks above the **Upper Bollinger Band**.
    *   **RSI(14) is above 50** (confirming positive rising momentum).
2.  **Exit (Stop Loss / Take Profit)**:
    *   The close price falls below the **20-day SMA (Middle Band)**, acting as a trailing stop loss.
    *   **RSI(14) rises above 80** (climax profit target).

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate bb-squeeze
```

### Backtesting
To backtest this strategy against any stock:
```bash
saham strategy backtest BBCA --strategy bb-squeeze
```
