"""
Persistence integration tests for ia_* and sc_* fingerprint fields.

Verifies that AccumulationScreenUseCase.execute() persists both sets of
diagnostic evidence into the saved CandidateObservation payload.

The distinction under test:
  - A field being None because evidence was genuinely unavailable (e.g. no
    ForeignFlowPoints) is acceptable and expected.
  - A field being None because the builder was never called, or the fingerprint
    helper was never invoked, is the bug we are guarding against.

Acceptance:
  1. ia_cnfb_divergence_20d is not None when broker repo returns plausible
     CNFB-style ForeignFlowPoints.
  2. sc_sector and sc_peer_count are not None when market repo returns peer
     candles for same-sector tickers.
  3. All ia_* and sc_* keys are present (possibly None) when inputs are
     genuinely unavailable — a missing key signals a wiring gap, not an
     acceptable null.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.domain.entities.broker_flow import BrokerSummary, ForeignFlowPoint
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.ticker_notation_provider import TickerNotationProvider
from src.domain.value_objects.ticker_notation import TickerNotationSnapshot

# --------------------------------------------------------------------------- #
# Stubs
# --------------------------------------------------------------------------- #

class _MockMarketRepo(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        return False

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class _MockBrokerRepo(BrokerDataRepository):
    """Stub that returns pre-loaded summaries and ForeignFlowPoints."""

    def __init__(
        self,
        summaries: list[BrokerSummary],
        flow_points: list[ForeignFlowPoint] | None = None,
    ) -> None:
        self._summaries = summaries
        self._flow_points = flow_points or []

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        pass

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        pass

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[BrokerSummary]:
        rows = [s for s in self._summaries if s.ticker == ticker.upper()]
        if start_date is not None:
            rows = [s for s in rows if s.date >= start_date]
        if end_date is not None:
            rows = [s for s in rows if s.date <= end_date]
        return sorted(rows, key=lambda s: s.date)

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        source: str | None = None,
    ) -> bool:
        return False

    def get_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date

    def get_foreign_flow_points(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[ForeignFlowPoint]:
        rows = [p for p in self._flow_points if p.ticker == ticker.upper()]
        if start_date is not None:
            rows = [p for p in rows if p.date >= start_date]
        if end_date is not None:
            rows = [p for p in rows if p.date <= end_date]
        return sorted(rows, key=lambda p: p.date)

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        broker_codes: list[str] | None = None,
        source: str | None = None,
    ) -> list:
        return []


class _CapturingObservationsRepo:
    """Captures whatever save_many() receives so tests can assert on it."""

    def __init__(self) -> None:
        self.saved: list[CandidateObservation] = []

    def save_many(self, observations: list[CandidateObservation]) -> None:
        self.saved.extend(observations)

    def get_latest(self, ticker: str, snapshot_date: date) -> CandidateObservation | None:
        return None

    def get_at(self, ticker: str, snapshot_date: date, captured_at) -> CandidateObservation | None:
        return None

    def list_recent(self, ticker: str, *, before_date: date | None = None, limit: int = 20):
        return []

    def list_by_date(self, snapshot_date: date):
        return []

    def list_all_by_date(self, snapshot_date: date):
        return []

    def list_snapshot_dates(self):
        return []


class _MockTickerNotationProvider(TickerNotationProvider):
    def __init__(self, sector: str) -> None:
        self._sector = sector

    def get_notation(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> TickerNotationSnapshot | None:
        return TickerNotationSnapshot(ticker=ticker, sector=self._sector)


# --------------------------------------------------------------------------- #
# Shared factories
# --------------------------------------------------------------------------- #

def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _candle(ticker: str, day: date, close: float) -> Candle:
    price = Decimal(str(round(close, 2)))
    return Candle(
        ticker=ticker,
        date=day,
        open=price,
        high=Decimal(str(round(close * 1.005, 2))),
        low=Decimal(str(round(close * 0.995, 2))),
        close=price,
        volume=1_000_000,
    )


def _summary(ticker: str, day: date) -> BrokerSummary:
    buy_val = Decimal("5_000_000_000")
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=buy_val,
        foreign_sell_value=Decimal("1_000_000_000"),
        foreign_buy_lot=50_000,
        foreign_sell_lot=10_000,
        total_value=buy_val * Decimal("3"),
        total_lot=200_000,
    )


def _flow_point(ticker: str, day: date, net_val: float) -> ForeignFlowPoint:
    return ForeignFlowPoint(
        ticker=ticker,
        date=day,
        net_val=Decimal(str(int(net_val))),
        net_lot=max(1, int(net_val / 1_000_000)),
        avg_price=Decimal("1000"),
    )


# --------------------------------------------------------------------------- #
# Complete list of expected ia_* and sc_* fingerprint keys from
# _ia_evidence_fingerprint() and _sc_fingerprint() in the use case.
# --------------------------------------------------------------------------- #

_IA_KEYS = [
    "institutional_accumulation_status",
    "ia_foreign_participation",
    "ia_foreign_cr4",
    "ia_foreign_cr8",
    "ia_cnfb_divergence_20d",
    "ia_cnfb_divergence_30d",
    "ia_cnfb_distribution_3d",
    "ia_foreign_vwap_distance",
    "ia_foreign_track_coverage",
    "ia_foreign_track_conviction",
    "ia_domestic_broker_consistency",
    "ia_domestic_broker_reversal",
    "ia_domestic_accumulation_session_ratio",
    "ia_domestic_buy_vwap_distance",
    "ia_domestic_broker_hhi_divergence",
    "ia_bandar_broad_score_normalized",
    "ia_domestic_track_coverage",
    "ia_domestic_track_conviction",
    "ia_counterparty_transfer_asymmetry",
    "ia_counterparty_buy_hhi",
    "ia_counterparty_sell_hhi",
    "ia_coverage_score",
    "ia_conviction_score",
]

_SC_KEYS = [
    "sc_sector",
    "sc_peer_count",
    "sc_sector_20d_return",
    "sc_sector_vs_ihsg_20d",
    "sc_sector_breadth",
    "sc_ticker_vs_sector_rs",
    "sc_sector_regime",
    "sc_coverage_score",
]

# Complete list of expected cq_* fingerprint keys from _cq_fingerprint() —
# the DIAGNOSTIC company_quality_context producer. Every key must be present
# in the saved payload even when the underlying data is unavailable (None):
# distinguish "key absent = wiring bug" from "key present, None = data missing".
_CQ_KEYS = [
    "cq_valuation_score",
    "cq_earnings_trend_score",
    "cq_analyst_score",
    "cq_insider_score",
    "cq_seasonality_score",
    "cq_aggregate_score",
    "cq_coverage_score",
    "cq_present_axis_count",
]


# --------------------------------------------------------------------------- #
# Test 1 — ia_cnfb_divergence_20d is not None with plausible CNFB data
# --------------------------------------------------------------------------- #

class TestIaCnfbDivergenceWithPlausibleFlowData:
    """
    Guards the wiring path:
      broker_repo.get_foreign_flow_points()
        → InstitutionalAccumulationEvidenceBuilder.build()
          → metadata["cnfb_bullish_scores"]["cnfb_20d"]
            → _ia_evidence_fingerprint()["ia_cnfb_divergence_20d"]
              → payload["sub_signal_fingerprint"]["ia_cnfb_divergence_20d"]
    """

    def _run(self) -> dict:
        # 30 weekday sessions ending 2026-06-30.
        session_days = _weekdays(date(2026, 5, 22), 30)
        snapshot_date = session_days[-1]

        # Price gently declines (bearish price slope).
        candles = [
            _candle("BBCA", d, 9500.0 - i * 5.0)
            for i, d in enumerate(session_days)
        ]
        # Broker summaries — only need the last 7 to pass the screen filter.
        summaries = [_summary("BBCA", d) for d in session_days[-7:]]
        # ForeignFlowPoints with monotonically increasing cumulative net (bullish CNFB).
        # Each point adds a positive net_val so running sum always rises — slope > 0.
        daily_net = 1_000_000_000.0
        flow_points = [
            _flow_point("BBCA", d, daily_net * (i + 1))
            for i, d in enumerate(session_days)
        ]

        obs_repo = _CapturingObservationsRepo()
        uc = AccumulationScreenUseCase(
            broker_repository=_MockBrokerRepo(summaries, flow_points),
            market_repository=_MockMarketRepo(candles),
            candidate_observations_repository=obs_repo,
        )
        uc.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                as_of_date=snapshot_date,
                min_foreign_flow_score=0.0,
                min_net_buy_days=1,
                resistance_gate_enabled=False,
            )
        )
        assert obs_repo.saved, (
            "No observations saved — candidate was skipped before persistence. "
            "Check that the broker summaries satisfy _is_usable_broker_summary()."
        )
        return obs_repo.saved[0].payload["sub_signal_fingerprint"]

    def test_ia_cnfb_divergence_20d_key_is_present(self):
        fp = self._run()
        assert "ia_cnfb_divergence_20d" in fp, (
            "ia_cnfb_divergence_20d key missing from sub_signal_fingerprint — "
            "_ia_evidence_fingerprint() was not called or its result was not spread."
        )

    def test_ia_cnfb_divergence_20d_is_not_none(self):
        fp = self._run()
        assert fp["ia_cnfb_divergence_20d"] is not None, (
            "ia_cnfb_divergence_20d is None despite 30 ForeignFlowPoints with "
            "monotonically increasing CNFB. The builder likely did not receive "
            "flow_points — check that MockBrokerRepo.get_foreign_flow_points() "
            "is wired and that the date range in the use case includes the test dates."
        )

    def test_all_ia_keys_present_when_data_is_available(self):
        fp = self._run()
        missing = [k for k in _IA_KEYS if k not in fp]
        assert not missing, f"ia_* keys missing from fingerprint: {missing}"


# --------------------------------------------------------------------------- #
# Test 2 — sc_sector and sc_peer_count are not None with peer candles
# --------------------------------------------------------------------------- #

class TestScFingerprintWithPeerCandles:
    """
    Guards the wiring path:
      market_repo.get_candles(peer)
        → SectorContextEvidenceBuilder.build()
          → SectorContextEvidence.peer_count / sector
            → _sc_fingerprint()["sc_peer_count"] / ["sc_sector"]
              → payload["sub_signal_fingerprint"]["sc_peer_count"]

    BBCA is in the "bank" universe group in config/universes.yaml.
    The builder reads universes.yaml via from_yaml() to discover peers.
    We provide candles for 3 bank peers so the builder can compute sector metrics.
    """

    def _run(self) -> dict:
        session_days = _weekdays(date(2026, 5, 22), 25)
        snapshot_date = session_days[-1]

        all_candles: list[Candle] = []
        # Main ticker and peers (known bank-group members from universes.yaml).
        for ticker, base_price in [
            ("BBCA", 9000.0),
            ("BBNI", 5000.0),
            ("BBRI", 5500.0),
            ("BMRI", 6500.0),
            ("IHSG", 7200.0),   # benchmark for sector_vs_ihsg computation
        ]:
            for i, d in enumerate(session_days):
                all_candles.append(_candle(ticker, d, base_price + i * 10.0))

        summaries = [_summary("BBCA", d) for d in session_days[-7:]]

        obs_repo = _CapturingObservationsRepo()
        uc = AccumulationScreenUseCase(
            broker_repository=_MockBrokerRepo(summaries),
            market_repository=_MockMarketRepo(all_candles),
            candidate_observations_repository=obs_repo,
            # Provides sector="Finance" so sc_sector flows into SectorContextRequest.
            ticker_notation_provider=_MockTickerNotationProvider("Finance"),
        )
        uc.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                as_of_date=snapshot_date,
                min_foreign_flow_score=0.0,
                min_net_buy_days=1,
                resistance_gate_enabled=False,
            )
        )
        assert obs_repo.saved, "No observations saved"
        return obs_repo.saved[0].payload["sub_signal_fingerprint"]

    def test_sc_peer_count_is_not_none_and_positive(self):
        fp = self._run()
        assert "sc_peer_count" in fp, (
            "sc_peer_count key missing — _sc_fingerprint() was not called or "
            "its dict was not spread into sub_signal_fingerprint."
        )
        assert fp["sc_peer_count"] is not None, (
            "sc_peer_count is None despite peer candles provided. "
            "SectorContextEvidenceBuilder may not have received peer candles."
        )
        assert fp["sc_peer_count"] > 0, (
            f"sc_peer_count={fp['sc_peer_count']} — builder received peer candles "
            "but computed 0 valid peers. Check min_valid_sessions_per_peer in "
            "config/sector_context.yaml vs the number of test candles (25 sessions)."
        )

    def test_sc_sector_is_not_none_when_ticker_notation_provides_sector(self):
        fp = self._run()
        assert "sc_sector" in fp, "sc_sector key missing from sub_signal_fingerprint"
        assert fp["sc_sector"] is not None, (
            "sc_sector is None despite ticker_notation_provider returning sector='Finance'. "
            "The sector value may not be flowing from candidate.ticker_notation.sector "
            "into _build_candidate_sector_context()."
        )

    def test_all_sc_keys_present_when_peer_data_is_available(self):
        fp = self._run()
        missing = [k for k in _SC_KEYS if k not in fp]
        assert not missing, f"sc_* keys missing from fingerprint: {missing}"

    def test_all_cq_keys_present_when_screening(self):
        fp = self._run()
        missing = [k for k in _CQ_KEYS if k not in fp]
        assert not missing, (
            f"cq_* keys missing from fingerprint: {missing}. "
            "If _cq_fingerprint() was never called or its dict not spread into "
            "sub_signal_fingerprint, these keys will be absent — a wiring gap."
        )


# --------------------------------------------------------------------------- #
# Test 3 — all ia_* and sc_* keys exist even when inputs are unavailable
# --------------------------------------------------------------------------- #

class TestFingerprintKeysExistWhenInputsUnavailable:
    """
    When inputs are genuinely unavailable (no ForeignFlowPoints, no peer candles),
    every ia_* and sc_* key must still be present in the fingerprint dict with
    an explicit None value — not absent.

    A missing key indicates a wiring gap: the fingerprint helper was never called
    or the spread (**ia_dict) was removed.
    """

    def _run_minimal_screen(self) -> dict:
        session_days = _weekdays(date(2026, 5, 22), 10)
        snapshot_date = session_days[-1]
        candles = [_candle("BBCA", d, 9000.0) for d in session_days]
        summaries = [_summary("BBCA", d) for d in session_days[-7:]]

        obs_repo = _CapturingObservationsRepo()
        uc = AccumulationScreenUseCase(
            # No ForeignFlowPoints (get_foreign_flow_points returns []).
            broker_repository=_MockBrokerRepo(summaries),
            # No peer candles and no IHSG candles (only BBCA).
            market_repository=_MockMarketRepo(candles),
            candidate_observations_repository=obs_repo,
            # No ticker_notation_provider — sc_sector will be None.
        )
        uc.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                as_of_date=snapshot_date,
                min_foreign_flow_score=0.0,
                min_net_buy_days=1,
                resistance_gate_enabled=False,
            )
        )
        assert obs_repo.saved, "No observations saved — cannot assert on fingerprint"
        return obs_repo.saved[0].payload["sub_signal_fingerprint"]

    def test_all_ia_keys_present_with_none_values(self):
        fp = self._run_minimal_screen()
        missing = [k for k in _IA_KEYS if k not in fp]
        assert not missing, (
            f"ia_* keys missing from fingerprint: {missing}. "
            "If _ia_evidence_fingerprint() was never called, these keys will be absent. "
            "This is a wiring gap, not an acceptable null."
        )

    def test_ia_cnfb_divergence_20d_is_none_not_absent_when_no_flow_points(self):
        fp = self._run_minimal_screen()
        assert "ia_cnfb_divergence_20d" in fp, (
            "ia_cnfb_divergence_20d key is absent — wiring gap detected. "
            "Expected the key to exist with a None value, not be missing entirely."
        )
        # The value should be None because no ForeignFlowPoints were available.
        assert fp["ia_cnfb_divergence_20d"] is None, (
            "ia_cnfb_divergence_20d should be None with no flow data, "
            f"but got {fp['ia_cnfb_divergence_20d']!r}."
        )

    def test_all_sc_keys_present_with_none_or_zero_values(self):
        fp = self._run_minimal_screen()
        missing = [k for k in _SC_KEYS if k not in fp]
        assert not missing, (
            f"sc_* keys missing from fingerprint: {missing}. "
            "If _sc_fingerprint() was never called, these keys will be absent."
        )

    def test_sc_sector_is_none_not_absent_when_no_ticker_notation(self):
        fp = self._run_minimal_screen()
        assert "sc_sector" in fp, (
            "sc_sector key is absent — wiring gap in _sc_fingerprint()."
        )
        assert fp["sc_sector"] is None, (
            "sc_sector should be None when no ticker_notation provides sector, "
            f"but got {fp['sc_sector']!r}."
        )

    def test_all_cq_keys_present_with_none_values(self):
        fp = self._run_minimal_screen()
        missing = [k for k in _CQ_KEYS if k not in fp]
        assert not missing, (
            f"cq_* keys missing from fingerprint: {missing}. "
            "If _cq_fingerprint() was never called, these keys will be absent."
        )

    def test_cq_aggregate_score_is_none_not_absent_when_no_enrichment(self):
        fp = self._run_minimal_screen()
        assert "cq_aggregate_score" in fp, (
            "cq_aggregate_score key is absent — wiring gap in _cq_fingerprint()."
        )
        # No forward-P/E, analyst, insider, or seasonality enrichment → no axes.
        assert fp["cq_aggregate_score"] is None, (
            "cq_aggregate_score should be None with no company-quality enrichment, "
            f"but got {fp['cq_aggregate_score']!r}."
        )
