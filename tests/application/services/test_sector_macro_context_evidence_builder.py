"""Tests for SectorMacroContextEvidenceBuilder (ADR-053)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.sector_macro_context_evidence_builder import (
    SectorMacroContextConfig,
    SectorMacroContextEvidenceBuilder,
    SectorMacroContextRequest,
    _piecewise_score,
    _session_return_fraction,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


def _candle(ticker: str, dt: date, close: float) -> Candle:
    return Candle(
        ticker=ticker,
        date=dt,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1_000,
    )


def _make_candles(ticker: str, closes: list[float], start: date | None = None) -> list[Candle]:
    base = start or date(2026, 5, 1)
    return [_candle(ticker, base + timedelta(days=i), c) for i, c in enumerate(closes)]


def _energy_config(**overrides) -> SectorMacroContextConfig:
    raw = {
        "sector_macro_context": {
            "evidence_status": "DIAGNOSTIC",
            "lookback_sessions": 10,
            "min_valid_sessions": 5,
            "min_coverage_to_label": 0.5,
            "score_labels": {"favorable_min": 0.65, "neutral_min": 0.35},
            "regime_thresholds": {"supportive_min": 0.65, "headwind_max": 0.35},
            "factor_library": {
                "coal_futures": {
                    "series": "MTF=F",
                    "kind": "return_sessions",
                    "invert": False,
                    "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                },
                "usd_idr": {
                    "series": "IDR=X",
                    "kind": "return_sessions",
                    "invert": False,
                    "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                },
            },
            "sector_maps": {
                "energy": {
                    "factors": [
                        {"ref": "coal_futures", "weight": 0.65},
                        {"ref": "usd_idr", "weight": 0.35},
                    ]
                }
            },
        }
    }
    # shallow merge overrides into root
    if overrides:
        raw["sector_macro_context"].update(overrides)
    return SectorMacroContextConfig.from_mapping(raw)


class TestConfigValidation:
    def test_rejects_non_diagnostic(self):
        with pytest.raises(ValueError, match="DIAGNOSTIC"):
            SectorMacroContextConfig.from_mapping(
                {
                    "sector_macro_context": {
                        "evidence_status": "PRODUCTION",
                        "factor_library": {
                            "x": {
                                "series": "MTF=F",
                                "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                            }
                        },
                        "sector_maps": {"energy": {"factors": [{"ref": "x", "weight": 1.0}]}},
                    }
                }
            )

    def test_rejects_unknown_ref(self):
        with pytest.raises(ValueError, match="unknown factor_library"):
            SectorMacroContextConfig.from_mapping(
                {
                    "sector_macro_context": {
                        "factor_library": {
                            "coal_futures": {
                                "series": "MTF=F",
                                "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                            }
                        },
                        "sector_maps": {"energy": {"factors": [{"ref": "missing", "weight": 1.0}]}},
                    }
                }
            )

    def test_required_series_tickers_live_maps_only(self):
        cfg = _energy_config()
        # inject library-only factor via raw rebuild
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "coal_futures": {
                        "series": "MTF=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "cpo": {
                        "series": "KO=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                },
                "sector_maps": {"energy": {"factors": [{"ref": "coal_futures", "weight": 1.0}]}},
            }
        }
        cfg = SectorMacroContextConfig.from_mapping(raw)
        assert cfg.required_series_tickers() == frozenset({"MTF=F"})
        assert "KO=F" in cfg.all_library_series_tickers()


class TestSessionReturn:
    def test_positive_return(self):
        candles = _make_candles("MTF=F", [100.0] * 5 + [110.0])
        assert _session_return_fraction(candles, lookback=10, min_valid=5) == pytest.approx(
            0.10, abs=0.001
        )

    def test_insufficient(self):
        candles = _make_candles("MTF=F", [100.0, 110.0])
        assert _session_return_fraction(candles, lookback=10, min_valid=5) is None


class TestPiecewiseScore:
    def test_supportive_boundary(self):
        assert _piecewise_score(0.05, supportive_min=0.05, headwind_max=-0.05) == 1.0

    def test_headwind_boundary(self):
        assert _piecewise_score(-0.05, supportive_min=0.05, headwind_max=-0.05) == 0.0

    def test_midpoint(self):
        mid = _piecewise_score(0.0, supportive_min=0.05, headwind_max=-0.05)
        assert mid == pytest.approx(0.5)


class TestResolveSectorGroup:
    def test_prefers_mapped_membership_over_broad_bag(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "oil_proxy": {
                        "series": "CL=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "cpo": {
                        "series": "CPO=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "usd_idr": {
                        "series": "IDR=X",
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "energy": {
                        "factors": [
                            {"ref": "oil_proxy", "weight": 0.65},
                            {"ref": "usd_idr", "weight": 0.35},
                        ]
                    },
                    "plantation": {
                        "factors": [
                            {"ref": "cpo", "weight": 0.70},
                            {"ref": "usd_idr", "weight": 0.30},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        # consumer_goods first in membership (YAML order style), plantation second
        assert (
            builder.resolve_sector_group(("consumer_goods", "noncyc", "plantation")) == "plantation"
        )
        assert builder.resolve_sector_group(("energy",)) == "energy"
        assert builder.resolve_sector_group(("bank",)) == "bank"  # fallback first
        assert builder.resolve_sector_group(()) is None

    def test_prefers_metals_over_basic_materials(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "copper": {
                        "series": "HG=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "usd_idr": {
                        "series": "IDR=X",
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "metals": {
                        "factors": [
                            {"ref": "copper", "weight": 0.55},
                            {"ref": "usd_idr", "weight": 0.45},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("basic_materials", "metals", "bumn20")) == "metals"

    def test_prefers_bank_over_finance(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "us_10y": {
                        "series": "^TNX",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "bank": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("bank", "finance")) == "bank"

    def test_prefers_gold_over_basic_materials(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "gold_proxy": {
                        "series": "GC=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "usd_idr": {
                        "series": "IDR=X",
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "gold": {
                        "factors": [
                            {"ref": "gold_proxy", "weight": 0.65},
                            {"ref": "usd_idr", "weight": 0.35},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("basic_materials", "gold", "bumn20")) == "gold"

    def test_prefers_cement_and_chemicals_over_basic_materials(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "us_10y": {
                        "series": "^TNX",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "oil_proxy": {
                        "series": "CL=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "usd_idr": {
                        "series": "IDR=X",
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "cement": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    },
                    "chemicals": {
                        "factors": [
                            {"ref": "oil_proxy", "weight": 0.60},
                            {"ref": "usd_idr", "weight": 0.40},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("basic_materials", "cement")) == "cement"
        assert builder.resolve_sector_group(("basic_materials", "chemicals")) == "chemicals"

    def test_prefers_property_dev_logistics_telco(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "us_10y": {
                        "series": "^TNX",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "oil_proxy": {
                        "series": "CL=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "usd_idr": {
                        "series": "IDR=X",
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "property_dev": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    },
                    "logistics": {
                        "factors": [
                            {"ref": "oil_proxy", "weight": 0.60},
                            {"ref": "usd_idr", "weight": 0.40},
                        ]
                    },
                    "telco": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("property", "property_dev")) == "property_dev"
        assert builder.resolve_sector_group(("logistics",)) == "logistics"
        assert builder.resolve_sector_group(("telecommunication", "telco")) == "telco"

    def test_prefers_poultry_over_consumer_goods(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "corn": {
                        "series": "ZC=F",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.03, "headwind_max": -0.03},
                    },
                    "soy": {
                        "series": "ZS=F",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.03, "headwind_max": -0.03},
                    },
                },
                "sector_maps": {
                    "poultry": {
                        "factors": [
                            {"ref": "corn", "weight": 0.55},
                            {"ref": "soy", "weight": 0.45},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("consumer_goods", "noncyc", "poultry")) == "poultry"

    def test_prefers_insurance_multifinance_packaging(self):
        raw = {
            "sector_macro_context": {
                "factor_library": {
                    "us_10y": {
                        "series": "^TNX",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "oil_proxy": {
                        "series": "CL=F",
                        "thresholds": {"supportive_min": 0.05, "headwind_max": -0.05},
                    },
                    "usd_idr": {
                        "series": "IDR=X",
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "insurance": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    },
                    "multifinance": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    },
                    "packaging": {
                        "factors": [
                            {"ref": "oil_proxy", "weight": 0.60},
                            {"ref": "usd_idr", "weight": 0.40},
                        ]
                    },
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        assert builder.resolve_sector_group(("finance", "insurance")) == "insurance"
        assert builder.resolve_sector_group(("finance", "multifinance")) == "multifinance"
        assert builder.resolve_sector_group(("basic_materials", "packaging")) == "packaging"

    def test_poultry_rising_feed_is_headwind(self):
        raw = {
            "sector_macro_context": {
                "lookback_sessions": 10,
                "min_valid_sessions": 5,
                "min_coverage_to_label": 0.5,
                "factor_library": {
                    "corn": {
                        "series": "ZC=F",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.03, "headwind_max": -0.03},
                    },
                    "soy": {
                        "series": "ZS=F",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.03, "headwind_max": -0.03},
                    },
                },
                "sector_maps": {
                    "poultry": {
                        "factors": [
                            {"ref": "corn", "weight": 0.55},
                            {"ref": "soy", "weight": 0.45},
                        ]
                    }
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        corn_up = _make_candles("ZC=F", [400.0] * 5 + [440.0])  # +10%
        soy_up = _make_candles("ZS=F", [1000.0] * 5 + [1100.0])  # +10%
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="CPIN",
                snapshot_date=date(2026, 5, 20),
                sector_group="poultry",
                series_candles={"ZC=F": corn_up, "ZS=F": soy_up},
            )
        )
        assert ev.macro_regime == "HEADWIND"
        assert all(f.score is not None and f.score <= 0.35 for f in ev.factors)


class TestBuilder:
    def test_supportive_energy(self):
        # coal +10% and weaker rupiah (+2% IDR=X) both supportive for energy (invert=false).
        coal = _make_candles("MTF=F", [100.0] * 5 + [110.0])
        usd = _make_candles("IDR=X", [16000.0] * 5 + [16320.0])  # +2% raw
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"MTF=F": coal, "IDR=X": usd},
            )
        )
        assert ev.macro_regime == "SUPPORTIVE"
        assert ev.coverage_score == pytest.approx(1.0)
        assert ev.composite_score is not None and ev.composite_score >= 0.65
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC
        assert len(ev.factors) == 2

    def test_headwind_energy(self):
        coal = _make_candles("MTF=F", [100.0] * 5 + [90.0])  # -10%
        usd = _make_candles("IDR=X", [16000.0] * 5 + [15680.0])  # -2% stronger rupiah headwind
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"MTF=F": coal, "IDR=X": usd},
            )
        )
        assert ev.macro_regime == "HEADWIND"
        assert ev.composite_score is not None and ev.composite_score <= 0.35

    def test_invert_flag_vix_like(self):
        # invert=true: higher series return → lower score (risk series).
        raw = {
            "sector_macro_context": {
                "lookback_sessions": 10,
                "min_valid_sessions": 5,
                "min_coverage_to_label": 0.5,
                "factor_library": {
                    "risk_proxy": {
                        "series": "IDR=X",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    }
                },
                "sector_maps": {"energy": {"factors": [{"ref": "risk_proxy", "weight": 1.0}]}},
            }
        }
        cfg = SectorMacroContextConfig.from_mapping(raw)
        builder = SectorMacroContextEvidenceBuilder(cfg)
        # +2% raw with invert → effective -2% → score 0 → HEADWIND
        usd_up = _make_candles("IDR=X", [16000.0] * 5 + [16320.0])
        ev_up = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"IDR=X": usd_up},
            )
        )
        assert ev_up.factors[0].score == pytest.approx(0.0)
        assert ev_up.macro_regime == "HEADWIND"

        # -2% raw with invert → effective +2% → score 1 → SUPPORTIVE
        usd_dn = _make_candles("IDR=X", [16000.0] * 5 + [15680.0])
        ev_dn = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"IDR=X": usd_dn},
            )
        )
        assert ev_dn.factors[0].score == pytest.approx(1.0)
        assert ev_dn.macro_regime == "SUPPORTIVE"

    def test_missing_one_series_partial_coverage(self):
        coal = _make_candles("MTF=F", [100.0] * 5 + [110.0])
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"MTF=F": coal},  # no IDR=X
            )
        )
        assert ev.coverage_score == pytest.approx(0.5)
        # coverage == min_coverage_to_label 0.5 → still labels
        assert ev.macro_regime == "SUPPORTIVE"
        assert any("usd_idr" in r for r in ev.unavailable_reasons)
        assert sum(1 for f in ev.factors if f.score is not None) == 1

    def test_zero_series_unknown(self):
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={},
            )
        )
        assert ev.macro_regime == "UNKNOWN"
        assert ev.coverage_score == 0.0
        assert ev.composite_score is None

    def test_no_map_unknown(self):
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="BBCA",
                snapshot_date=date(2026, 5, 20),
                sector_group="bank",
                series_candles={},
            )
        )
        assert ev.macro_regime == "UNKNOWN"
        assert "sector_map:missing:bank" in ev.unavailable_reasons[0]

    def test_unresolved_group(self):
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ZZZZ",
                snapshot_date=date(2026, 5, 20),
                sector_group=None,
                series_candles={},
            )
        )
        assert "sector_group:unresolved" in ev.unavailable_reasons[0]

    def test_weight_renorm_when_partial(self):
        # Only coal available: composite should equal coal score (1.0), not 0.65*1.0
        coal = _make_candles("MTF=F", [100.0] * 5 + [110.0])
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"MTF=F": coal},
            )
        )
        assert ev.composite_score == pytest.approx(1.0)

    def test_insufficient_candles_unknown_coverage(self):
        coal = _make_candles("MTF=F", [100.0, 110.0])  # too few
        usd = _make_candles("IDR=X", [16000.0, 16100.0])
        builder = SectorMacroContextEvidenceBuilder(_energy_config())
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="ADRO",
                snapshot_date=date(2026, 5, 20),
                sector_group="energy",
                series_candles={"MTF=F": coal, "IDR=X": usd},
            )
        )
        assert ev.macro_regime == "UNKNOWN"
        assert ev.coverage_score == 0.0

    def test_bank_risk_map_rising_rates_and_idr_are_headwind(self):
        """Defensive bank policy: invert both series so up = headwind."""
        raw = {
            "sector_macro_context": {
                "lookback_sessions": 10,
                "min_valid_sessions": 5,
                "min_coverage_to_label": 0.5,
                "factor_library": {
                    "us_10y": {
                        "series": "^TNX",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "bank": {
                        "factors": [
                            {"ref": "us_10y", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    }
                },
            }
        }
        builder = SectorMacroContextEvidenceBuilder(SectorMacroContextConfig.from_mapping(raw))
        # Rising yields + weaker IDR → both inverted → headwind
        rates_up = _make_candles("^TNX", [4.0] * 5 + [4.2])  # +5%
        idr_up = _make_candles("IDR=X", [16000.0] * 5 + [16320.0])  # +2%
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="BBCA",
                snapshot_date=date(2026, 5, 20),
                sector_group="bank",
                series_candles={"^TNX": rates_up, "IDR=X": idr_up},
            )
        )
        assert ev.macro_regime == "HEADWIND"
        assert all(f.score is not None and f.score <= 0.35 for f in ev.factors)

        # Falling yields + stronger IDR → supportive
        rates_dn = _make_candles("^TNX", [4.2] * 5 + [4.0])
        idr_dn = _make_candles("IDR=X", [16320.0] * 5 + [16000.0])
        ev2 = builder.build(
            SectorMacroContextRequest(
                ticker="BBCA",
                snapshot_date=date(2026, 5, 20),
                sector_group="bank",
                series_candles={"^TNX": rates_dn, "IDR=X": idr_dn},
            )
        )
        assert ev2.macro_regime == "SUPPORTIVE"
