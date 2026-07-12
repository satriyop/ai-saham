"""Tests for the sector context infrastructure loader (Phase H)."""

import yaml

from src.application.services.sector_context_evidence_builder import (
    SectorContextEvidenceBuilder,
)
from src.infrastructure.config.sector_context_config_loader import (
    build_sector_universe_index,
    create_sector_context_evidence_builder,
    load_sector_context_config,
)


def test_create_sector_context_evidence_builder_does_not_raise():
    # Smoke test — ensure the factory doesn't crash with real config files.
    builder = create_sector_context_evidence_builder()
    assert isinstance(builder, SectorContextEvidenceBuilder)


def test_load_sector_context_config_reads_yaml(tmp_path):
    config_path = tmp_path / "sector_context.yaml"
    config_path.write_text(yaml.dump({"min_peer_count": 5}))

    config = load_sector_context_config(config_path)

    assert config.min_peer_count == 5


def test_build_sector_universe_index_excludes_index_groups(tmp_path):
    universes_path = tmp_path / "universes.yaml"
    universes_path.write_text(
        yaml.dump(
            {
                "lq45": {"tickers": ["BBCA"]},
                "bank": {"tickers": ["bbca", "bbri"]},
            }
        )
    )

    index = build_sector_universe_index(universes_path)

    assert "lq45" not in index
    assert index["bank"] == ("BBCA", "BBRI")


def test_build_sector_universe_index_missing_file_returns_empty(tmp_path):
    index = build_sector_universe_index(tmp_path / "nonexistent.yaml")
    assert index == {}
