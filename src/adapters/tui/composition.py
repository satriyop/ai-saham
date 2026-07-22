"""Single, lazy composition root for the offline TUI adapter.

All infrastructure imports are intentionally confined to this module. The
capability is built inside the first worker call, then reused under a lock so
launch and Reload each execute exactly one serialized Daily request.

Layer: Adapter composition root
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any

from src.adapters.tui.controllers.accumulation_controller import (
    AccumulationController,
    AccumulationLoader,
)
from src.adapters.tui.controllers.daily_controller import (
    DailyController,
    DailyLoader,
    DailyPreviewer,
    DailyRefresher,
)
from src.application.use_case.refresh_daily_workspace_use_case import (
    DailyWorkspaceRefreshPlan,
    PreviewDailyWorkspaceRefreshUseCase,
    RefreshDailyWorkspaceRequest,
    RefreshDailyWorkspaceResult,
    RefreshDailyWorkspaceUseCase,
)
from src.adapters.tui.controllers.ticker_research_controller import (
    TickerLoader,
    TickerResearchController,
)
from src.adapters.tui.main import SahamTuiApp
from src.adapters.tui.presenters.accumulation_presenter import AccumulationPresenter
from src.adapters.tui.presenters.daily_presenter import DailyPresenter
from src.adapters.tui.presenters.ticker_research_presenter import TickerResearchPresenter
from src.adapters.tui.research_capabilities import (
    ResearchExecution,
    SerializedResearchCapabilities,
)
from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.application.services.swing_broker_detail_builder import (
    build_broker_detail,
    build_broker_quality_note,
    build_flow_detail,
)
from src.application.services.swing_data_freshness import build_swing_data_freshness
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.accumulation_screen_use_case import resolve_setup_targets
from src.application.use_case.assess_corporate_action_event_risk_use_case import (
    AssessCorporateActionEventRiskUseCase,
)
from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
from src.application.use_case.build_live_signal_evidence_execution_context_use_case import (
    BuildLiveSignalEvidenceExecutionContextUseCase,
)
from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingResponse,
    DailyBriefingUseCase,
)
from src.application.use_case.daily_setup_lens_impact_use_case import (
    DailySetupLensImpactUseCase,
    SwingLensRequestDefaults,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowUseCase,
)
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisWorkflowUseCase,
)
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.composition.risk_engine_factory import create_risk_engine
from src.infrastructure.composition.signal_engine_factory import create_signal_engine
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.analyze_swing_config import load_analyze_swing_config
from src.infrastructure.config.app_config import AppConfig, load_app_config
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
)
from src.infrastructure.config.corporate_action_policy_config import (
    load_corporate_action_policy_config,
)
from src.infrastructure.config.engine_config_loader import load_engine_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.config.market_context_config import load_market_context_config
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.sector_context_config_loader import (
    create_sector_context_evidence_builder,
)
from src.infrastructure.config.swing_config_loader import load_swing_config
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
)
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def _forbid_tui_refresh(**kwargs) -> None:
    raise RuntimeError("TUI local-only contract forbids provider refresh")


def _forbid_tui_sentiment(**kwargs) -> None:
    raise RuntimeError("TUI local-only contract forbids sentiment fetch")


@dataclass(frozen=True)
class _DailyExecution:
    use_case: DailyBriefingUseCase
    request: DailyBriefingRequest


@dataclass(frozen=True)
class _StockDependencies:
    db_path: Path
    app_config: AppConfig
    market_repository: Any
    broker_repository: Any
    observations_repository: Any
    stockbit_providers: Any

    def indicator_registry(self):
        return create_indicator_registry(
            market_repository=self.market_repository,
            broker_repository=self.broker_repository,
        )

    def signal_engine(self):
        return create_signal_engine(db_path=self.db_path, with_enrichment=True)

    def risk_engine(self):
        config = load_engine_config(Path(self.app_config.config_paths.risk_engine))
        return create_risk_engine(
            db_path=self.db_path,
            with_enrichment=True,
            rules_loader=RulesYamlLoader(),
            config=config,
        )

    def ticker_profile_classifier(self, profile_path=None, universes_path=None):
        paths = self.app_config.config_paths
        return create_ticker_profile_classifier(
            profile_path=profile_path or paths.ticker_profile,
            universes_path=universes_path or paths.universes,
        )

    def institutional_config(self, path=None):
        return load_institutional_accumulation_config(
            path=path or self.app_config.config_paths.institutional_accumulation
        )

    def sector_context_builder(self, config_path=None, universes_path=None):
        paths = self.app_config.config_paths
        return create_sector_context_evidence_builder(
            config_path=config_path or paths.sector_context,
            universes_path=universes_path or paths.universes,
        )

    def company_quality_builder(self, config_path=None, scoring=None, neutral_score=50.0):
        return create_company_quality_context_evidence_builder(
            config_path=config_path or self.app_config.config_paths.company_quality_context,
            scoring=scoring,
            neutral_score=neutral_score,
        )


class _SerializedDailyCapability:
    def __init__(self, factory: Callable[[], _DailyExecution]) -> None:
        self._factory = factory
        self._execution: _DailyExecution | None = None
        self._lock = Lock()

    def __call__(self) -> DailyBriefingResponse:
        with self._lock:
            if self._execution is None:
                self._execution = self._factory()
            return self._execution.use_case.execute(self._execution.request)


def _build_daily_request(config: AppConfig) -> DailyBriefingRequest:
    return DailyBriefingRequest(
        universe=config.analysis.universe,
        top=3,
        as_of_date=None,
        opening_data_dir=Path("data/opening"),
        universe_config_path=Path("config/universes.yaml"),
    )


def _build_dependencies(config: AppConfig, db_path: Path) -> _StockDependencies:
    return _StockDependencies(
        db_path=db_path,
        app_config=config,
        market_repository=SQLiteMarketRepository(db_path=db_path),
        broker_repository=SQLiteBrokerRepository(db_path),
        observations_repository=SQLiteCandidateObservationsRepository(db_path),
        stockbit_providers=create_readonly_stockbit_providers(db_path),
    )


def _build_accumulation_use_case(deps: _StockDependencies, *, risk_use_case=None):
    accumulation_config = load_accumulation_screener_config()
    return create_accumulation_screen_use_case(
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
        indicator_registry=deps.indicator_registry(),
        rules_loader=RulesYamlLoader(),
        stockbit_providers=deps.stockbit_providers,
        risk_use_case=risk_use_case,
        signal_engine=deps.signal_engine(),
        candidate_observations_repository=deps.observations_repository,
        foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
        derived_feature_policy=accumulation_config.derived_features,
        swing_setup_catalog=build_swing_setup_catalog_config(
            load_swing_config(config=deps.app_config)
        ),
        ticker_profile_classifier_factory=deps.ticker_profile_classifier,
        institutional_accumulation_config_factory=deps.institutional_config,
        sector_context_builder_factory=deps.sector_context_builder,
        company_quality_context_builder_factory=deps.company_quality_builder,
    )


def _build_candidate_builder(
    deps, swing_config, analyze_config, accumulation_config, signal_engine
):
    def build_candidate(ticker, window, as_of_date, *, execution_context):
        use_case = create_accumulation_screen_use_case(
            broker_repository=deps.broker_repository,
            market_repository=deps.market_repository,
            indicator_registry=deps.indicator_registry(),
            rules_loader=RulesYamlLoader(),
            stockbit_providers=deps.stockbit_providers,
            signal_engine=signal_engine,
            foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
            derived_feature_policy=accumulation_config.derived_features,
            ticker_profile_classifier_factory=deps.ticker_profile_classifier,
            institutional_accumulation_config_factory=deps.institutional_config,
            sector_context_builder_factory=deps.sector_context_builder,
            company_quality_context_builder_factory=deps.company_quality_builder,
        )
        response = use_case.execute(
            AccumulationScreenRequest(
                tickers=[ticker],
                as_of_date=as_of_date,
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
            ),
            execution_context=execution_context,
        )
        if not response.candidates:
            return None
        selected = response.candidates[0]
        for observation in response.observation_candidates:
            if observation.candidate is selected:
                return observation.evaluation_result
        raise ValueError(
            f"Accumulation screen selected {selected.ticker!r} without matching "
            "observation evaluation"
        )

    return build_candidate


def _build_broker_detail_builder(swing_config, broker_weights):
    smart = set(swing_config.smart_money_brokers)
    noise = set(swing_config.noise_brokers)

    def builder(ticker, broker_repo, window_sessions=5, as_of_date=None):
        return build_broker_detail(
            ticker=ticker,
            broker_repo=broker_repo,
            window_sessions=window_sessions,
            as_of_date=as_of_date,
            smart_money_brokers=smart,
            noise_brokers=noise,
            broker_weights=broker_weights,
            smart_share_threshold_pct=swing_config.smart_share_threshold_pct,
        )

    return builder


def _build_setup_evaluator(setup_name, swing_config):
    setup_config = build_swing_setup_catalog_config(swing_config)

    def evaluator(candidate, broker_detail=None):
        return EvaluateSwingSetupUseCase().execute(
            EvaluateSwingSetupRequest(
                setup_name=setup_name,
                candidate=candidate,
                config=setup_config,
                broker_detail=broker_detail,
            )
        )

    return evaluator


def _build_swing_workflow(deps: _StockDependencies, setup_name: str | None):
    swing_config = load_swing_config(config=deps.app_config)
    analyze_config = load_analyze_swing_config()
    accumulation_config = load_accumulation_screener_config()
    smart = set(swing_config.smart_money_brokers)
    noise = set(swing_config.noise_brokers)
    broker_weights: dict[str, Decimal] = {
        **{code: swing_config.smart_weight for code in smart},
        **{code: swing_config.noise_weight for code in noise},
    }
    signal_engine = deps.signal_engine()
    return SwingAnalysisWorkflowUseCase(
        market_repository=deps.market_repository,
        broker_repository=deps.broker_repository,
        registry=deps.indicator_registry(),
        refresh_data=_forbid_tui_refresh,
        build_data_freshness=build_swing_data_freshness,
        build_flow_detail=build_flow_detail,
        build_broker_detail=_build_broker_detail_builder(swing_config, broker_weights),
        build_accumulation_candidate_evaluation=_build_candidate_builder(
            deps, swing_config, analyze_config, accumulation_config, signal_engine
        ),
        evaluate_setup=_build_setup_evaluator(setup_name, swing_config),
        build_broker_quality_note=lambda broker_detail, setup_eval: build_broker_quality_note(
            broker_detail,
            setup_eval,
            smart_sell_min_share_pct=swing_config.smart_sell_min_share_pct,
        ),
        fetch_sentiment=_forbid_tui_sentiment,
        load_swing_config=lambda: swing_config,
        resolve_setup_targets=resolve_setup_targets,
        rules_loader=RulesYamlLoader(),
        evaluate_market_context=evaluate_market_context,
        structural_gates=[FundamentalGate(), LiquidityGate(), FreeFloatGate()],
        execution_gates=[BandarGate()],
        signal_engine=signal_engine,
        risk_engine=deps.risk_engine(),
        candidate_observations_repository=deps.observations_repository,
        foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
        corporate_action_risk_use_case=AssessCorporateActionEventRiskUseCase(
            repository=SQLiteCorporateActionCalendarRepository(deps.db_path),
            policy=load_corporate_action_policy_config(),
        ),
        ticker_profile_classifier_factory=deps.ticker_profile_classifier,
        institutional_accumulation_config_factory=deps.institutional_config,
        sector_context_builder_factory=deps.sector_context_builder,
        company_quality_context_builder_factory=deps.company_quality_builder,
        session_resolver=EffectiveMarketSessionResolver(deps.market_repository),
        signal_evidence_context_builder=SignalEvidenceExecutionContextBuilder(
            trading_session_calendar_loader=lambda start, end: IHSGTradingSessionCalendarProvider(
                deps.market_repository
            ).load(
                coverage_start=start,
                coverage_end=end,
            )
        ),
    )


def _build_setup_lens(deps: _StockDependencies) -> DailySetupLensImpactUseCase:
    config = deps.app_config
    analyze_config = load_analyze_swing_config()
    return DailySetupLensImpactUseCase(
        setup_workflows={
            setup_name: _build_swing_workflow(deps, setup_name)
            for setup_name in AVAILABLE_SWING_SETUPS
        },
        request_defaults=SwingLensRequestDefaults(
            window=config.swing.window,
            flow_window=analyze_config.flow_detail_window_sessions,
            risk_pct=config.swing.risk_pct,
            atr_mult=config.swing.atr_mult,
            rr=config.swing.rr,
            regime_universe=config.analysis.regime_universe,
            benchmark=config.analysis.benchmark,
            db_path=deps.db_path,
        ),
    )


def _build_daily_execution() -> _DailyExecution:
    config = load_app_config()
    db_path = Path(config.storage.db_path)
    deps = _build_dependencies(config, db_path)
    risk_config = load_engine_config(Path(config.config_paths.risk_engine))
    from src.application.services.engine_bootstrap.risk_config_resolvers import (
        resolve_risk_gates,
    )

    structural, execution = resolve_risk_gates(risk_config)
    risk_use_case = AssessRiskUseCase(
        repository=deps.market_repository,
        structural_gates=structural,
        execution_gates=execution,
    )
    regime_tickers = resolve_tickers(
        universe=config.analysis.regime_universe,
        explicit=[],
        db_path=db_path,
        loader=YamlUniverseConfigLoader(),
        repository=deps.broker_repository,
    )
    use_case = DailyBriefingUseCase(
        market_repository=deps.market_repository,
        broker_repository=deps.broker_repository,
        regime_use_case=MarketContextEngine(
            market_repository=deps.market_repository,
            config=load_market_context_config(),
            broker_repository=deps.broker_repository,
            universe=regime_tickers,
        ),
        accumulation_use_case=_build_accumulation_use_case(deps, risk_use_case=risk_use_case),
        universe_loader=YamlUniverseConfigLoader(),
        setup_lens_impact_use_case=_build_setup_lens(deps),
        session_resolver=EffectiveMarketSessionResolver(deps.market_repository),
    )
    return _DailyExecution(use_case=use_case, request=_build_daily_request(config))


def create_daily_capability() -> DailyLoader:
    return _SerializedDailyCapability(_build_daily_execution)


def _build_research_execution() -> ResearchExecution:
    config = load_app_config()
    db_path = Path(config.storage.db_path)
    deps = _build_dependencies(config, db_path)
    screener = load_accumulation_screener_config()
    swing_config = load_swing_config(config=config)
    screen = _build_accumulation_use_case(deps)
    live_context = BuildLiveSignalEvidenceExecutionContextUseCase(
        session_resolver=EffectiveMarketSessionResolver(deps.market_repository),
        context_builder=SignalEvidenceExecutionContextBuilder(
            trading_session_calendar_loader=lambda start, end: IHSGTradingSessionCalendarProvider(
                deps.market_repository
            ).load(
                coverage_start=start,
                coverage_end=end,
            )
        ),
        market_data_repository=deps.market_repository,
    )
    accumulation = RunAccumulationScreenWorkflowUseCase(
        screen_use_case=screen,
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
        swing_config=swing_config,
        accumulation_screener_config=screener,
        rules_loader=RulesYamlLoader(),
        indicator_registry_factory=create_indicator_registry,
        live_signal_evidence_context_use_case=live_context,
        save_watchlist_use_case=None,
    )
    tickers = resolve_tickers(
        universe=config.analysis.universe,
        explicit=[],
        db_path=db_path,
        loader=YamlUniverseConfigLoader(),
        repository=deps.broker_repository,
    )
    return ResearchExecution(
        accumulation,
        _build_swing_workflow(deps, None),
        config,
        db_path,
        tickers,
        load_analyze_swing_config().flow_detail_window_sessions,
    )


def _build_daily_refresh_execution(
    request: RefreshDailyWorkspaceRequest,
    *,
    on_start: Any = None,
    on_ticker_complete: Any = None,
) -> RefreshDailyWorkspaceResult:
    config = load_app_config()
    db_path = Path(config.storage.db_path)
    sb_providers = create_readonly_stockbit_providers(db_path)
    sb_client = sb_providers.session if sb_providers else None

    from src.adapters.cli.fetch_market_workflow_factory import create_workflow_use_case
    workflow_use_case = create_workflow_use_case(
        db_path=db_path,
        broker_provider=sb_client,
        broker_provider_name="stockbit" if sb_client else "none",
    )

    from src.application.use_case.fetch_market_command_workflow_use_case import (
        FetchMarketCommandWorkflowRequest,
    )

    candles_only = request.components == "CANDLES_ONLY"
    broker_only = request.components == "BROKER_ONLY"

    workflow_req = FetchMarketCommandWorkflowRequest(
        tickers=list(request.tickers),
        universe=request.universe if not request.tickers else None,
        days=request.days,
        db_path=db_path,
        candles_provider="yfinance",
        broker_provider=sb_client,
        broker_provider_name="stockbit" if sb_client else "none",
        refresh=request.force_refresh,
        candles_only=candles_only,
        broker_only=broker_only,
        no_meta=not request.include_meta,
        no_enrichment=not request.include_enrichment,
        no_calendar=not request.include_calendar,
    )

    def refresh_market_data_capability(req: Any, on_start: Any = None, on_ticker_complete: Any = None):
        return workflow_use_case.execute(
            workflow_req,
            on_start=on_start,
            on_ticker_complete=on_ticker_complete,
        )

    daily_exec = _build_daily_execution()
    use_case = RefreshDailyWorkspaceUseCase(
        refresh_market_data_capability=refresh_market_data_capability,
        daily_briefing_use_case=daily_exec.use_case,
    )
    return use_case.execute(
        request,
        on_start=on_start,
        on_ticker_complete=on_ticker_complete,
    )


def _build_daily_preview_execution(
    request: RefreshDailyWorkspaceRequest,
) -> DailyWorkspaceRefreshPlan:
    config = load_app_config()
    db_path = Path(config.storage.db_path)
    sb_providers = create_readonly_stockbit_providers(db_path)
    sb_client = sb_providers.session if sb_providers else None
    broker_name = "stockbit" if sb_client else "none"

    def resolver_capability(req: RefreshDailyWorkspaceRequest):
        tickers = resolve_tickers(
            universe=req.universe,
            explicit=list(req.tickers),
            db_path=db_path,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(db_path),
        )
        return (len(tickers), "yfinance", broker_name, ())

    use_case = PreviewDailyWorkspaceRefreshUseCase(resolver_capability)
    return use_case.execute(request)


def create_tui_app(
    *,
    daily_loader: DailyLoader | None = None,
    daily_refresher: DailyRefresher | None = None,
    daily_previewer: DailyPreviewer | None = None,
    accumulation_loader: AccumulationLoader | None = None,
    ticker_loader: TickerLoader | None = None,
) -> SahamTuiApp:
    daily = daily_loader or create_daily_capability()
    refresher = daily_refresher or _build_daily_refresh_execution
    previewer = daily_previewer or _build_daily_preview_execution
    research = SerializedResearchCapabilities(_build_research_execution)
    accumulation = accumulation_loader or research.load_accumulation
    ticker = ticker_loader or research.load_ticker
    return SahamTuiApp(
        DailyController(daily, refresh_daily=refresher, preview_daily=previewer),
        DailyPresenter(),
        AccumulationController(accumulation),
        AccumulationPresenter(),
        TickerResearchController(ticker),
        TickerResearchPresenter(),
    )
