"""Pure universe-index logic to build reverse index for index membership."""

from __future__ import annotations

from typing import Any

INDEX_UNIVERSE_KEYS: frozenset[str] = frozenset({"lq45", "idx30", "idx80", "jii", "mbx"})


def build_ticker_universe_index(
    universes: dict[str, Any] | None,
) -> dict[str, tuple[str, ...]]:
    """Build a reverse ticker-to-index mapping from universes dict.

    - Input is already-parsed mapping data, not a file path.
    - Ignore non-index universe keys.
    - Ignore non-dict universe blocks.
    - Uppercase ticker codes.
    - Preserve insertion order per ticker.
    - Do not import YAML or Path here.
    """
    reverse: dict[str, list[str]] = {}
    if not isinstance(universes, dict):
        return {}

    for key, block in universes.items():
        if key not in INDEX_UNIVERSE_KEYS:
            continue
        if not isinstance(block, dict):
            continue
        for ticker in block.get("tickers") or []:
            code = str(ticker).upper()
            bucket = reverse.setdefault(code, [])
            if key not in bucket:
                bucket.append(key)
    return {code: tuple(keys) for code, keys in reverse.items()}
