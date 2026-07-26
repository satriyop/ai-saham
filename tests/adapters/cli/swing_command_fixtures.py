"""Shared fixtures and mock repositories for swing CLI command tests."""

from datetime import date
from decimal import Decimal

from typer.testing import CliRunner

from src.adapters.cli.analyze_swing_commands import FOREIGN_BOUNCE_SETUP_NAME
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.swing_backtest_attribution import (
    AttributionGroupStat,
    SampleQuality,
    SwingBacktestAttributionSummary,
)
from src.application.services.swing_broker_detail_builder import (
    build_broker_detail as _build_broker_detail_base,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType

_COMPLETE_SOURCE_REVIEW = {
    "readiness_state": "PATCH_ELIGIBLE",
    "walk_forward_enforced": True,
    "is_ratio": 0.70,
    "is_end_date": "2026-04-01",
    "oos_start_date": "2026-04-02",
    "full_end_date": "2026-07-01",
    "sample": {"status": "TRADE_READY", "min_sample_size": 30},
    "backtest_summary": {"trade_count": 60},
    "oos_backtest_summary": {
        "trade_count": 30,
        "total_return_pct": 3.2,
        "average_return_pct": 0.2,
        "win_rate_pct": 50.0,
        "profit_factor": 1.5,
        "drawdown_regression_pct": 0.0,
    },
    "attribution": {
        "market_regime": {
            "buckets": [
                {"key": "RISK_ON", "oos_trade_count": 15, "oos_profit": 1.0},
                {"key": "NEUTRAL", "oos_trade_count": 15, "oos_profit": 0.8},
            ],
        },
        "signal_authority_coverage_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
        "setup_readiness_status": {"buckets": [{"key": "READY", "observation_count": 30}]},
    },
}

runner = CliRunner()


def _build_broker_detail(*args, **kwargs):
    from src.adapters.cli.analyze_swing_command_config import load_analyze_swing_command_config
    cfg = load_analyze_swing_command_config()
    smart_money_brokers = set(cfg.swing_config.smart_money_brokers)
    noise_brokers = set(cfg.swing_config.noise_brokers)
    broker_weights = {
        **{code: cfg.swing_config.smart_weight for code in smart_money_brokers},
        **{code: cfg.swing_config.noise_weight for code in noise_brokers},
    }
    return _build_broker_detail_base(
        *args,
        **kwargs,
        smart_money_brokers=smart_money_brokers,
        noise_brokers=noise_brokers,
        broker_weights=broker_weights,
        smart_share_threshold_pct=cfg.swing_config.smart_share_threshold_pct,
    )



class FakeBrokerSummaryRepository:
    def __init__(self, summaries):
        self._summaries = summaries

    def get_broker_summaries(self, ticker: str, start_date=None, end_date=None):
        return [
            summary
            for summary in self._summaries
            if summary.ticker == ticker
            and (start_date is None or summary.date >= start_date)
            and (end_date is None or summary.date <= end_date)
        ]


def _tx(
    code: str,
    name: str,
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=name,
        broker_type=broker_type,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _summary(
    day: date,
    buy: str,
    sell: str,
    total: str = "1000000000",
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
    source: str = "stockbit",
) -> BrokerSummary:
    net_value = Decimal(buy) - Decimal(sell)
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal(buy),
        foreign_sell_value=Decimal(sell),
        foreign_buy_lot=max(int(net_value), 0),
        foreign_sell_lot=max(-int(net_value), 0),
        total_value=Decimal(total),
        total_lot=1000,
        source=source,
    )


def _candidate(**overrides) -> AccumulationCandidate:
    if "score" in overrides:
        overrides["accum_score"] = overrides.pop("score")
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "accum_score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def _trade_ready_backtest_response() -> SwingBacktestResponse:
    return SwingBacktestResponse(
        setup=FOREIGN_BOUNCE_SETUP_NAME,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        initial_capital=Decimal("1000000"),
        cost_bps=Decimal("20"),
        final_equity=Decimal("1010000"),
        total_return_pct=1.0,
        max_drawdown_pct=-1.0,
        trade_count=60,
        win_rate_pct=50.0,
        avg_trade_return_pct=1.0,
        profit_factor=1.5,
        exposure_pct=25.0,
        skipped_no_cash=0,
        skipped_duplicate=0,
        skipped_no_forward_data=0,
        skipped_by_regime=0,
        attribution_summary=SwingBacktestAttributionSummary(
            sample_quality=SampleQuality(
                status="TRADE_READY",
                completed_trade_count=60,
                candidate_observation_count=0,
                min_sample_size=30,
                trade_sample_ready=True,
                candidate_sample_ready=False,
                notes=(),
            ),
            group_stats=(
                AttributionGroupStat(
                    dimension="signal_strength",
                    bucket="STRONG",
                    trade_count=30,
                    win_rate_pct=20.0,
                    avg_return_pct=-2.0,
                    total_pnl=Decimal("-6000"),
                    profit_factor=0.5,
                ),
                AttributionGroupStat(
                    dimension="signal_strength",
                    bucket="WEAK",
                    trade_count=30,
                    win_rate_pct=80.0,
                    avg_return_pct=5.0,
                    total_pnl=Decimal("15000"),
                    profit_factor=2.0,
                ),
            ),
        ),
    )


def _patch_swing_backtest_command(monkeypatch):
    from unittest.mock import MagicMock

    from src.adapters.cli import trade_swing_backtest_runner
    from src.adapters.composition.stock_analysis_workflow_dependencies import (
        StockAnalysisWorkflowDependencies,
    )

    class FakeSwingBacktestUseCase:
        def __init__(self, *args, **kwargs):
            pass

        def execute(self, request):
            return _trade_ready_backtest_response()

    fake_deps = MagicMock(spec=StockAnalysisWorkflowDependencies)
    fake_deps.broker_repository = object()
    fake_deps.market_repository = object()
    fake_deps.indicator_registry_factory = lambda *args, **kwargs: object()
    fake_deps.rules_loader_factory = lambda: object()
    fake_deps.create_signal_engine = lambda: object()
    fake_deps.create_risk_engine = lambda: object()
    fake_deps.create_market_context_provider = lambda: object()

    monkeypatch.setattr(
        trade_swing_backtest_runner,
        "resolve_tickers",
        lambda universe, explicit, db_path, **kwargs: tuple(explicit) or ("BBCA",),
    )
    monkeypatch.setattr(
        trade_swing_backtest_runner,
        "create_stock_analysis_workflow_dependencies",
        lambda db_path: fake_deps,
    )
    monkeypatch.setattr(
        trade_swing_backtest_runner,
        "SwingBacktestUseCase",
        FakeSwingBacktestUseCase,
    )
