# RSI Momentum

**Type:** strategy

## Description

Momentum strategy combining RSI extremes with SMA trend confirmation. Buys oversold dips in uptrends, exits on overbought or trend breakdown.

## When to Use

Trending markets where pullbacks are buying opportunities. Works best with liquid large-cap stocks.

## Tags

`momentum`, `rsi`, `trend-following`, `mean-reversion`

## CLI Usage

```bash
saham strategy validate rsi-momentum
saham backtest BBCA --strategy rsi-momentum
```

## Dependencies

- RSI
- SMA

## Data Requirements

- ohlcv

## Rules Summary

- **oversold_uptrend** (LOW_RISK): RSI oversold while price above SMA50 - uptrend dip buy
- **overbought_exit** (HIGH_RISK): RSI overbought - take profit
- **trend_breakdown** (HIGH_RISK): Price below SMA50 with weakening RSI - trend broken

## Limitations

- Underperforms in range-bound/sideways markets
- May generate false signals during trend transitions
- Single timeframe analysis only

## Examples

- Buy BBCA on RSI oversold dip while still in uptrend
- Exit when RSI overbought or price breaks below SMA50

<!-- rules_hash: 6dbcc55204b285d91d1a968d947b674f25d04df9f4bac477beff3cc2b21b9097 -->

---
*Auto-generated from strategy.skill.yaml. Do not edit directly.*
