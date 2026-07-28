"""
Factory for fresh accumulation screen used by 'saham screen compare'.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.adapters.composition.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow,
    create_live_signal_evidence_execution_context_use_case,
)
from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.universe_loader import resolve_tickers
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository


@dataclass(frozen=True)
class FreshAccumulationScreenForCompareResult:
    """Outcome of running a fresh accumulation screen for 'saham screen compare'."""

    candidates: list
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def run_fresh_accumulation_screen_for_compare(
    *,
    universe: str,
    window: int,
    top: int,
    db_path: Path,
    screener_config,
    swing_policy,
) -> FreshAccumulationScreenForCompareResult:
    """Run the accumulation screen silently and return the top candidates.

    Used by ``saham screen compare``. Uses ``create_accumulation_screen_workflow``
    (not the persistence bundle), so this call is read-only — it never writes
    candidate observations.
    """
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=[],
            db_path=db_path,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(db_path),
        )
        if not ticker_list:
            return FreshAccumulationScreenForCompareResult(
                candidates=[],
                error=f"No tickers resolved for universe '{universe}'",
            )

        workflow = create_accumulation_screen_workflow(
            db_path=db_path,
            screener_config=screener_config,
            with_risk=False,
            swing_policy=swing_policy,
        )
        use_case = workflow.use_case

        context_use_case = create_live_signal_evidence_execution_context_use_case(
            workflow.market_repository
        )
        execution_context = context_use_case.execute(
            run_at=datetime.now(IDX_TIMEZONE),
        )

        response = use_case.execute(
            AccumulationScreenRequest(
                tickers=ticker_list,
                window_days=window,
                min_net_buy_days=1,
                min_accum_score=0.0,
                min_accum_score_enabled=False,
                tier1_broker_codes=swing_policy.tier1_broker_codes,
                bci_cluster_min_count=swing_policy.bci_cluster_min_count,
                bci_stable_min_count=swing_policy.bci_stable_min_count,
                resistance_gate_enabled=swing_policy.resistance_gate_enabled,
                resistance_headroom_min_pct=swing_policy.resistance_headroom_min_pct,
                ex_date_warning_days=swing_policy.ex_date_warning_days,
            ),
            execution_context=execution_context,
        )
        return FreshAccumulationScreenForCompareResult(candidates=response.candidates[:top])
    except Exception as exc:
        return FreshAccumulationScreenForCompareResult(
            candidates=[],
            error=f"Fresh accumulation screen failed: {type(exc).__name__}: {exc}",
        )
