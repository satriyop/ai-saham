"""Unit tests for BuildTickerSectorContextUseCase (descriptive L2a+L2b)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from src.application.services.candidate_evidence_data_loader import (
    SectorContextInputs,
    SectorMacroContextInputs,
)
from src.application.use_case.build_ticker_sector_context_use_case import (
    BuildTickerSectorContextRequest,
    BuildTickerSectorContextUseCase,
)
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
from src.domain.value_objects.sector_macro_context_evidence import (
    MacroFactorScore,
    SectorMacroContextEvidence,
)

pytestmark = pytest.mark.agent


class _FakeLoader:
    def load_sector_context_inputs(self, **kwargs):
        return SectorContextInputs(
            ticker_candles=(),
            peer_candles={},
            ihsg_20d_return=0.01,
        )

    def load_sector_macro_context_inputs(self, **kwargs):
        return SectorMacroContextInputs(series_candles={}, policy_steps=None)


class _ScBuilder:
    def sector_groups_for_ticker(self, ticker):
        return ("bank",)

    def peers_for_ticker(self, ticker):
        return ("BBRI", "BMRI", "BBNI")

    def build(self, request):
        return SectorContextEvidence(
            sector="bank",
            peer_count=3,
            peer_tickers=("BBRI", "BMRI", "BBNI"),
            sector_20d_return=0.02,
            sector_vs_ihsg_20d=0.01,
            sector_breadth=0.67,
            ticker_vs_sector_rs=-0.005,
            sector_regime="BULLISH",
            coverage_score=1.0,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(),
        )


class _SmcConfig:
    def series_for_group(self, group):
        return ()

    def policy_series_for_group(self, group):
        return ()

    def max_policy_lookback_days_for_group(self, group):
        return 180


class _SmcBuilder:
    config = _SmcConfig()

    def resolve_sector_group(self, groups):
        return groups[0] if groups else None

    def build(self, request):
        return SectorMacroContextEvidence(
            sector_group="bank",
            as_of_date=request.snapshot_date,
            factors=(
                MacroFactorScore(
                    name="usd_idr",
                    series="USDIDR",
                    value=0.001,
                    score=0.6,
                    weight=1.0,
                    label="NEUTRAL",
                    rationale="flat FX",
                ),
            ),
            composite_score=0.6,
            macro_regime="NEUTRAL",
            coverage_score=1.0,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(),
        )


def test_happy_path_both_dimensions_no_scores_on_result() -> None:
    uc = BuildTickerSectorContextUseCase(
        _FakeLoader(),  # type: ignore[arg-type]
        sector_context_builder_factory=lambda: _ScBuilder(),  # type: ignore[return-value]
        sector_macro_context_builder_factory=lambda: _SmcBuilder(),  # type: ignore[return-value]
        market_repository=None,
    )
    result = uc.execute(
        BuildTickerSectorContextRequest(ticker="bbca", as_of=date(2026, 8, 1), peers_limit=2)
    )
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.peer_context is not None
    assert result.peer_context.sector_regime == "BULLISH"
    assert len(result.peer_context.peer_tickers) == 2  # capped
    assert result.macro_context is not None
    assert result.macro_context.macro_regime == "NEUTRAL"
    assert result.macro_context.factors[0].label == "NEUTRAL"
    assert not hasattr(result.macro_context.factors[0], "score")
    assert not hasattr(result.macro_context, "composite_score")
    assert result.warnings == ()


def test_both_fail_returns_none() -> None:
    class BrokenSc:
        def sector_groups_for_ticker(self, ticker):
            raise RuntimeError("no")

        def peers_for_ticker(self, ticker):
            return ()

    class BrokenSmc:
        config = _SmcConfig()

        def resolve_sector_group(self, groups):
            raise RuntimeError("no")

    uc = BuildTickerSectorContextUseCase(
        _FakeLoader(),  # type: ignore[arg-type]
        sector_context_builder_factory=lambda: BrokenSc(),  # type: ignore[return-value]
        sector_macro_context_builder_factory=lambda: BrokenSmc(),  # type: ignore[return-value]
    )
    assert (
        uc.execute(BuildTickerSectorContextRequest(ticker="BBCA", as_of=date(2026, 8, 1))) is None
    )
