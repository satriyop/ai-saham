"""Tests for TickerProfileConfigLoader in infrastructure."""

from __future__ import annotations

import yaml

from src.application.dto.ticker_profile import TickerProfileConfig
from src.application.services.ticker_profile_classifier import TickerProfileClassifier
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
    load_ticker_profile_config,
    load_ticker_universe_index,
)


def test_profile_yaml_loads_into_config(tmp_path):
    config_data = {
        "ticker_profile": {
            "evidence_status": "DIAGNOSTIC",
            "profile_window_days": 20,
            "market_cap_thresholds_idr": {
                "large": 5_000_000_000_000,
                "mid": 500_000_000_000,
                "small": 100_000_000_000,
            },
            "index_membership_scores": {
                "lq45": 1.0,
                "idx30": 0.9,
            },
            "liquidity_thresholds": {
                "high_daily_value_idr": 20_000_000_000,
                "low_daily_value_idr": 200_000_000,
            },
            "volatility_thresholds": {
                "high_atr_pct": 0.04,
                "low_atr_pct": 0.004,
            },
            "sparse_history_threshold": 5,
            "conservative_fallback_confidence": 0.25,
            "exposure_weights": {
                "foreign_institutional": {
                    "foreign_flow": 0.5,
                    "index_membership": 0.5,
                }
            },
        }
    }
    p = tmp_path / "ticker_profile.yaml"
    with open(p, "w") as f:
        yaml.dump(config_data, f)

    config = load_ticker_profile_config(p)
    assert isinstance(config, TickerProfileConfig)
    assert config.profile_window_days == 20
    assert config.market_cap_large == 5_000_000_000_000
    assert config.index_membership_scores == {"lq45": 1.0, "idx30": 0.9}
    assert config.liquidity_high == 20_000_000_000.0
    assert config.volatility_high == 0.04
    assert config.sparse_history_threshold == 5
    assert config.conservative_fallback_confidence == 0.25
    assert config.exposure_weights == {
        "foreign_institutional": {"foreign_flow": 0.5, "index_membership": 0.5}
    }


def test_missing_universes_yaml_returns_empty_dict(tmp_path):
    p = tmp_path / "non_existent_universes.yaml"
    index = load_ticker_universe_index(p)
    assert index == {}


def test_universes_yaml_builds_reverse_index_filtered(tmp_path):
    universes_data = {
        "lq45": {"tickers": ["BBCA", "BMRI"]},
        "idx30": {"tickers": ["BBCA", "ASII"]},
        "bank": {"tickers": ["BBCA", "BBRI"]},
        "energy": {"tickers": ["ADRO"]},
        "mbx": {"tickers": ["BMRI", "TLKM"]},
    }
    p = tmp_path / "universes.yaml"
    with open(p, "w") as f:
        yaml.dump(universes_data, f)

    index = load_ticker_universe_index(p)
    # lq45, idx30, mbx are included. bank and energy are excluded.
    assert "BBCA" in index
    assert set(index["BBCA"]) == {"lq45", "idx30"}
    assert "BMRI" in index
    assert set(index["BMRI"]) == {"lq45", "mbx"}
    assert "ASII" in index
    assert index["ASII"] == ("idx30",)
    assert "TLKM" in index
    assert index["TLKM"] == ("mbx",)

    assert "BBRI" not in index
    assert "ADRO" not in index


def test_create_ticker_profile_classifier_returns_instance(tmp_path):
    profile_data = {
        "ticker_profile": {
            "index_membership_scores": {"lq45": 1.0},
        }
    }
    universes_data = {"lq45": {"tickers": ["BBCA"]}}
    prof_p = tmp_path / "ticker_profile.yaml"
    with open(prof_p, "w") as f:
        yaml.dump(profile_data, f)

    univ_p = tmp_path / "universes.yaml"
    with open(univ_p, "w") as f:
        yaml.dump(universes_data, f)

    classifier = create_ticker_profile_classifier(profile_path=prof_p, universes_path=univ_p)
    assert isinstance(classifier, TickerProfileClassifier)
    assert classifier._universe_index == {"BBCA": ("lq45",)}
    assert classifier._config.index_membership_scores == {"lq45": 1.0}
