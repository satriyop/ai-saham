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
    assert "coal" in cfg.sector_maps
    assert "oil_gas" in cfg.sector_maps
    assert "energy" in cfg.sector_maps
    assert "plantation" in cfg.sector_maps
    assert "metals" in cfg.sector_maps
    assert "gold" in cfg.sector_maps
    assert "cement" in cfg.sector_maps
    assert "chemicals" in cfg.sector_maps
    assert "property_dev" in cfg.sector_maps
    assert "logistics" in cfg.sector_maps
    assert "telco" in cfg.sector_maps
    assert "poultry" in cfg.sector_maps
    assert "insurance" in cfg.sector_maps
    assert "multifinance" in cfg.sector_maps
    assert "packaging" in cfg.sector_maps
    assert "bank" in cfg.sector_maps
    # Track C residual / dedicated coverage
    for group in (
        "property",
        "transportation",
        "auto",
        "consumer_goods",
        "consumer_non_cyclicals",
        "consumer_staples",
    ):
        assert group in cfg.sector_maps, group
    assert cfg.required_series_tickers() >= frozenset(
        {"CL=F", "IDR=X", "CPO=F", "HG=F", "GC=F", "ZC=F", "ZS=F", "COAL"}
    )
    # Track B: domestic rates maps use BI policy steps, not live ^TNX candles.
    assert "^TNX" not in cfg.required_series_tickers()
    for group in (
        "bank",
        "cement",
        "property_dev",
        "property",
        "telco",
        "insurance",
        "multifinance",
        "auto",
        "consumer_goods",
        "consumer_non_cyclicals",
        "consumer_staples",
    ):
        refs = [r.ref for r in cfg.sector_maps[group]]
        assert "bi_rate_policy" in refs, group
        assert "us_10y" not in refs, group
        assert cfg.policy_series_for_group(group) == ("BI_RATE",)
    for group in ("transportation", "logistics"):
        refs = [r.ref for r in cfg.sector_maps[group]]
        assert "oil_cost" in refs, group
        assert cfg.series_for_group(group) == ("CL=F", "IDR=X")


def test_required_series_from_repo_config():
    series = required_sector_macro_series_tickers()
    assert "CL=F" in series
    assert "IDR=X" in series
    assert "CPO=F" in series  # plantation
    assert "HG=F" in series  # metals
    assert "GC=F" in series  # gold — auto-fetched via fetch market context
    assert "ZC=F" in series  # poultry corn
    assert "ZS=F" in series  # poultry soy
    assert "COAL" in series  # coal proxy ETF
    # Library may still define us_10y; live maps no longer require it for fetch.
    assert "^TNX" not in series


def test_track_c_resolve_prefers_specialists_and_auto_cohort():
    """Dedicated cohorts win over residual bags; ASII resolves via auto group."""
    from src.infrastructure.config.sector_context_config_loader import (
        create_sector_context_evidence_builder,
    )

    sc = create_sector_context_evidence_builder()
    smc = create_sector_macro_context_evidence_builder()

    def resolve(ticker: str) -> str | None:
        return smc.resolve_sector_group(sc.sector_groups_for_ticker(ticker))

    assert resolve("ASII") == "auto"
    assert resolve("AUTO") == "auto"
    assert resolve("AALI") == "plantation"  # not residual consumer_goods
    assert resolve("CPIN") == "poultry"
    assert resolve("PWON") == "property_dev"  # not residual property
    assert resolve("PANI") == "property"
    assert resolve("ICBP") == "consumer_goods"
    assert resolve("UNVR") == "consumer_non_cyclicals"
    assert resolve("BIRD") == "transportation"
    # Intentionally unmapped bags stay unresolved as maps
    assert resolve("GOTO") == "tech"
    assert "tech" not in smc.config.sector_maps


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
