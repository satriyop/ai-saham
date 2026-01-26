# Indicator Plugin Development Guide

Create custom technical indicators that integrate seamlessly with the analysis engine.

## Quick Start

1. Copy `_template.py` to a new file (e.g., `my_indicator.py`)
2. Remove the underscore prefix from the filename
3. Update the class name, `name`, and `default_period` attributes
4. Implement the `compute()` method
5. Restart the application to load your plugin

```python
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class RSIIndicator(IndicatorPlugin):
    name = "RSI"           # Uppercase only!
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        # Your implementation here
        return []
```

## Naming Rules

Plugin names **must** match the pattern: `^[A-Z0-9_]+$`

| Valid | Invalid | Reason |
|-------|---------|--------|
| `ATR` | `atr` | No lowercase |
| `RSI_14` | `RSI-14` | No hyphens |
| `EMA200` | `EMA 200` | No spaces |
| `BOLLINGER_BANDS` | `BollingerBands` | No mixed case |

The loader will skip plugins with invalid names and log a warning.

## Plugin Structure

### Required Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique uppercase identifier |
| `default_period` | `int` | Default lookback period |

### Required Methods

```python
def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
    """Compute indicator values."""
    ...
```

## The Compute Contract

### Input

- **candles**: List of `Candle` objects sorted by date **ascending** (oldest first)
- **period**: Lookback period (use `default_period` if none specified)

Each `Candle` has:
- `date: datetime.date`
- `open: Decimal`
- `high: Decimal`
- `low: Decimal`
- `close: Decimal`
- `volume: int`

### Output

Return a `list[Decimal]` representing computed values.

**Date Alignment**: Results align to the **end** of the input data:
- `result[-1]` corresponds to `candles[-1]` (most recent candle)
- `result[0]` corresponds to the first candle with enough history

**Output Length**: Typically:
- `len(candles) - period + 1` for simple averages (SMA)
- `len(candles) - period` for indicators needing previous close (ATR)

### Insufficient Data

Return an **empty list** `[]` if there's not enough data. Never raise exceptions.

```python
if len(candles) < period:
    return []
```

## Best Practices

### DO

- Use `Decimal` for all calculations (financial precision)
- Return empty list when insufficient data
- Keep computations deterministic and reproducible
- Document your algorithm and formula
- Handle edge cases gracefully

### DON'T

- Don't use floating-point arithmetic (`float`)
- Don't access external resources (network, filesystem)
- Don't maintain state between calls
- Don't modify the input candles
- Don't raise exceptions for invalid input

## Restrictions

Plugins operate in a sandboxed context:

1. **No I/O**: No file access, network calls, or database queries
2. **No Side Effects**: Must be pure functions
3. **No Global State**: Each call should be independent
4. **No External Dependencies**: Only use standard library and project imports

## Testing Your Plugin

### Manual Test

```python
from plugins.indicators.my_indicator import MyIndicator
from src.domain.entities.candle import Candle
from decimal import Decimal
from datetime import date

# Create test data
candles = [
    Candle(date=date(2024, 1, i), open=Decimal("100"), high=Decimal("105"),
           low=Decimal("95"), close=Decimal(str(100 + i)), volume=1000)
    for i in range(1, 21)
]

indicator = MyIndicator()
result = indicator.compute(candles, period=14)

print(f"Input: {len(candles)} candles")
print(f"Output: {len(result)} values")
print(f"Latest value: {result[-1] if result else 'N/A'}")
```

### Verify Plugin Loads

```bash
# Run the loader test
python -m pytest tests/infrastructure/plugins/test_indicator_loader.py -v -k "test_load"
```

## Examples

### ATR (Average True Range)

See `atr.py` for a production implementation featuring:
- True Range calculation
- Wilder's smoothing method
- Proper date alignment

### Template

See `_template.py` for a minimal starting point with inline documentation.

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Plugin not discovered | File starts with `_` | Rename file (remove underscore) |
| Plugin skipped | Invalid name format | Use uppercase, digits, underscores only |
| Import error in logs | Missing dependencies | Check imports exist in project |
| Empty results | Insufficient data | Verify candle count >= period |
