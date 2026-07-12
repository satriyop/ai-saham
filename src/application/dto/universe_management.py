"""DTOs for universe management use cases.

Layer: Application
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UniverseConfigEntry:
    """Represents a single universe entry in the YAML config."""

    updated: str
    tickers: tuple[str, ...]
    sector_id: int | None = None
    subsector_id: int | None = None


@dataclass(frozen=True)
class UniverseUpdateItem:
    """Result of updating a single universe."""

    key: str
    universe_type: str
    tickers: tuple[str, ...]
    previous_count: int
    delta: int


@dataclass(frozen=True)
class UniverseUpdateResult:
    """Result of the update universe workflow."""

    updated: tuple[UniverseUpdateItem, ...]
    failed: tuple[str, ...]
    config_path: Path


@dataclass(frozen=True)
class UniverseDiscoverItem:
    """Discoverable universe from Stockbit."""

    key: str
    universe_type: str
    subsector_id: int | str
    sector_id: int


@dataclass(frozen=True)
class UniverseCreateResult:
    """Result of creating a custom universe."""

    universe_name: str
    tickers: tuple[str, ...]
    sector_id: int
    subsector_id: int | None
    config_path: Path


@dataclass(frozen=True)
class UniverseInspectRow:
    """Row for inspect output tables."""

    id: str
    name: str
    count: str


@dataclass(frozen=True)
class UniverseInspectResult:
    """Result of inspect universe workflow."""

    title: str
    rows: tuple[UniverseInspectRow, ...]
    total: int | None = None
    tip_lines: tuple[str, ...] = ()
