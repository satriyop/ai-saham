"""
Application workflow coordinator for `saham analyze swing`.

Layer: Application
AI usage: Optional sentiment provider, controlled by injected fetcher.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.application.dto import swing_analysis as swing_analysis_dto

if TYPE_CHECKING:
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse

from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.strategy_loader import StrategyLoader
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase
from src.application.use_case.score_foreign_flow_use_case import ForeignFlowScorePolicy
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.candidate_observations_repository import (
    CandidateObservationsRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker

if TYPE_CHECKING:
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.institutional_accumulation_evidence import InstitutionalAccumulationEvidence
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.trade_setup import TradeSetup


def _benchmark_return_from_repository(
    repository: MarketDataRepository,
    *,
    benchmark: str,
    end_date: date,
    lookback: int,
    min_valid: int,
) -> float | None:
    try:
        candles = repository.get_candles(
            canonicalize_ticker(benchmark),
            end_date=end_date,
        )
    except Exception:
        return None
    return _simple_return(candles, lookback=lookback, min_valid=min_valid)


def _simple_return(
    candles: list[Any] | tuple[Any, ...],
    *,
    lookback: int,
    min_valid: int,
) -> float | None:
    sorted_candles = sorted(candles, key=lambda c: c.date)
    window = sorted_candles[-lookback:] if len(sorted_candles) >= lookback else sorted_candles
    valid = [c for c in window if getattr(c, "close", None) and float(c.close) > 0.0]
    if len(valid) < min_valid:
        return None
    reference = float(valid[0].close)
    if reference <= 0.0:
        return None
    return (float(valid[-1].close) - reference) / reference


class SwingAnalysisWorkflowUseCase:
    """Run deterministic swing analysis steps and return structured state."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        registry: Any,
        refresh_data: Callable[..., tuple[str, ...]],
        build_data_freshness: Callable[..., Any],
        build_flow_detail: Callable[..., Any],
        build_broker_detail: Callable[..., Any],
        build_accumulation_candidate: Callable[..., Any | None],
        evaluate_setup: Callable[[Any | None, Any | None], Any | None],
        build_broker_quality_note: Callable[..., Any | None],
        fetch_sentiment: Callable[..., tuple[Any | None, str | None]],
        load_swing_config: Callable[[], Any],
        resolve_setup_targets: Callable[[str | None, Any], tuple[Decimal, Decimal]],
        evaluate_market_context: Callable[..., "MarketContext"] | None = None,
        structural_gates: list[RiskGate] | None = None,
        execution_gates: list[RiskGate] | None = None,
        signal_engine: "SignalEngine | None" = None,
        risk_engine: "RiskEngine | None" = None,
        candidate_observations_repository: CandidateObservationsRepository | None = None,
        foreign_flow_score_policy: ForeignFlowScorePolicy | None = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate = build_accumulation_candidate
        self._evaluate_setup = evaluate_setup
        self._build_broker_quality_note = build_broker_quality_note
        self._fetch_sentiment = fetch_sentiment
        self._load_swing_config = load_swing_config
        self._resolve_setup_targets = resolve_setup_targets
        self._evaluate_market_context = evaluate_market_context
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []
        self._signal_engine = signal_engine
        self._risk_engine = risk_engine
        self._candidate_observations_repo = candidate_observations_repository
        # Derive weights from the same policy ScoreForeignFlowUseCase/screener
        # use, so the two can never drift apart (see ADR-039).
        self._flow_confirmation_builder = FlowConfirmationEvidenceBuilder(
            foreign_flow_score_policy=foreign_flow_score_policy
        )

    def execute(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
    ) -> swing_analysis_dto.SwingAnalysisWorkflowResponse:
        warnings: list[str] = []

        refresh_actions = ("disabled",)
        if request.auto_refresh:
            refresh_actions = self._refresh_data(
                ticker=request.ticker,
                db_path=request.db_path,
                force_refresh=request.force_refresh,
            )

        data_freshness = self._build_data_freshness(
            ticker=request.ticker,
            as_of_date=request.today,
            market_repo=self._market_repo,
            broker_repo=self._broker_repo,
            refresh_actions=refresh_actions,
        )
        needs_broker_detail = request.include_flow_detail or request.setup_name is not None
        flow_detail = None
        if request.include_flow_detail:
            flow_detail = self._build_flow_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=request.flow_window,
                as_of_date=request.today,
            )
        broker_detail = None
        if needs_broker_detail:
            broker_detail = self._build_broker_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=5,
                as_of_date=request.today,
            )

        candles = self._market_repo.get_candles(request.ticker)
        if not candles:
            raise SwingAnalysisDataUnavailable(request.ticker)
        latest_close = candles[-1].close

        accumulation_candidate = None
        try:
            accumulation_candidate = self._build_accumulation_candidate(
                ticker=request.ticker,
                window=request.window,
            )
        except Exception as exc:
            warnings.append(f"Accumulation unavailable: {exc}")

        market_regime = None
        if request.with_market_context:
            try:
                if self._evaluate_market_context is None:
                    raise RuntimeError("Market context evaluator is not configured.")
                market_regime = self._evaluate_market_context(
                    db_path=request.db_path,
                    as_of_date=request.today,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        risk_response = None
        try:
            gate_ctx: GateContext | None = None
            if (self._structural_gates or self._execution_gates or request.with_technical_gate) and accumulation_candidate is not None:
                fund = accumulation_candidate.fundamentals
                bandar = accumulation_candidate.bandar_detector
                shareholding = accumulation_candidate.shareholding
                gate_ctx = GateContext(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    piotroski_f_score=fund.piotroski_f_score if fund else None,
                    market_cap_idr=fund.market_cap_idr if fund else None,
                    free_float_pct=shareholding.free_float_pct if shareholding else None,
                    five_day_accdist=bandar.five_day_accdist if bandar else None,
                )
            if request.with_technical_gate:
                # Opt-in TechnicalGate path: route through a use case that
                # appends TechnicalGate to the execution tier.
                from src.application.services.indicator_evaluator import IndicatorEvaluator
                from src.domain.rules.technical_gate import TechnicalGate

                evaluator = (
                    self._risk_engine.indicator_evaluator
                    if self._risk_engine is not None
                    else None
                ) or IndicatorEvaluator()
                indicator_defaults = (
                    self._risk_engine.indicator_defaults
                    if self._risk_engine is not None
                    else None
                )
                technical_gate_config = (
                    self._risk_engine.technical_gate_config
                    if self._risk_engine is not None
                    else None
                )
                execution_gates = list(self._execution_gates) + [
                    TechnicalGate(evaluator, technical_gate_config)
                ]
                risk_use_case = AssessRiskUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                    structural_gates=self._structural_gates or None,
                    execution_gates=execution_gates,
                    indicator_evaluator=evaluator,
                    indicator_history_days=indicator_defaults.history_days
                    if indicator_defaults is not None else 365,
                    gate_recent_candle_lookback=indicator_defaults.gate_recent_candle_lookback
                    if indicator_defaults is not None else 20,
                )
                risk_response = risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=request.ticker,
                        sma_period=indicator_defaults.sma_period
                        if indicator_defaults is not None else 20,
                        ema_period=indicator_defaults.ema_period
                        if indicator_defaults is not None else 20,
                        rsi_period=indicator_defaults.rsi_period
                        if indicator_defaults is not None else 14,
                        gate_context=gate_ctx,
                    )
                )
            elif self._risk_engine is not None and gate_ctx is not None:
                risk_response = self._risk_engine.assess_with_context(
                    ticker=request.ticker,
                    gate_context=gate_ctx,
                    market_context=None,
                )
            elif self._risk_engine is not None:
                risk_response = self._risk_engine.assess(
                    ticker=request.ticker,
                    as_of_date=request.today,
                    market_context=None,
                )
            else:
                risk_use_case = AssessRiskUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                    structural_gates=self._structural_gates or None,
                    execution_gates=self._execution_gates or None,
                )
                risk_response = risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=request.ticker,
                        gate_context=gate_ctx,
                    )
            )
        except Exception as exc:
            warnings.append(f"Risk assessment unavailable: {exc}")

        signal_assessment = None
        if self._signal_engine is not None:
            try:
                if (
                    accumulation_candidate is not None
                    and accumulation_candidate.signal_assessment is not None
                ):
                    # Fast path: reuse screener's pre-computed raw signal — no recomputation
                    signal_assessment = accumulation_candidate.signal_assessment
                elif accumulation_candidate is not None:
                    # Fallback: candidate exists but screener ran without a signal_engine
                    signal_ctx = build_signal_context_from_candidate(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        candidate=accumulation_candidate,
                        signal_engine=self._signal_engine,
                    )
                    signal_assessment = self._signal_engine.evaluate_with_context(
                        request.ticker,
                        signal_ctx,
                        market_context=market_regime,
                        setup_family=request.setup_name,
                    )
                else:
                    # No candidate — provider-based standalone evaluation
                    signal_assessment = self._signal_engine.evaluate(
                        request.ticker,
                        request.today,
                        market_context=market_regime,
                    )
            except Exception as exc:
                warnings.append(f"Signal assessment unavailable: {exc}")

        atr_value = self._compute_atr(candles)
        sizing: SizingResult | None = None
        setup_eval = None
        setup_sizing: PercentSizingResult | None = None
        if request.setup_name is not None:
            setup_eval = self._evaluate_setup(accumulation_candidate, broker_detail)

        broker_quality_note = self._build_broker_quality_note(
            broker_detail=broker_detail,
            setup_eval=setup_eval,
        )

        setup_entry: Decimal | None = None
        if request.capital is not None and setup_eval is not None and setup_eval.passed:
            setup_entry = (
                Decimal(str(request.entry_price))
                if request.entry_price
                else latest_close
            )
        elif request.capital is not None and atr_value and setup_eval is None:
            try:
                entry = (
                    Decimal(str(request.entry_price))
                    if request.entry_price
                    else latest_close
                )
                sizing = compute_position_size(
                    entry=entry,
                    atr=atr_value,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    atr_multiplier=Decimal(str(request.atr_mult)),
                    reward_risk=Decimal(str(request.rr)),
                )
            except ValueError as exc:
                warnings.append(f"Position sizing unavailable: {exc}")

        backtest_result = None
        if request.strategy_name is not None:
            try:
                loader = StrategyLoader(registry=self._registry)
                rules_path = loader.resolve(request.strategy_name)
                backtest_use_case = BacktestUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                )
                backtest_response = backtest_use_case.execute(
                    BacktestRequest(
                        ticker=request.ticker,
                        rules_file=rules_path,
                        initial_capital=Decimal("100000000"),
                    )
                )
                backtest_result = backtest_response.result
            except Exception as exc:
                warnings.append(f"Backtest unavailable: {exc}")

        sentiment_response = None
        sentiment_warning = None
        if request.include_sentiment:
            sentiment_response, sentiment_warning = self._fetch_sentiment(
                ticker=request.ticker,
                sentiment_verbose=request.sentiment_verbose,
            )

        trade_setup = None
        if signal_assessment is not None and risk_response is not None:
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                trade_setup = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        signal_response=signal_assessment,
                        risk_response=risk_response,
                        market_context=None,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"TradeSetup unavailable: {exc}")

        market_context_signal_preview = None
        market_context_risk_preview = None
        market_context_trade_setup_preview = None
        if (
            market_regime is not None
            and signal_assessment is not None
            and risk_response is not None
            and self._signal_engine is not None
            and self._risk_engine is not None
        ):
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                # Phase 5: canonical signal already includes regime conditioning.
                # MCE preview still differs via risk_preview (regime-adjusted risk).
                market_context_signal_preview = signal_assessment
                market_context_risk_preview = self._risk_engine.apply_market_context(
                    risk_response, market_regime
                )
                market_context_trade_setup_preview = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        signal_response=market_context_signal_preview,
                        risk_response=market_context_risk_preview,
                        market_context=market_regime,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"Market context preview unavailable: {exc}")

        swing_config = self._load_swing_config()
        regime_label = market_regime.regime.value if market_regime else None
        take_profit_pct, stop_loss_pct = self._resolve_setup_targets(
            regime_label,
            swing_config,
        )
        if setup_entry is not None and request.capital is not None:
            try:
                setup_sizing = compute_percent_position_size(
                    entry=setup_entry,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                )
            except ValueError as exc:
                warnings.append(f"Setup sizing unavailable: {exc}")

        verdict = swing_analysis_dto.SwingVerdict(
            trade_setup=trade_setup,
            signal_assessment=signal_assessment,
            risk_response=risk_response,
            market_regime=market_regime,
            market_context_signal_preview=market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=market_context_trade_setup_preview,
        )
        setup_evidence = None
        if accumulation_candidate is not None and setup_eval is not None:
            try:
                from src.application.services.candle_provenance import (
                    resolve_candle_source,
                )
                from src.application.services.setup_evidence_builder import (
                    SetupEvidenceBuilder,
                )

                candle_source = resolve_candle_source(
                    self._market_repo,
                    ticker=request.ticker,
                    as_of_date=candles[-1].date,
                )
                setup_evidence = SetupEvidenceBuilder().build(
                    accumulation_candidate,
                    setup_eval,
                    rs_vs_ihsg_5d=None,
                    volume_trend_ratio=None,
                    candle_source=candle_source,
                    analysis_date=request.today,
                )
            except Exception as exc:
                warnings.append(f"Setup evidence unavailable: {exc}")

        flow_confirmation_evidence = None
        if accumulation_candidate is not None:
            try:
                flow_confirmation_evidence = self._flow_confirmation_builder.build(
                    accumulation_candidate,
                    analysis_date=request.today,
                )
            except Exception as exc:
                warnings.append(f"Flow confirmation evidence unavailable: {exc}")

        setup_phase = None
        if setup_eval is not None:
            try:
                from src.application.services.setup_phase_detector import (
                    SetupPhaseConfig,
                    SetupPhaseDetector,
                )
                from src.application.services.setup_phase_history import (
                    load_previous_setup_phases,
                )

                setup_phase_config = getattr(
                    swing_config,
                    "setup_phase_config",
                    SetupPhaseConfig(),
                )
                previous_phases = load_previous_setup_phases(
                    self._candidate_observations_repo,
                    ticker=request.ticker,
                    before_date=request.today,
                    setup_family=request.setup_name,
                )
                setup_phase = SetupPhaseDetector().detect(
                    candles=candles,
                    setup_eval=setup_eval,
                    setup_evidence=setup_evidence,
                    flow_evidence=flow_confirmation_evidence,
                    setup_family=request.setup_name,
                    previous_phases=previous_phases,
                    config=setup_phase_config,
                )
            except Exception as exc:
                warnings.append(f"Setup phase unavailable: {exc}")

        strategy_rule_evidence = None
        if request.strategy_name is not None:
            try:
                from src.application.services.strategy_evidence_builder import (
                    StrategyEvidenceBuilder,
                    StrategyEvidenceRequest,
                )

                strategy_rule_evidence = StrategyEvidenceBuilder(
                    registry=self._registry,
                    loader=StrategyLoader(registry=self._registry),
                ).build(
                    StrategyEvidenceRequest(
                        ticker=request.ticker,
                        strategy_name=request.strategy_name,
                        candles=tuple(candles),
                        snapshot_date=request.today,
                        setup_family=request.setup_name,
                        setup_phase=setup_phase,
                    )
                )
            except Exception as exc:
                warnings.append(f"Strategy evidence unavailable: {exc}")

        broker_daily_flows: tuple = ()
        broker_summaries: tuple = ()
        institutional_accumulation_evidence = None
        try:
            from datetime import timedelta

            from src.application.services.institutional_accumulation_evidence_builder import (
                InstitutionalAccumulationEvidenceBuilder,
                InstitutionalAccumulationEvidenceRequest,
            )

            ia_start_date = request.today - timedelta(days=45)
            broker_daily_flows = tuple(
                self._broker_repo.get_broker_daily_flows(
                    request.ticker, start_date=ia_start_date, end_date=request.today
                )
            )
            foreign_flow_points = tuple(
                self._broker_repo.get_foreign_flow_points(
                    request.ticker, start_date=ia_start_date, end_date=request.today
                )
            )
            broker_summaries = tuple(
                self._broker_repo.get_broker_summaries(
                    request.ticker, start_date=ia_start_date, end_date=request.today
                )
            )
            institutional_accumulation_evidence = (
                InstitutionalAccumulationEvidenceBuilder.from_yaml().build(
                    InstitutionalAccumulationEvidenceRequest(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        broker_daily_flows=broker_daily_flows,
                        foreign_flow_points=foreign_flow_points,
                        broker_summaries=broker_summaries,
                        bandar_snapshot=(
                            accumulation_candidate.bandar_detector
                            if accumulation_candidate is not None
                            else None
                        ),
                        candles=tuple(candles),
                    )
                )
            )
        except Exception as exc:
            warnings.append(f"Institutional accumulation evidence unavailable: {exc}")

        ticker_profile_snapshot = None
        try:
            from decimal import Decimal as _Decimal

            from src.application.services.ticker_profile_classifier import (
                TickerProfileClassifier,
                TickerProfileRequest,
            )

            tp_market_cap_idr: _Decimal | None = None
            if (
                accumulation_candidate is not None
                and accumulation_candidate.fundamentals is not None
                and accumulation_candidate.fundamentals.market_cap_idr is not None
            ):
                tp_market_cap_idr = _Decimal(
                    str(accumulation_candidate.fundamentals.market_cap_idr)
                )
            tp_sector = (
                accumulation_candidate.ticker_notation.sector
                if accumulation_candidate is not None
                and accumulation_candidate.ticker_notation is not None
                else None
            )
            tp_sub_sector = (
                accumulation_candidate.ticker_notation.sub_sector
                if accumulation_candidate is not None
                and accumulation_candidate.ticker_notation is not None
                else None
            )
            ticker_profile_snapshot = TickerProfileClassifier.from_yaml().classify(
                TickerProfileRequest(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    candles=tuple(candles),
                    broker_daily_flows=broker_daily_flows,
                    broker_summaries=broker_summaries,
                    market_cap_idr=tp_market_cap_idr,
                    sector=tp_sector,
                    sub_sector=tp_sub_sector,
                )
            )
        except Exception as exc:
            warnings.append(f"Ticker profile classification unavailable: {exc}")

        sector_context_evidence = None
        try:
            from src.application.services.sector_context_evidence_builder import (
                SectorContextEvidenceBuilder,
                SectorContextRequest,
            )

            sc_builder = SectorContextEvidenceBuilder.from_yaml()
            sc_sector = (
                accumulation_candidate.ticker_notation.sector
                if accumulation_candidate is not None
                and accumulation_candidate.ticker_notation is not None
                else None
            ) or (
                ticker_profile_snapshot.sector if ticker_profile_snapshot is not None else None
            )
            peer_tickers = sc_builder.peers_for_ticker(request.ticker)
            peer_candles: dict[str, list] = {}
            for peer in peer_tickers:
                try:
                    pc = self._market_repo.get_candles(peer)
                    if pc:
                        peer_candles[peer] = list(pc)
                except Exception:
                    pass
            ihsg_20d_return = _benchmark_return_from_repository(
                self._market_repo,
                benchmark=request.benchmark,
                end_date=request.today,
                lookback=20,
                min_valid=18,
            )
            sector_context_evidence = sc_builder.build(
                SectorContextRequest(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    sector=sc_sector,
                    ticker_candles=tuple(candles),
                    peer_candles=peer_candles,
                    ihsg_20d_return=ihsg_20d_return,
                )
            )
        except Exception as exc:
            warnings.append(f"Sector context evidence unavailable: {exc}")

        # DIAGNOSTIC-only company-quality / ticker-alpha conviction evidence.
        # Built from the same enrichment already loaded on accumulation_candidate;
        # no extra fetch. Feeds the Alpha/Trigger company_quality_context slot with
        # zero effective score authority (DIAGNOSTIC → effective_weight 0.0).
        company_quality_context_evidence = None
        if accumulation_candidate is not None and self._signal_engine is not None:
            try:
                from src.application.services.company_quality_context_evidence_builder import (
                    CompanyQualityContextEvidenceBuilder,
                    CompanyQualityContextRequest,
                )

                _cq_ctx = build_signal_context_from_candidate(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    candidate=accumulation_candidate,
                    signal_engine=self._signal_engine,
                )
                company_quality_context_evidence = (
                    CompanyQualityContextEvidenceBuilder.from_yaml().build(
                        CompanyQualityContextRequest(
                            ticker=request.ticker,
                            snapshot_date=request.today,
                            signal_context=_cq_ctx,
                        )
                    )
                )
            except Exception as exc:
                warnings.append(f"Company quality context evidence unavailable: {exc}")

        evidence = swing_analysis_dto.SwingEvidence(
            accumulation_candidate=accumulation_candidate,
            setup_eval=setup_eval,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
            setup_evidence=setup_evidence,
            flow_confirmation_evidence=flow_confirmation_evidence,
            setup_phase=setup_phase,
            strategy_rule_evidence=strategy_rule_evidence,
            institutional_accumulation_evidence=institutional_accumulation_evidence,
            ticker_profile_snapshot=ticker_profile_snapshot,
            sector_context_evidence=sector_context_evidence,
            company_quality_context_evidence=company_quality_context_evidence,
        )

        # Re-score with evidence now that both groups are available. Signal was
        # computed earlier (before setup_eval existed), so that score had no
        # evidence groups and confidence=0. Recompose all downstream outputs
        # (TradeSetup, MCE preview) so verdict is internally consistent.
        if (
            self._signal_engine is not None
            and accumulation_candidate is not None
            and (setup_evidence is not None or flow_confirmation_evidence is not None)
        ):
            try:
                _evidence_ctx = build_signal_context_from_candidate(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    candidate=accumulation_candidate,
                    signal_engine=self._signal_engine,
                )
                signal_assessment = self._signal_engine.evaluate_with_context(
                    request.ticker,
                    _evidence_ctx,
                    market_context=market_regime,
                    setup_evidence=setup_evidence,
                    flow_confirmation_evidence=flow_confirmation_evidence,
                    setup_family=request.setup_name,
                    setup_phase=setup_phase,
                    sector_context_evidence=sector_context_evidence,
                    company_quality_context_evidence=company_quality_context_evidence,
                )
            except Exception as exc:
                warnings.append(f"Evidence-enriched signal re-score unavailable: {exc}")
            else:
                # Re-score succeeded — recompose trade_setup and MCE preview so
                # all three fields in verdict use the same enriched signal score.
                _new_trade_setup = trade_setup
                _new_mce_signal = market_context_signal_preview
                _new_mce_trade_preview = market_context_trade_setup_preview

                if risk_response is not None:
                    try:
                        from src.application.use_case.assess_trade_setup_use_case import (
                            AssessTradeSetupRequest,
                            AssessTradeSetupUseCase,
                        )
                        _new_trade_setup = AssessTradeSetupUseCase().execute(
                            AssessTradeSetupRequest(
                                ticker=request.ticker,
                                snapshot_date=request.today,
                                signal_response=signal_assessment,
                                risk_response=risk_response,
                                market_context=None,
                            )
                        ).setup
                    except Exception as exc:
                        warnings.append(f"TradeSetup re-composition unavailable: {exc}")

                if market_context_risk_preview is not None:
                    try:
                        from src.application.use_case.assess_trade_setup_use_case import (
                            AssessTradeSetupRequest,
                            AssessTradeSetupUseCase,
                        )
                        # Phase 5: canonical signal already includes regime — no
                        # separate apply_market_context() needed for signal preview.
                        _new_mce_signal = signal_assessment
                        _new_mce_trade_preview = AssessTradeSetupUseCase().execute(
                            AssessTradeSetupRequest(
                                ticker=request.ticker,
                                snapshot_date=request.today,
                                signal_response=_new_mce_signal,
                                risk_response=market_context_risk_preview,
                                market_context=market_regime,
                            )
                        ).setup
                    except Exception as exc:
                        warnings.append(f"MCE preview re-computation unavailable: {exc}")

                verdict = replace(
                    verdict,
                    signal_assessment=signal_assessment,
                    trade_setup=_new_trade_setup,
                    market_context_signal_preview=_new_mce_signal,
                    market_context_trade_setup_preview=_new_mce_trade_preview,
                )

        diagnostics = swing_analysis_dto.SwingDiagnostics(
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            broker_quality_note=broker_quality_note,
            refresh_actions=refresh_actions,
            warnings=tuple(warnings),
        )

        return swing_analysis_dto.SwingAnalysisWorkflowResponse(
            ticker=request.ticker,
            today=request.today,
            refresh_actions=refresh_actions,
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            candles=candles,
            latest_close=latest_close,
            accumulation_candidate=accumulation_candidate,
            risk_response=risk_response,
            atr_value=atr_value,
            sizing=sizing,
            setup_eval=setup_eval,
            setup_sizing=setup_sizing,
            broker_quality_note=broker_quality_note,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            market_regime=market_regime,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
            signal_assessment=verdict.signal_assessment,
            trade_setup=verdict.trade_setup,
            market_context_signal_preview=verdict.market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=verdict.market_context_trade_setup_preview,
            verdict=verdict,
            evidence=evidence,
            diagnostics=diagnostics,
            modules={
                "setup": request.setup_name is not None,
                "sizing": request.capital is not None,
                "strategy": request.strategy_name is not None,
                "sentiment": request.include_sentiment,
                "flow_detail": request.include_flow_detail,
                "signal_detail": request.include_signal_detail,
                "risk_detail": request.include_risk_detail,
                "market_detail": request.include_market_detail,
                "market_context": request.with_market_context,
                "technical_gate": request.with_technical_gate,
            },
            warnings=tuple(warnings),
        )

    def _compute_atr(self, candles: list[Any]) -> Decimal | None:
        try:
            atr_values = self._registry.compute("ATR", candles, 14)
            if atr_values:
                return atr_values[-1][1]
        except Exception:
            return None
        return None

class SwingAnalysisDataUnavailable(Exception):
    """Raised when a ticker has no local candle data for swing analysis."""

    def __init__(self, ticker: str) -> None:
        super().__init__(ticker)
        self.ticker = ticker
