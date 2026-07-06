"""Tests for SectorContextEvidenceBuilder (Phase H)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.application.services.sector_context_evidence_builder import (
    SectorContextConfig,
    SectorContextEvidenceBuilder,
    SectorContextRequest,
    _classify_regime,
    _compute_return,
    _coverage,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _candle(ticker: str, dt: str, close: float) -> Candle:
    return Candle(
        ticker=ticker,
        date=date.fromisoformat(dt),
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1_000_000,
    )


def _make_candles(ticker: str, closes: list[float]) -> list[Candle]:
    base = date(2026, 5, 1)
    from datetime import timedelta
    return [
        _candle(ticker, (base + timedelta(days=i)).isoformat(), c)
        for i, c in enumerate(closes)
    ]


def _default_config() -> SectorContextConfig:
    return SectorContextConfig(
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        min_peer_count=3,
        max_peer_count=20,
        lookback_sessions=20,
        min_valid_sessions_per_peer=5,
        bullish_sector_vs_ihsg_min=0.01,
        bullish_breadth_min=0.55,
        bearish_sector_vs_ihsg_max=-0.01,
        bearish_breadth_max=0.45,
    )


# --------------------------------------------------------------------------- #
# Unit tests for pure helpers
# --------------------------------------------------------------------------- #

class TestComputeReturn:
    def test_basic_positive_return(self):
        candles = _make_candles("A", [100.0] * 5 + [110.0])  # 10% return
        result = _compute_return(candles, lookback=10, min_valid=5)
        assert result == pytest.approx(0.10, abs=0.001)

    def test_negative_return(self):
        candles = _make_candles("A", [100.0] * 5 + [90.0])
        result = _compute_return(candles, lookback=10, min_valid=5)
        assert result == pytest.approx(-0.10, abs=0.001)

    def test_insufficient_candles_returns_none(self):
        candles = _make_candles("A", [100.0, 110.0])
        result = _compute_return(candles, lookback=20, min_valid=5)
        assert result is None

    def test_zero_ref_close_returns_none(self):
        candles = _make_candles("A", [0.0] * 10 + [100.0])
        result = _compute_return(candles, lookback=20, min_valid=5)
        assert result is None


class TestCoverage:
    def test_exactly_min_peers(self):
        assert _coverage(3, 3) == pytest.approx(1.0)

    def test_more_than_min_peers_capped(self):
        assert _coverage(10, 3) == pytest.approx(1.0)

    def test_fewer_than_min_peers(self):
        assert _coverage(1, 3) == pytest.approx(1.0 / 3.0, abs=0.001)

    def test_zero_peers(self):
        assert _coverage(0, 3) == pytest.approx(0.0)


class TestClassifyRegime:
    def test_bullish(self):
        result = _classify_regime(
            sector_vs_ihsg_20d=0.02,
            sector_breadth=0.70,
            bullish_sector_vs_ihsg_min=0.01,
            bullish_breadth_min=0.55,
            bearish_sector_vs_ihsg_max=-0.01,
            bearish_breadth_max=0.45,
        )
        assert result == "BULLISH"

    def test_bearish(self):
        result = _classify_regime(
            sector_vs_ihsg_20d=-0.02,
            sector_breadth=0.30,
            bullish_sector_vs_ihsg_min=0.01,
            bullish_breadth_min=0.55,
            bearish_sector_vs_ihsg_max=-0.01,
            bearish_breadth_max=0.45,
        )
        assert result == "BEARISH"

    def test_neutral_mixed_signals(self):
        result = _classify_regime(
            sector_vs_ihsg_20d=0.02,   # sector outperforms
            sector_breadth=0.40,       # but breadth is weak
            bullish_sector_vs_ihsg_min=0.01,
            bullish_breadth_min=0.55,
            bearish_sector_vs_ihsg_max=-0.01,
            bearish_breadth_max=0.45,
        )
        assert result == "NEUTRAL"

    def test_unknown_when_ihsg_unavailable_and_no_breadth(self):
        result = _classify_regime(
            sector_vs_ihsg_20d=None,
            sector_breadth=None,
            bullish_sector_vs_ihsg_min=0.01,
            bullish_breadth_min=0.55,
            bearish_sector_vs_ihsg_max=-0.01,
            bearish_breadth_max=0.45,
        )
        assert result == "UNKNOWN"

    def test_neutral_when_ihsg_unavailable(self):
        result = _classify_regime(
            sector_vs_ihsg_20d=None,
            sector_breadth=0.70,
            bullish_sector_vs_ihsg_min=0.01,
            bullish_breadth_min=0.55,
            bearish_sector_vs_ihsg_max=-0.01,
            bearish_breadth_max=0.45,
        )
        assert result == "NEUTRAL"


# --------------------------------------------------------------------------- #
# SectorContextEvidenceBuilder tests
# --------------------------------------------------------------------------- #

class TestSectorContextEvidenceBuilderBuild:
    def _make_builder(
        self,
        sector_index: dict | None = None,
    ) -> SectorContextEvidenceBuilder:
        return SectorContextEvidenceBuilder(
            config=_default_config(),
            sector_universe_index=sector_index or {
                "bank": ("BBCA", "BBRI", "BBNI", "BMRI", "BDMN"),
            },
        )

    def _make_request(
        self,
        ticker: str = "BBCA",
        sector: str | None = "Finance",
        peer_closes: dict[str, list[float]] | None = None,
        ticker_closes: list[float] | None = None,
        ihsg_20d_return: float | None = 0.015,
    ) -> SectorContextRequest:
        if ticker_closes is None:
            ticker_closes = [100.0] * 10 + [108.0]
        if peer_closes is None:
            peer_closes = {
                "BBRI": [100.0] * 10 + [103.0],
                "BBNI": [100.0] * 10 + [102.0],
                "BMRI": [100.0] * 10 + [105.0],
                "BDMN": [100.0] * 10 + [101.0],
            }
        return SectorContextRequest(
            ticker=ticker,
            snapshot_date=date(2026, 7, 6),
            sector=sector,
            ticker_candles=tuple(_make_candles(ticker, ticker_closes)),
            peer_candles={
                peer: _make_candles(peer, closes)
                for peer, closes in peer_closes.items()
            },
            ihsg_20d_return=ihsg_20d_return,
        )

    def test_basic_build_produces_valid_evidence(self):
        builder = self._make_builder()
        request = self._make_request()
        ev = builder.build(request)

        assert isinstance(ev, SectorContextEvidence)
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC
        assert ev.peer_count == 4
        assert ev.sector_20d_return is not None
        assert ev.sector_breadth is not None
        assert ev.coverage_score == pytest.approx(1.0)
        assert ev.sector_regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN")

    def test_sector_vs_ihsg_computed_correctly(self):
        builder = self._make_builder()
        request = self._make_request(ihsg_20d_return=0.010)
        ev = builder.build(request)

        # All peers return ~2-5% so sector_20d_return ~3%
        # ihsg_20d_return = 1%, so sector_vs_ihsg ~2%
        assert ev.sector_vs_ihsg_20d is not None
        assert ev.sector_vs_ihsg_20d > 0  # sector outperforms

    def test_ticker_vs_sector_rs_computed(self):
        builder = self._make_builder()
        # Ticker returns 8%, peers return ~2-5%
        request = self._make_request(
            ticker_closes=[100.0] * 10 + [108.0],
            peer_closes={
                "BBRI": [100.0] * 10 + [103.0],
                "BBNI": [100.0] * 10 + [102.0],
                "BMRI": [100.0] * 10 + [102.0],
                "BDMN": [100.0] * 10 + [101.0],
            },
        )
        ev = builder.build(request)
        # Ticker 8% return, sector avg ~2%, so RS > 0
        assert ev.ticker_vs_sector_rs is not None
        assert ev.ticker_vs_sector_rs > 0.0

    def test_no_ihsg_return_leaves_sector_vs_ihsg_none(self):
        builder = self._make_builder()
        request = self._make_request(ihsg_20d_return=None)
        ev = builder.build(request)
        assert ev.sector_vs_ihsg_20d is None
        assert "sector_vs_ihsg:ihsg_return_unavailable" in ev.unavailable_reasons

    def test_no_peer_candles_returns_zero_coverage(self):
        builder = self._make_builder()
        request = SectorContextRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 7, 6),
            sector="Finance",
            ticker_candles=tuple(_make_candles("BBCA", [100.0] * 10 + [108.0])),
            peer_candles={},
            ihsg_20d_return=0.01,
        )
        ev = builder.build(request)
        assert ev.coverage_score == 0.0
        assert ev.sector_20d_return is None
        assert "sector_peers:no_valid_candles" in ev.unavailable_reasons

    def test_insufficient_peer_candles_lowers_coverage(self):
        builder = self._make_builder()
        # Only 1 peer with enough candles (min_peer_count=3)
        request = self._make_request(
            peer_closes={
                "BBRI": [100.0] * 10 + [103.0],  # valid
            }
        )
        ev = builder.build(request)
        assert ev.peer_count == 1
        assert ev.coverage_score == pytest.approx(1.0 / 3.0, abs=0.01)

    def test_peers_with_too_few_candles_excluded(self):
        builder = self._make_builder()
        request = self._make_request(
            peer_closes={
                "BBRI": [100.0, 103.0],   # only 2 candles, below min_valid=5
                "BBNI": [100.0] * 10 + [105.0],  # valid
                "BMRI": [100.0] * 10 + [104.0],  # valid
                "BDMN": [100.0] * 10 + [103.0],  # valid
            }
        )
        ev = builder.build(request)
        assert "BBRI" not in ev.peer_tickers
        assert ev.peer_count == 3

    def test_evidence_status_always_diagnostic(self):
        builder = self._make_builder()
        ev = builder.build(self._make_request())
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC

    def test_builder_never_raises_on_bad_input(self):
        builder = self._make_builder()
        # Pass completely empty candles
        request = SectorContextRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 7, 6),
            sector="Finance",
            ticker_candles=(),
            peer_candles={},
            ihsg_20d_return=None,
        )
        ev = builder.build(request)
        # Should degrade gracefully, not raise
        assert isinstance(ev, SectorContextEvidence)
        assert ev.coverage_score == 0.0

    def test_sector_regime_bullish_when_sector_outperforms(self):
        builder = self._make_builder()
        # Peers return 5%, IHSG returns 1% → sector_vs_ihsg ≈ 4% > threshold 1%
        # All peers positive → breadth = 1.0 > threshold 0.55
        request = self._make_request(
            peer_closes={
                "BBRI": [100.0] * 10 + [105.0],
                "BBNI": [100.0] * 10 + [105.0],
                "BMRI": [100.0] * 10 + [105.0],
                "BDMN": [100.0] * 10 + [105.0],
            },
            ihsg_20d_return=0.01,
        )
        ev = builder.build(request)
        assert ev.sector_regime == "BULLISH"

    def test_sector_regime_bearish_when_sector_underperforms(self):
        builder = self._make_builder()
        # Peers decline 3%, IHSG rises 1% → sector_vs_ihsg ≈ -4% < -1% threshold
        # All peers negative → breadth = 0.0 < 0.45
        request = self._make_request(
            peer_closes={
                "BBRI": [100.0] * 10 + [97.0],
                "BBNI": [100.0] * 10 + [97.0],
                "BMRI": [100.0] * 10 + [97.0],
                "BDMN": [100.0] * 10 + [97.0],
            },
            ihsg_20d_return=0.01,
        )
        ev = builder.build(request)
        assert ev.sector_regime == "BEARISH"


class TestSectorContextEvidenceBuilderIndex:
    def test_peers_for_ticker_excludes_self(self):
        builder = SectorContextEvidenceBuilder(
            config=_default_config(),
            sector_universe_index={
                "bank": ("BBCA", "BBRI", "BBNI", "BMRI"),
            },
        )
        peers = builder.peers_for_ticker("BBCA")
        assert "BBCA" not in peers
        assert "BBRI" in peers

    def test_peers_for_ticker_unknown_ticker(self):
        builder = SectorContextEvidenceBuilder(
            config=_default_config(),
            sector_universe_index={"bank": ("BBCA", "BBRI")},
        )
        peers = builder.peers_for_ticker("UNKNOWN")
        assert peers == ()

    def test_peers_capped_at_max(self):
        big_group = tuple(f"TICK{i:02d}" for i in range(30))
        builder = SectorContextEvidenceBuilder(
            config=_default_config(),
            sector_universe_index={"big": big_group},
        )
        peers = builder.peers_for_ticker("TICK00")
        assert len(peers) <= 20  # max_peer_count

    def test_sector_group_for_ticker(self):
        builder = SectorContextEvidenceBuilder(
            config=_default_config(),
            sector_universe_index={"bank": ("BBCA", "BBRI")},
        )
        assert builder.sector_group_for_ticker("BBCA") == "bank"
        assert builder.sector_group_for_ticker("TLKM") is None

    def test_from_yaml_does_not_raise(self):
        # Smoke test — just ensure the factory doesn't crash with real config files.
        builder = SectorContextEvidenceBuilder.from_yaml()
        assert isinstance(builder, SectorContextEvidenceBuilder)
