"""Optional plan-swing fetchers — re-export from shared composition.

Layer: Adapter
"""

from src.adapters.composition.swing_optional_fetchers import (
    auto_refresh_swing_data,
    fetch_swing_sentiment,
)

__all__ = ["auto_refresh_swing_data", "fetch_swing_sentiment"]
