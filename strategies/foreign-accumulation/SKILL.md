# Foreign Accumulation

**Type:** strategy

## Description

Detects foreign investor accumulation patterns on IDX stocks. Combines foreign flow data with RSI confirmation.

## When to Use

Screening for stocks with sustained institutional/foreign buying. Best in trending or early-trend market conditions.

## Tags

`foreign-flow`, `institutional`, `accumulation`, `idx`

## CLI Usage

```bash
saham strategy validate foreign-accumulation
saham backtest BBCA --strategy foreign-accumulation
```

## Dependencies

- CONSECUTIVE_FOREIGN_BUY
- FOREIGN_FLOW
- RSI
- SMA

## Data Requirements

- broker_flow
- ohlcv

## Rules Summary

- **foreign_accumulation_strong** (LOW_RISK): Strong foreign accumulation with 3+ consecutive buy days
- **foreign_accumulation_moderate** (LOW_RISK): Foreign accumulation with RSI below overbought level
- **foreign_distribution** (HIGH_RISK): Heavy foreign selling - potential distribution
- **overbought_no_support** (HIGH_RISK): RSI overbought while foreign selling

## Limitations

- Requires broker flow data (run broker fetch first)
- May lag actual accumulation by 1-2 trading days
- Not suitable for intraday analysis

## Examples

- Foreign accumulation with RSI confirmation on BBRI
- Detect distribution when foreigners sell consistently

<!-- rules_hash: 56e98107bfc8d028cc80e6f7f0a5d1eec9e9a37761a8a1d2078d67ce70fd1c3e -->

---
*Auto-generated from strategy.skill.yaml. Do not edit directly.*
