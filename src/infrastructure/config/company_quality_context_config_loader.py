"""Loader for company-quality-context evidence builder config (Phase I prep).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextConfig,
    CompanyQualityContextEvidenceBuilder,
)
from src.application.services.signal_scoring_config import SignalScoringConfig

DEFAULT_COMPANY_QUALITY_CONTEXT_CONFIG_PATH = Path("config/company_quality_context.yaml")
_DEFAULT_NEUTRAL_SCORE = 50.0


def load_company_quality_context_config(
    path: str | Path | None = None,
) -> CompanyQualityContextConfig:
    """Load CompanyQualityContextConfig from YAML file path.

    Falls back to defaults when the config file does not exist.
    """
    cfg_p = Path(path) if path is not None else DEFAULT_COMPANY_QUALITY_CONTEXT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if cfg_p.exists():
        with open(cfg_p, "r") as fh:
            raw = yaml.safe_load(fh) or {}
    return CompanyQualityContextConfig.from_mapping(raw)


def create_company_quality_context_evidence_builder(
    config_path: str | Path | None = None,
    scoring: SignalScoringConfig | None = None,
    neutral_score: float = _DEFAULT_NEUTRAL_SCORE,
) -> CompanyQualityContextEvidenceBuilder:
    """Create CompanyQualityContextEvidenceBuilder with loaded config."""
    config = load_company_quality_context_config(config_path)
    return CompanyQualityContextEvidenceBuilder(
        config, scoring=scoring, neutral_score=neutral_score
    )
