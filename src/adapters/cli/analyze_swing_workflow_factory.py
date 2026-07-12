"""
Factory for the saham analyze swing workflow.

Layer: Adapter

This module owns CLI/infrastructure wiring so analyze_swing_commands.py can stay
focused on flag parsing, request construction, execution, and rendering.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.dto.swing_broker_detail import BrokerDetail
from src.application.dto.swing_config import SwingConfig
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.services.bootstrap import (
    create_indicator_registry,
    create_risk_engine,
    create_signal_engine,
)
from src.application.services.swing_broker_detail_builder import (
    build_broker_detail,
    build_broker_quality_note,
    build_flow_detail,
)
from src.application.services.swing_data_freshness import (
    build_swing_data_freshness,
)
from src.application.services.swing_data_refresh import refresh_swing_data
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.accumulation_screen_use_case import resolve_setup_targets
from src.application.use_case.assess_corporate_action_event_risk_use_case import (
    AssessCorporateActionEventRiskUseCase,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    SwingSetupCatalogConfig,
)
from src.application.use_case.fetch_sentiment_use_case import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.application.use_case.swing_analysis_workflow_use_case import SwingAnalysisWorkflowUseCase
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.value_objects.setup_evaluation import SetupEvaluation
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.analyze_swing_config import AnalyzeSwingConfig
from src.infrastructure.config.corporate_action_policy_config import (
    load_corporate_action_policy_config,
)
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory


def create_swing_analysis_workflow(
    *,
    db_path: Path,
    setup_name: str | None,
    swing_config: SwingConfig,
    analyze_config: AnalyzeSwingConfig,
    smart_money_brokers: set[str],
    noise_brokers: set[str],
    broker_weights: dict[str, Decimal],
) -> SwingAnalysisWorkflowUseCase:
    """Build the composite swing analysis workflow with CLI infrastructure."""
    market_repo = SQLiteMarketRepository(db_path=db_path)
    broker_repo = SQLiteBrokerRepository(db_path)
    candidate_observations_repo = SQLiteCandidateObservationsRepository(db_path)
    corporate_action_risk_use_case = AssessCorporateActionEventRiskUseCase(
        repository=SQLiteCorporateActionCalendarRepository(db_path),
        policy=load_corporate_action_policy_config(),
    )
    registry = create_indicator_registry(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )
    accumulation_config = load_accumulation_screener_config()

    def _build_accumulation_candidate(ticker: str, window: int):
        stockbit_providers = create_readonly_stockbit_providers(db_path)
        accum_uc = create_accumulation_screen_use_case(
            broker_repository=broker_repo,
            market_repository=market_repo,
            stockbit_providers=stockbit_providers,
            foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
            derived_feature_policy=accumulation_config.derived_features,
            ticker_profile_classifier_factory=create_ticker_profile_classifier,
        )
        accum_resp = accum_uc.execute(
            AccumulationScreenRequest(
                tickers=[ticker],
                window_days=window,
                min_net_buy_days=analyze_config.candidate_min_net_buy_days,
                min_foreign_flow_score=analyze_config.candidate_min_foreign_flow_score,
                min_foreign_flow_score_enabled=True,
                tier1_broker_codes=swing_config.tier1_broker_codes,
                bci_cluster_min_count=swing_config.bci_cluster_min_count,
                bci_stable_min_count=swing_config.bci_stable_min_count,
                resistance_gate_enabled=swing_config.resistance_gate_enabled,
                resistance_headroom_min_pct=swing_config.resistance_headroom_min_pct,
                ex_date_warning_days=swing_config.ex_date_warning_days,
            )
        )
        return accum_resp.candidates[0] if accum_resp.candidates else None

    def _build_broker_detail(ticker, broker_repo, window_sessions=5, as_of_date=None):
        return build_broker_detail(
            ticker=ticker,
            broker_repo=broker_repo,
            window_sessions=window_sessions,
            as_of_date=as_of_date,
            smart_money_brokers=smart_money_brokers,
            noise_brokers=noise_brokers,
            broker_weights=broker_weights,
            smart_share_threshold_pct=swing_config.smart_share_threshold_pct,
        )

    return SwingAnalysisWorkflowUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        registry=registry,
        refresh_data=lambda ticker, db_path, force_refresh: _auto_refresh_swing_data(
            ticker=ticker,
            db_path=db_path,
            force_refresh=force_refresh,
            analyze_config=analyze_config,
        ),
        build_data_freshness=build_swing_data_freshness,
        build_flow_detail=build_flow_detail,
        build_broker_detail=_build_broker_detail,
        build_accumulation_candidate=_build_accumulation_candidate,
        evaluate_setup=lambda candidate, broker_detail: _evaluate_swing_setup(
            setup_name=setup_name,
            candidate=candidate,
            broker_detail=broker_detail,
            config=_setup_config(swing_config),
        ),
        build_broker_quality_note=lambda broker_detail, setup_eval: build_broker_quality_note(
            broker_detail,
            setup_eval,
            smart_sell_min_share_pct=swing_config.smart_sell_min_share_pct,
        ),
        fetch_sentiment=lambda ticker, sentiment_verbose: _fetch_swing_sentiment(
            ticker=ticker,
            sentiment_verbose=sentiment_verbose,
            analyze_config=analyze_config,
        ),
        load_swing_config=lambda: swing_config,
        resolve_setup_targets=resolve_setup_targets,
        evaluate_market_context=evaluate_market_context,
        structural_gates=[FundamentalGate(), LiquidityGate(), FreeFloatGate()],
        execution_gates=[BandarGate()],
        signal_engine=create_signal_engine(db_path=db_path, with_enrichment=True),
        risk_engine=create_risk_engine(db_path=db_path, with_enrichment=True),
        candidate_observations_repository=candidate_observations_repo,
        foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
        corporate_action_risk_use_case=corporate_action_risk_use_case,
        ticker_profile_classifier_factory=create_ticker_profile_classifier,
    )


def _auto_refresh_swing_data(
    *,
    ticker: str,
    db_path: Path,
    force_refresh: bool,
    analyze_config: AnalyzeSwingConfig,
) -> tuple[str, ...]:
    from src.adapters.cli.fetch_market_broker_refresh import fetch_broker
    from src.adapters.cli.fetch_market_candle_refresh import fetch_candles
    from src.adapters.cli.fetch_market_provider_factory import create_broker_provider

    return refresh_swing_data(
        ticker=ticker,
        db_path=db_path,
        force_refresh=force_refresh,
        market_refresh_days=analyze_config.market_refresh_days,
        broker_refresh_days=analyze_config.broker_refresh_days,
        fetch_candles=fetch_candles,
        create_broker_provider=create_broker_provider,
        fetch_broker=fetch_broker,
    )


def _setup_config(swing_config: SwingConfig) -> SwingSetupCatalogConfig:
    return build_swing_setup_catalog_config(swing_config)


def _evaluate_swing_setup(
    *,
    setup_name: str | None,
    candidate: AccumulationCandidate | None,
    broker_detail: BrokerDetail | None = None,
    config: SwingSetupCatalogConfig,
) -> SetupEvaluation:
    """Evaluate audited setup fit for one accumulation candidate."""
    return EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=setup_name or "foreign-bounce",
            candidate=candidate,
            config=config,
            broker_detail=broker_detail,
        )
    )


@contextmanager
def _quiet_sentiment_fetch(enabled: bool):
    """Suppress optional sentiment provider noise in composite swing output."""
    if not enabled:
        with nullcontext():
            yield
        return

    previous_disable = logging.root.manager.disable
    sink = StringIO()
    try:
        logging.disable(logging.CRITICAL)
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous_disable)


def _fetch_swing_sentiment(
    *,
    ticker: str,
    sentiment_verbose: bool,
    analyze_config: AnalyzeSwingConfig,
):
    """Fetch optional sentiment context without leaking provider noise by default."""
    try:
        with _quiet_sentiment_fetch(enabled=not sentiment_verbose):
            news_provider = SentimentFactory.create_news_provider()
            classifier = SentimentFactory.create_classifier(use_ai=False)
            sent_uc = FetchSentimentUseCase(
                news_provider=news_provider,
                classifier=classifier,
            )
            response = sent_uc.execute(FetchSentimentRequest(
                ticker=ticker,
                max_headlines=analyze_config.sentiment_max_headlines,
                days=analyze_config.sentiment_days,
            ))
        return response, response.warning
    except Exception as exc:
        if sentiment_verbose:
            return None, f"Sentiment fetch failed: {exc}"
        return None, "News unavailable (provider fetch failed)."
