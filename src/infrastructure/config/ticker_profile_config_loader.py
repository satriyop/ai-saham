"""Loader for ticker profile config and universes mapping."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.dto.ticker_profile import TickerProfileConfig
from src.application.services.ticker_index_membership_resolver import (
    build_ticker_universe_index,
)
from src.application.services.ticker_profile_classifier import (
    TickerProfileClassifier,
)

DEFAULT_PROFILE_CONFIG_PATH = Path("config/ticker_profile.yaml")
DEFAULT_UNIVERSES_PATH = Path("config/universes.yaml")


def load_ticker_profile_config(
    path: str | Path | None = None,
) -> TickerProfileConfig:
    """Load TickerProfileConfig from YAML file path."""
    p = Path(path) if path is not None else DEFAULT_PROFILE_CONFIG_PATH
    with open(p, "r") as handle:
        raw = yaml.safe_load(handle) or {}
    return TickerProfileConfig.from_mapping(raw)


def load_ticker_universe_index(
    path: str | Path | None = None,
) -> dict[str, tuple[str, ...]]:
    """Load and build universe index from universes YAML file path."""
    p = Path(path) if path is not None else DEFAULT_UNIVERSES_PATH
    if not p.exists():
        return {}
    with open(p, "r") as handle:
        raw = yaml.safe_load(handle) or {}
    return build_ticker_universe_index(raw)


def create_ticker_profile_classifier(
    profile_path: str | Path | None = None,
    universes_path: str | Path | None = None,
) -> TickerProfileClassifier:
    """Create TickerProfileClassifier with loaded config and universe index."""
    config = load_ticker_profile_config(profile_path)
    index = load_ticker_universe_index(universes_path)
    return TickerProfileClassifier(config=config, ticker_universe_index=index)
