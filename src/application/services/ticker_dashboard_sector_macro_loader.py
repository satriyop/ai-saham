"""
Local-only sector-macro loader for ticker dashboard (ADR-053 browse surface).

Same builder/assembler semantics as single-ticker screen accum. No network.

Layer: Application
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from src.application.services.candidate_evidence_data_loader import (
    CandidateEvidenceDataLoader,
)
from src.application.services.candidate_sector_macro_context_evidence_assembler import (
    CandidateSectorMacroContextEvidenceAssembler,
)

if TYPE_CHECKING:
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.application.services.sector_macro_context_evidence_builder import (
        SectorMacroContextEvidenceBuilder,
    )
    from src.domain.value_objects.sector_macro_context_evidence import (
        SectorMacroContextEvidence,
    )


class TickerDashboardSectorMacroLoader:
    """Build SectorMacroContextEvidence for one ticker from pre-injected deps."""

    def __init__(
        self,
        *,
        data_loader: CandidateEvidenceDataLoader,
        sector_macro_context_builder_factory: Callable[[], SectorMacroContextEvidenceBuilder],
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder],
    ) -> None:
        self._data_loader = data_loader
        self._smc_builder_factory = sector_macro_context_builder_factory
        self._sc_builder_factory = sector_context_builder_factory
        self._assembler = CandidateSectorMacroContextEvidenceAssembler()

    def __call__(self, ticker: str, as_of: date) -> SectorMacroContextEvidence | None:
        """Return evidence or None on soft failure (caller isolates exceptions too)."""
        try:
            smc_builder = self._smc_builder_factory()
            sc_builder = self._sc_builder_factory()
            sector_group = smc_builder.resolve_sector_group(
                sc_builder.sector_groups_for_ticker(ticker)
            )
            series_tickers = smc_builder.config.series_for_group(sector_group)
            policy_series = smc_builder.config.policy_series_for_group(sector_group)
            policy_lookback = smc_builder.config.max_policy_lookback_days_for_group(sector_group)
            inputs = self._data_loader.load_sector_macro_context_inputs(
                series_tickers=series_tickers,
                snapshot_date=as_of,
                policy_series=policy_series,
                policy_lookback_days=policy_lookback,
            )
            return self._assembler.assemble(
                builder=smc_builder,
                ticker=ticker,
                snapshot_date=as_of,
                sector_group=sector_group,
                inputs=inputs,
            )
        except Exception:
            return None
