# Stochastic Mean Reversion Strategy

A pure mean-reversion strategy designed to trade short-term swing lows and capitulation bottoms during consolidating or neutral market regimes.

## Rules

This strategy uses the Stochastic %K and RSI indicators:

1.  **Entry (Long)**: 
    *   **Stochastic %K is below 15** (deep oversold).
    *   **RSI(14) is below 35** (momentum confirmation of capitulation).
2.  **Exit (Stop Loss / Take Profit)**:
    *   **Stochastic %K rises above 85** (profit target at overbought extreme).
    *   The close price falls below the **20-day EMA (Trailing Stop)**, signaling that the bounce has failed.

## Usage

### Validation
To validate this strategy config:
```bash
saham strategy validate stochastic-reversion
```

### Backtesting
To backtest this strategy against any stock:
```bash
saham strategy backtest BBCA --strategy stochastic-reversion
```
