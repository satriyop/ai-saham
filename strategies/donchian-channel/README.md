# Donchian Channel Breakout Strategy

Classic trend-following strategy based on Richard Donchian's Price Channels (famously used in the Turtle Trading system).

## Rules

This strategy uses a 20-period lookback window:

1.  **Entry (Long)**: 
    *   The close price breaks above the **Donchian Upper Band** (the highest high of the previous 20 candles).
    *   **RSI(14) is below 70** (to avoid entering at highly exhausted, overbought levels).
2.  **Exit (Stop Loss / Take Profit)**:
    *   The close price falls below the **Donchian Middle Band** (the average of the 20-period upper/lower bands), acting as a trailing stop loss and exit on momentum loss.
    *   **RSI(14) rises above 80** (exit to secure profits during extreme overbought buying climaxes).

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate donchian-channel
```

### Backtesting
To backtest this strategy against any stock:
```bash
saham strategy backtest ADRO --strategy donchian-channel
saham strategy backtest BBCA --strategy donchian-channel --start 2026-01-01 --verbose
```
