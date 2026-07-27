"""Loader for sector context config and the sector universe index (Phase H).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.services.sector_context_evidence_builder import (
    SectorContextConfig,
    SectorContextEvidenceBuilder,
)

DEFAULT_SECTOR_CONTEXT_CONFIG_PATH = Path("config/sector_context.yaml")
DEFAULT_UNIVERSES_PATH = Path("config/universes.yaml")

# Universe keys that represent index membership, not sector groups.
_INDEX_UNIVERSE_KEYS: frozenset[str] = frozenset({"lq45", "idx30", "idx80", "jii", "mbx"})


def load_sector_context_config(
    path: str | Path | None = None,
) -> SectorContextConfig:
    """Load SectorContextConfig from YAML file path."""
    config_path = Path(path) if path is not None else DEFAULT_SECTOR_CONTEXT_CONFIG_PATH
    with open(config_path, "r") as fh:
        raw = yaml.safe_load(fh) or {}
    return SectorContextConfig.from_mapping(raw)


def build_sector_universe_index(
    universes_path: str | Path | None = None,
) -> dict[str, tuple[str, ...]]:
    """Build {universe_group_name: (ticker, ...)} for sector (non-index) groups."""
    uni_p = Path(universes_path) if universes_path is not None else DEFAULT_UNIVERSES_PATH
    result: dict[str, tuple[str, ...]] = {}
    if not uni_p.exists():
        return result
    with open(uni_p, "r") as fh:
        data = yaml.safe_load(fh) or {}
    for key, block in data.items():
        if key in _INDEX_UNIVERSE_KEYS:
            continue
        if not isinstance(block, dict):
            continue
        tickers = block.get("tickers") or []
        if tickers:
            result[key] = tuple(str(t).upper() for t in tickers)
    return result


def create_sector_context_evidence_builder(
    config_path: str | Path | None = None,
    universes_path: str | Path | None = None,
) -> SectorContextEvidenceBuilder:
    """Create SectorContextEvidenceBuilder with loaded config and sector index."""
    config = load_sector_context_config(config_path)
    index = build_sector_universe_index(universes_path)
    return SectorContextEvidenceBuilder(config, index)
