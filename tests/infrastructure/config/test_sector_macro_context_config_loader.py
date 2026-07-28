"""Tests for sector macro context infrastructure loader (ADR-053)."""

import yaml

from src.application.services.sector_macro_context_evidence_builder import (
    SectorMacroContextEvidenceBuilder,
)
from src.infrastructure.config.sector_macro_context_config_loader import (
    create_sector_macro_context_evidence_builder,
    load_sector_macro_context_config,
    required_sector_macro_series_tickers,
)


def test_create_builder_from_repo_config():
    builder = create_sector_macro_context_evidence_builder()
    assert isinstance(builder, SectorMacroContextEvidenceBuilder)
    cfg = builder.config
    assert "energy" in cfg.sector_maps
    assert "plantation" in cfg.sector_maps
    assert cfg.required_series_tickers() >= frozenset({"CL=F", "IDR=X", "CPO=F"})


def test_required_series_from_repo_config():
    series = required_sector_macro_series_tickers()
    assert "CL=F" in series
    assert "IDR=X" in series
    assert "CPO=F" in series  # live plantation map


def test_load_rejects_non_diagnostic(tmp_path):
    path = tmp_path / "smc.yaml"
    path.write_text(
        yaml.dump(
            {
                "sector_macro_context": {
                    "evidence_status": "LOW_WEIGHT",
                    "factor_library": {
                        "coal_futures": {
                            "series": "MTF=F",
                            "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                        }
                    },
                    "sector_maps": {
                        "energy": {"factors": [{"ref": "coal_futures", "weight": 1.0}]}
                    },
                }
            }
        )
    )
    import pytest

    with pytest.raises(ValueError, match="DIAGNOSTIC"):
        load_sector_macro_context_config(path)


def test_load_rejects_bad_ref(tmp_path):
    path = tmp_path / "smc.yaml"
    path.write_text(
        yaml.dump(
            {
                "sector_macro_context": {
                    "factor_library": {
                        "coal_futures": {
                            "series": "MTF=F",
                            "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                        }
                    },
                    "sector_maps": {"energy": {"factors": [{"ref": "nope", "weight": 1.0}]}},
                }
            }
        )
    )
    import pytest

    with pytest.raises(ValueError, match="unknown factor_library"):
        load_sector_macro_context_config(path)
