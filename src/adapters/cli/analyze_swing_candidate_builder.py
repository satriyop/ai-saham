"""
Accumulation candidate construction for the saham analyze swing workflow.

Layer: Adapter

Wires the accumulation screen use case for a single ticker/window lookup so
the top-level workflow factory does not own use-case construction directly.
"""

from __future__ import annotations

from datetime import date

from src.adapters.cli.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
)
from src.application.dto.accumulation_screen import (
    AccumulationCandidateEvaluationResult,
    AccumulationScreenRequest,
)
from src.application.dto.swing_config import SwingConfig
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
)
from src.infrastructure.config.analyze_swing_config import AnalyzeSwingConfig


def create_accumulation_candidate_builder(
    *,
    deps: StockAnalysisWorkflowDependencies,
    swing_config: SwingConfig,
    analyze_config: AnalyzeSwingConfig,
    accumulation_config: AccumulationScreenerConfig,
):
    def _build_accumulation_candidate_evaluation(
        ticker: str, window: int, as_of_date: date
    ) -> AccumulationCandidateEvaluationResult | None:
        accum_uc = create_accumulation_screen_use_case(
            broker_repository=deps.broker_repository,
            market_repository=deps.market_repository,
            indicator_registry=deps.indicator_registry_factory(),
            rules_loader=deps.rules_loader_factory(),
            stockbit_providers=deps.stockbit_providers,
            foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
            derived_feature_policy=accumulation_config.derived_features,
            ticker_profile_classifier_factory=deps.ticker_profile_classifier_factory,
            institutional_accumulation_config_factory=(
                deps.institutional_accumulation_config_factory
            ),
            sector_context_builder_factory=deps.sector_context_builder_factory,
            company_quality_context_builder_factory=(
                deps.company_quality_context_builder_factory
            ),
        )
        accum_resp = accum_uc.execute(
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
            )
        )
        # Run the screen exactly once (above) and select the surviving
        # observation candidate corresponding to accum_resp.candidates[0] —
        # never re-query or re-run the evaluator (ADR-041
        # CANONICAL-EVIDENCE-BOUNDARY). A single-ticker request always
        # produces at most one observation candidate for that ticker.
        if not accum_resp.candidates:
            return None
        selected = accum_resp.candidates[0]
        for observation in accum_resp.observation_candidates:
            if observation.candidate is selected:
                return observation.evaluation_result
        raise ValueError(
            f"Accumulation screen selected {selected.ticker!r} but no matching "
            "observation_candidates entry carries its evaluation_result — this "
            "is a screen use-case invariant violation, not a missing-data case."
        )

    return _build_accumulation_candidate_evaluation
