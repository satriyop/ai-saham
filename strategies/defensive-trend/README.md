# Defensive Trend Strategy

Trend-following strategy designed specifically for defensive consumer goods (staples, non-cyclicals) that tend to outperform or hold their trend during market corrections.

## Rules

1.  **Entry (Long)**: 
    *   The close price is above the **50-day EMA** (verifying a medium-term uptrend).
    *   **RSI(14) is between 45 and 65** (healthy rising trend, not overbought).
2.  **Exit (Stop Loss / Take Profit)**:
    *   The close price falls below the **50-day EMA** (stop loss).
    *   **RSI(14) rises above 75** (take profit target).

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate defensive-trend
```

### Backtesting
To backtest this strategy against INDF or JPFA:
```bash
saham strategy backtest INDF --strategy defensive-trend
saham strategy backtest JPFA --strategy defensive-trend
```
