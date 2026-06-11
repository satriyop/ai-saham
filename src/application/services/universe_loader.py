"""
Universe loader service.

Resolves ticker lists from named universes (lq45, idx80, idxcomp100)
or explicit ticker arguments. Used by `saham update` and
`saham screen accumulation` to determine which stocks to process.

Layer: Application
"""

from pathlib import Path

import yaml

UNIVERSE_CONFIG_PATH = Path("config/universes.yaml")
SUPPORTED_UNIVERSES = ("lq45", "idx80", "idxcomp100")


class UniverseNotFoundError(Exception):
    pass


def load_universe(
    name: str,
    config_path: Path = UNIVERSE_CONFIG_PATH,
) -> list[str]:
    """Return sorted list of tickers for a named universe.

    Args:
        name: Universe name — one of lq45, idx80, idxcomp100
        config_path: Path to universes.yaml

    Raises:
        UniverseNotFoundError: If universe name is not in config
        FileNotFoundError: If config file does not exist
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Universe config not found at '{config_path}'. "
            "Run: saham universe update"
        )

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if name not in data:
        available = ", ".join(data.keys())
        raise UniverseNotFoundError(
            f"Universe '{name}' not found. Available: {available}"
        )

    return list(data[name]["tickers"])


def load_universe_meta(
    config_path: Path = UNIVERSE_CONFIG_PATH,
) -> dict[str, dict]:
    """Return metadata (updated date, count) for all universes.

    Returns:
        Dict mapping universe name → {updated, count}
    """
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return {
        name: {
            "updated": entry.get("updated", "unknown"),
            "count": len(entry.get("tickers", [])),
        }
        for name, entry in data.items()
    }


def load_cached_tickers(db_path: Path) -> list[str]:
    """Return all tickers that have broker flow data in the local DB.

    Args:
        db_path: Path to SQLite database

    Returns:
        Sorted list of ticker strings
    """
    import sqlite3

    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ticker FROM broker_summaries ORDER BY ticker"
        )
        return [row[0] for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def resolve_tickers(
    universe: str | None,
    explicit: list[str],
    db_path: Path,
    config_path: Path = UNIVERSE_CONFIG_PATH,
) -> list[str]:
    """Combine universe and explicit tickers into a deduplicated list.

    Args:
        universe: Named universe or "cached" (or None)
        explicit: Explicit ticker symbols passed as arguments
        db_path: Path to SQLite DB (used when universe="cached")
        config_path: Path to universes.yaml

    Returns:
        Deduplicated sorted list of ticker strings

    Raises:
        UniverseNotFoundError: If universe name is unknown
        FileNotFoundError: If universe config is missing
    """
    tickers: list[str] = []

    if universe == "cached":
        tickers.extend(load_cached_tickers(db_path))
    elif universe is not None:
        tickers.extend(load_universe(universe, config_path))

    for t in explicit:
        tickers.append(t.upper())

    # Deduplicate while preserving order (universe first, then explicit)
    seen: set[str] = set()
    result: list[str] = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            result.append(t)

    return result
