# Defensive Reversion Strategy

Mean-reversion strategy designed for stable consumer stocks that have steady demand, making pullbacks to oversold support reliable swing buy points.

## Rules

1.  **Entry (Long)**: 
    *   **RSI(14) is below 35** (price is oversold near historical range support).
2.  **Exit (Stop Loss / Take Profit)**:
    *   **RSI(14) rises above 65** (swing rebound profit target achieved).
    *   **RSI(14) falls below 25** (support broken stop loss).

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate defensive-reversion
```

### Backtesting
To backtest this strategy against INDF or JPFA:
```bash
saham strategy backtest INDF --strategy defensive-reversion
saham strategy backtest JPFA --strategy defensive-reversion
```
