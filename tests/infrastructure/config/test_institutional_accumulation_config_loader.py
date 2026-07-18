"""Tests for the institutional accumulation infrastructure loader (Phase E)."""

import pytest
import yaml

from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)


def test_load_institutional_accumulation_config_reads_real_default_file():
    config = load_institutional_accumulation_config()
    config.validate()  # weight groups must sum to 1.00 in the real file
    assert not hasattr(config, "evidence_status")


def test_load_institutional_accumulation_config_explicit_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_institutional_accumulation_config(tmp_path / "nonexistent.yaml")


def test_load_institutional_accumulation_config_reads_custom_yaml(tmp_path):
    config_path = tmp_path / "institutional_accumulation.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "institutional_accumulation": {
                    "windows": {"foreign_vwap_days": 15},
                }
            }
        )
    )

    config = load_institutional_accumulation_config(config_path)

    assert config.foreign_vwap_days == 15


def test_load_institutional_accumulation_config_rejects_legacy_evidence_status(tmp_path):
    config_path = tmp_path / "institutional_accumulation.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "institutional_accumulation": {
                    "evidence_status": "PRODUCTION",
                }
            }
        )
    )

    with pytest.raises(ValueError) as exc_info:
        load_institutional_accumulation_config(config_path)
    assert str(exc_info.value) == (
        "institutional_accumulation.evidence_status is not configurable; "
        "evidence authority is owned by the validated central authority registry"
    )
