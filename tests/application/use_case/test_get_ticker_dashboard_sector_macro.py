"""Sector-macro on GetTickerDashboardUseCase — real assembly path, local fixtures."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
from src.application.ports.ticker_dashboard_source import TickerDashboardSource
from src.application.services.candidate_evidence_data_loader import (
    CandidateEvidenceDataLoader,
)
from src.application.services.sector_macro_context_evidence_builder import (
    SectorMacroContextConfig,
    SectorMacroContextEvidenceBuilder,
)
from src.application.services.ticker_dashboard_layout import panel_keys_for_mode
from src.application.services.ticker_dashboard_sector_macro_loader import (
    TickerDashboardSectorMacroLoader,
)
from src.application.use_case.get_ticker_dashboard_use_case import GetTickerDashboardUseCase
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.policy_rate_step import (
    PolicyRateDirection,
    PolicyRateStep,
)
from src.domain.value_objects.sector_macro_context_evidence import (
    SectorMacroContextEvidence,
)
from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
    SQLiteMacroCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


class _EmptySource(TickerDashboardSource):
    """Minimal source — all panels empty; sector-macro uses separate loader."""

    def get_notation(self, ticker: str):
        return None

    def get_fundamentals(self, ticker: str):
        return None

    def get_analyst(self, ticker: str):
        return None

    def get_ownership(self, ticker: str):
        return None

    def get_bandar(self, ticker: str, session_date: date):
        return None

    def get_forward_estimates(self, ticker: str):
        return None

    def get_profile(self, ticker: str):
        return None

    def get_candles(self, ticker: str, start_date: date, end_date: date):
        return []

    def get_ticker_corp_actions(self, ticker: str, from_date: date, to_date: date):
        return []

    def get_calendar_corp_actions(self, ticker: str, from_date: date, to_date: date):
        return []

    def is_ticker_corp_cache_fresh(self, ticker: str) -> bool:
        return False

    def get_insider_transactions(
        self, ticker: str, from_date: date, to_date: date, action_type: str = "ALL"
    ):
        return []

    def get_seasonality(self, ticker: str, year: int, month: int):
        return None

    def get_foreign_flow_points(self, ticker: str, source: str):
        return []

    def get_earnings_history(self, ticker: str, quarters: int):
        return []

    def get_iev_history(self, ticker: str, limit: int):
        return []

    def get_sentiment_logs(self, ticker: str, limit: int):
        return []


def _bank_config() -> SectorMacroContextConfig:
    return SectorMacroContextConfig.from_mapping(
        {
            "sector_macro_context": {
                "evidence_status": "DIAGNOSTIC",
                "lookback_sessions": 10,
                "min_valid_sessions": 5,
                "min_coverage_to_label": 0.5,
                "score_labels": {"favorable_min": 0.65, "neutral_min": 0.35},
                "regime_thresholds": {"supportive_min": 0.65, "headwind_max": 0.35},
                "factor_library": {
                    "bi_rate_policy": {
                        "series": "BI_RATE",
                        "kind": "policy_rate_steps",
                        "invert": True,
                        "lookback_days": 180,
                        "thresholds": {"supportive_min": 1.0, "headwind_max": -1.0},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "kind": "return_sessions",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "bank": {
                        "factors": [
                            {"ref": "bi_rate_policy", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    }
                },
            }
        }
    )


class _FakeScBuilder:
    def __init__(self, memberships: tuple[str, ...]) -> None:
        self._memberships = memberships

    def sector_groups_for_ticker(self, ticker: str) -> tuple[str, ...]:
        return self._memberships


class _FakeMarketRepo:
    def __init__(self, candles: dict[str, list[Candle]]) -> None:
        self._candles = candles

    def get_candles(self, ticker: str, end_date=None, **kwargs):
        return list(self._candles.get(ticker.upper(), []))


class _FakeBrokerRepo:
    pass


def _candle(ticker: str, d: date, close: float) -> Candle:
    return Candle(
        ticker=ticker,
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1000,
    )


def test_panel_keys_full_includes_sector_macro_brief_omits():
    full = panel_keys_for_mode(brief=False)
    brief = panel_keys_for_mode(brief=True)
    assert "sector_macro" in full
    assert "sector_macro" not in brief


def test_dashboard_full_loads_sector_macro_via_injected_loader():
    """Mapped success: loader returns SUPPORTIVE evidence; appears on DTO."""
    cut = PolicyRateStep(
        event_date=date(2026, 6, 15),
        title="Interest Rate Decision",
        direction=PolicyRateDirection.CUT,
        actual="5.25%",
        previous="5.50%",
    )
    as_of = date(2026, 7, 1)
    idr = [_candle("IDR=X", as_of - timedelta(days=i), 16000.0) for i in range(20)]

    smc_builder = SectorMacroContextEvidenceBuilder(_bank_config())

    def loader(ticker: str, snapshot: date) -> SectorMacroContextEvidence | None:
        from src.application.services.candidate_evidence_data_loader import (
            SectorMacroContextInputs,
        )
        from src.application.services.candidate_sector_macro_context_evidence_assembler import (
            CandidateSectorMacroContextEvidenceAssembler,
        )

        return CandidateSectorMacroContextEvidenceAssembler().assemble(
            builder=smc_builder,
            ticker=ticker,
            snapshot_date=snapshot,
            sector_group="bank",
            inputs=SectorMacroContextInputs(
                series_candles={"IDR=X": tuple(reversed(idr))},
                policy_steps={"BI_RATE": (cut,)},
            ),
        )

    uc = GetTickerDashboardUseCase(_EmptySource(), sector_macro_context_loader=loader)
    dash = uc.execute(
        GetTickerDashboardRequest(ticker="BBCA", brief=False, today=date(2026, 7, 24))
    )
    assert "sector_macro" in dash.panel_keys
    assert dash.sector_macro_context_evidence is not None
    assert dash.sector_macro_context_evidence.evidence_status == EvidenceStatus.DIAGNOSTIC
    assert dash.sector_macro_context_evidence.sector_group == "bank"
    bi = next(f for f in dash.sector_macro_context_evidence.factors if f.name == "bi_rate_policy")
    assert bi.label == "FAVORABLE"
    assert bi.score == 1.0
    # related action points to judgment, not Action invented on view
    cmds = [a.command for a in dash.related_actions]
    assert any("screen accum BBCA" in c for c in cmds)


def test_dashboard_brief_skips_sector_macro_loader():
    called: list[tuple] = []

    def loader(ticker: str, snapshot: date):
        called.append((ticker, snapshot))
        return None

    uc = GetTickerDashboardUseCase(_EmptySource(), sector_macro_context_loader=loader)
    dash = uc.execute(GetTickerDashboardRequest(ticker="BBCA", brief=True, today=date(2026, 7, 24)))
    assert "sector_macro" not in dash.panel_keys
    assert dash.sector_macro_context_evidence is None
    assert called == []


def test_dashboard_loader_exception_is_panel_error_not_abort():
    def boom(ticker: str, snapshot: date):
        raise RuntimeError("macro boom")

    uc = GetTickerDashboardUseCase(_EmptySource(), sector_macro_context_loader=boom)
    dash = uc.execute(
        GetTickerDashboardRequest(ticker="BBCA", brief=False, today=date(2026, 7, 24))
    )
    assert dash.sector_macro_context_evidence is None
    assert any(e.key == "sector_macro" for e in dash.panel_errors)
    # rest of dashboard still assembled
    assert dash.ticker == "BBCA"
    assert "identity" in dash.panel_keys


def test_dashboard_unmapped_group_fail_soft_via_real_loader(tmp_path: Path):
    """Real TickerDashboardSectorMacroLoader + empty market/macro → soft result."""
    db = tmp_path / "v.db"
    market = SQLiteMarketRepository(db_path=db)
    macro = SQLiteMacroCalendarRepository(db)
    data_loader = CandidateEvidenceDataLoader(
        market, _FakeBrokerRepo(), macro_calendar_repository=macro
    )

    def sc_factory():
        return _FakeScBuilder(("consumer_goods",))  # no sector_maps entry in bank-only cfg

    def smc_factory():
        return SectorMacroContextEvidenceBuilder(_bank_config())

    loader = TickerDashboardSectorMacroLoader(
        data_loader=data_loader,
        sector_macro_context_builder_factory=smc_factory,
        sector_context_builder_factory=sc_factory,
    )
    uc = GetTickerDashboardUseCase(_EmptySource(), sector_macro_context_loader=loader)
    dash = uc.execute(
        GetTickerDashboardRequest(ticker="XXXX", brief=False, today=date(2026, 7, 24))
    )
    # Unmapped group → fail-soft evidence (not exception / not panel_error)
    assert dash.ticker == "XXXX"
    assert not any(e.key == "sector_macro" for e in dash.panel_errors)
    smc = dash.sector_macro_context_evidence
    assert smc is not None, "builder returns unavailable VO for missing sector_map"
    assert smc.macro_regime == "UNKNOWN"
    assert smc.evidence_status == EvidenceStatus.DIAGNOSTIC
    assert smc.factors == ()
    assert any("sector_map:missing" in r for r in smc.unavailable_reasons)
