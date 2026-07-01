"""Ticker classification utilities.

Layer: Domain (Pure functions, standard library only)
"""

def is_non_idx_ticker(ticker: str, custom_non_idx: set[str] | None = None) -> bool:
    """Return True if the ticker is a global/non-IDX ticker.

    Examples of global/non-IDX tickers:
    - ^VIX, ^DJI (Indices starting with ^)
    - IDR=X (Currencies ending with =X)
    - KO=F, MTF=F (Futures ending with =F)
    - EIDO (US ETF, passed via custom_non_idx if configured)
    """
    ticker_upper = ticker.upper().strip()
    if custom_non_idx and ticker_upper in custom_non_idx:
        return True
    return (
        ticker_upper.startswith("^")
        or ticker_upper.endswith("=X")
        or ticker_upper.endswith("=F")
    )
