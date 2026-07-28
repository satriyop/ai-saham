"""Loader for sector macro context config (ADR-053).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.services.sector_macro_context_evidence_builder import (
    SectorMacroContextConfig,
    SectorMacroContextEvidenceBuilder,
)

DEFAULT_SECTOR_MACRO_CONTEXT_CONFIG_PATH = Path("config/sector_macro_context.yaml")


def load_sector_macro_context_config(
    path: str | Path | None = None,
) -> SectorMacroContextConfig:
    """Load SectorMacroContextConfig from YAML. Raises on invalid / non-DIAGNOSTIC."""
    config_path = Path(path) if path is not None else DEFAULT_SECTOR_MACRO_CONTEXT_CONFIG_PATH
    with open(config_path, "r") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"sector macro config must be a mapping: {config_path}")
    return SectorMacroContextConfig.from_mapping(raw)


def create_sector_macro_context_evidence_builder(
    config_path: str | Path | None = None,
) -> SectorMacroContextEvidenceBuilder:
    """Create SectorMacroContextEvidenceBuilder with loaded config."""
    config = load_sector_macro_context_config(config_path)
    return SectorMacroContextEvidenceBuilder(config)


def required_sector_macro_series_tickers(
    config_path: str | Path | None = None,
) -> frozenset[str]:
    """Series tickers needed by live sector maps (for fetch global context)."""
    return load_sector_macro_context_config(config_path).required_series_tickers()
