"""Tests for the company-quality-context infrastructure loader (Phase I prep)."""

import yaml

from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextEvidenceBuilder,
)
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
    load_company_quality_context_config,
)


def test_create_company_quality_context_evidence_builder_does_not_raise():
    builder = create_company_quality_context_evidence_builder()
    assert isinstance(builder, CompanyQualityContextEvidenceBuilder)


def test_load_company_quality_context_config_reads_yaml(tmp_path):
    config_path = tmp_path / "company_quality_context.yaml"
    config_path.write_text(
        yaml.dump({"axis_weights": {"valuation": 2.0}, "seasonality_weight": 0.25})
    )

    config = load_company_quality_context_config(config_path)

    assert config.valuation_weight == 2.0
    assert config.seasonality_weight == 0.25


def test_load_company_quality_context_config_missing_file_returns_defaults(tmp_path):
    config = load_company_quality_context_config(tmp_path / "nonexistent.yaml")

    assert config.valuation_weight == 1.0
    assert config.seasonality_weight == 0.5
