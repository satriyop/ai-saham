"""
Universe loader service.

Resolves ticker lists from named universes or explicit ticker arguments.
Universe lists are stored in config/universes.yaml and refreshed via
`saham fetch universe update` (Stockbit Exodus API).

Layer: Application
"""

from pathlib import Path

from src.application.ports.universe_config_loader import UniverseConfigLoader
from src.domain.ports.broker_data_repository import BrokerDataRepository

UNIVERSE_CONFIG_PATH = Path("config/universes.yaml")


class UniverseNotFoundError(Exception):
    pass


def load_universe(
    name: str,
    loader: UniverseConfigLoader,
    config_path: Path = UNIVERSE_CONFIG_PATH,
) -> list[str]:
    """Return sorted list of tickers for a named universe.

    Args:
        name: Universe name — one of lq45, idx80, idx30, jii, bumn20
        loader: Injected UniverseConfigLoader port
        config_path: Path to universes.yaml

    Raises:
        UniverseNotFoundError: If universe name is not in config
        FileNotFoundError: If config file does not exist
    """
    data = loader.load_config(config_path)

    if name not in data:
        available = ", ".join(data.keys())
        raise UniverseNotFoundError(
            f"Universe '{name}' not found. Available: {available}"
        )

    return list(data[name]["tickers"])


def load_universe_entry(
    name: str,
    loader: UniverseConfigLoader,
    config_path: Path = UNIVERSE_CONFIG_PATH,
) -> tuple[list[str], str]:
    """Return (tickers, updated_str) for a named universe in a single file read.

    Avoids the double parse that calling load_universe() then load_universe_meta()
    would incur.

    Raises:
        UniverseNotFoundError: If universe name is not in config.
        FileNotFoundError: If config file does not exist.
    """
    data = loader.load_config(config_path)
    if name not in data:
        available = ", ".join(data.keys())
        raise UniverseNotFoundError(
            f"Universe '{name}' not found. Available: {available}"
        )
    entry = data[name]
    return list(entry.get("tickers", [])), str(entry.get("updated", "unknown"))


def load_universe_meta(
    loader: UniverseConfigLoader,
    config_path: Path = UNIVERSE_CONFIG_PATH,
) -> dict[str, dict]:
    """Return metadata (updated date, count) for all universes.

    Returns:
        Dict mapping universe name → {updated, count}
    """
    try:
        data = loader.load_config(config_path)
    except FileNotFoundError:
        return {}

    return {
        name: {
            "updated": entry.get("updated", "unknown"),
            "count": len(entry.get("tickers", [])),
        }
        for name, entry in data.items()
    }


def load_cached_tickers(
    repository: BrokerDataRepository,
) -> list[str]:
    """Return all tickers that have broker flow data in the local DB.

    Uses the passed BrokerDataRepository.

    Args:
        repository: BrokerDataRepository port instance

    Returns:
        Sorted list of ticker strings
    """
    try:
        return repository.get_cached_tickers()
    except Exception:
        return []


def resolve_tickers(
    universe: str | None,
    explicit: list[str],
    db_path: Path,
    loader: UniverseConfigLoader,
    config_path: Path = UNIVERSE_CONFIG_PATH,
    repository: BrokerDataRepository | None = None,
) -> list[str]:
    """Combine universe and explicit tickers into a deduplicated list.

    Args:
        universe: Named universe or "cached" (or None)
        explicit: Explicit ticker symbols passed as arguments
        db_path: Path to SQLite DB (used when universe="cached")
        loader: Injected UniverseConfigLoader port
        config_path: Path to universes.yaml
        repository: Optional BrokerDataRepository port instance

    Returns:
        Deduplicated sorted list of ticker strings

    Raises:
        ValueError: If universe is 'cached' and repository is None.
        UniverseNotFoundError: If universe name is unknown
        FileNotFoundError: If universe config is missing
    """
    tickers: list[str] = []

    if universe == "cached":
        if repository is None:
            raise ValueError("BrokerDataRepository is required when universe='cached'")
        tickers.extend(load_cached_tickers(repository))
    elif universe is not None:
        tickers.extend(load_universe(universe, loader, config_path))

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
