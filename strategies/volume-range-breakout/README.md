# Range Volume Breakout Strategy

Classic price channel breakout strategy supported by volume expansion.

## Rules

This strategy uses Donchian Channels, Volume Ratio, and RSI:

1.  **Entry (Long)**: 
    *   The close price breaks above the **Donchian Upper Band** (the highest high of the previous 20 candles).
    *   **Volume Ratio (20) is above 2.0** (volume is 2x the prior 20-day average).
    *   **RSI(14) is below 70** (to avoid overbought breakout setups).
2.  **Exit (Stop Loss / Take Profit)**:
    *   The close price falls below the **Donchian Middle Band** (trailing stop loss).
    *   **RSI(14) rises above 80** (climax take profit).

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate volume-range-breakout
```

### Backtesting
To backtest this strategy against any stock:
```bash
saham strategy backtest BBCA --strategy volume-range-breakout
```
