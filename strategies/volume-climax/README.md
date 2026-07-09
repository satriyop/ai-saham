# Volume Climax Absorption Strategy

Volume-driven oversold mean reversion strategy designed to trade V-shape relief bounces and capitulation bottoms.

## Rules

This strategy uses the Volume Ratio and RSI indicators:

1.  **Entry (Long)**: 
    *   **Volume Ratio (20) is above 2.5** (volume is 2.5x the prior 20-day average).
    *   **RSI(14) is below 35** (price is deep oversold).
2.  **Exit (Stop Loss / Take Profit)**:
    *   **RSI(14) rises above 55** (profit target at neutral momentum).
    *   **RSI(14) falls below 25** (panic stop loss).

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate volume-climax
```

### Backtesting
To backtest this strategy against any stock:
```bash
saham strategy backtest BBCA --strategy volume-climax
```
