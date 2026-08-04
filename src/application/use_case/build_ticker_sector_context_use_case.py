"""Build descriptive ticker sector context (L2a peers + L2b macro) cache-only.

Shared by agent tool / future CLI-TUI adapters. Reuses ADR-053 builders and
assemblers but exposes facts only (no composite_score / factor scores).

Layer: Application
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from src.application.services.candidate_evidence_data_loader import (
    CandidateEvidenceDataLoader,
)
from src.application.services.candidate_sector_context_evidence_assembler import (
    CandidateSectorContextEvidenceAssembler,
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
    from src.domain.ports.market_data_repository import MarketDataRepository

_DEFAULT_PEERS_LIMIT = 10
_MAX_PEERS_LIMIT = 10
_DEFAULT_BENCHMARK = "IHSG"

_WARN_PEER_UNAVAILABLE = "SECTOR_PEER_CONTEXT_UNAVAILABLE"
_WARN_MACRO_UNAVAILABLE = "SECTOR_MACRO_CONTEXT_UNAVAILABLE"
_WARN_PEERS_THIN = "SECTOR_PEERS_THIN"


@dataclass(frozen=True)
class BuildTickerSectorContextRequest:
    ticker: str
    as_of: date | None = None
    peers_limit: int = _DEFAULT_PEERS_LIMIT
    benchmark: str = _DEFAULT_BENCHMARK


@dataclass(frozen=True)
class SectorPeerContextFacts:
    """L2a descriptive peer-relative sector readings (no coverage_score)."""

    sector_label: str | None
    peer_count: int
    peer_tickers: tuple[str, ...]
    sector_20d_return: float | None
    sector_vs_ihsg_20d: float | None
    sector_breadth: float | None
    ticker_vs_sector_rs: float | None
    sector_regime: str


@dataclass(frozen=True)
class SectorMacroFactorFact:
    """Single macro factor as facts (value/label/rationale — no score)."""

    name: str
    series: str
    value: float | None
    label: str
    rationale: str


@dataclass(frozen=True)
class SectorMacroContextFacts:
    """L2b descriptive routed macro readings (no composite_score)."""

    sector_group: str | None
    macro_regime: str
    factors: tuple[SectorMacroFactorFact, ...]


@dataclass(frozen=True)
class TickerSectorContextResult:
    ticker: str
    as_of: date
    sector_group: str | None
    peer_context: SectorPeerContextFacts | None
    macro_context: SectorMacroContextFacts | None
    warnings: tuple[str, ...]


class BuildTickerSectorContextUseCase:
    """Cache-only L2a + L2b sector context for one ticker."""

    def __init__(
        self,
        data_loader: CandidateEvidenceDataLoader,
        *,
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder],
        sector_macro_context_builder_factory: Callable[[], SectorMacroContextEvidenceBuilder],
        market_repository: MarketDataRepository | None = None,
    ) -> None:
        self._data_loader = data_loader
        self._sc_factory = sector_context_builder_factory
        self._smc_factory = sector_macro_context_builder_factory
        self._market_repo = market_repository
        self._sc_assembler = CandidateSectorContextEvidenceAssembler()
        self._smc_assembler = CandidateSectorMacroContextEvidenceAssembler()

    def execute(self, request: BuildTickerSectorContextRequest) -> TickerSectorContextResult | None:
        ticker = request.ticker.upper().strip()
        peers_limit = max(1, min(int(request.peers_limit), _MAX_PEERS_LIMIT))
        as_of = request.as_of or self._resolve_as_of(ticker)
        if as_of is None:
            return None

        warnings: list[str] = []
        sector_group: str | None = None
        peer_facts: SectorPeerContextFacts | None = None
        macro_facts: SectorMacroContextFacts | None = None

        try:
            sc_builder = self._sc_factory()
            groups = sc_builder.sector_groups_for_ticker(ticker)
            sector_group = groups[0] if groups else None
            peer_tickers = sc_builder.peers_for_ticker(ticker)[:peers_limit]
            sector_inputs = self._data_loader.load_sector_context_inputs(
                ticker=ticker,
                snapshot_date=as_of,
                sector=sector_group,
                peer_tickers=peer_tickers,
                benchmark=request.benchmark or _DEFAULT_BENCHMARK,
            )
            peer_ev = self._sc_assembler.assemble(
                builder=sc_builder,
                ticker=ticker,
                snapshot_date=as_of,
                sector=sector_group,
                inputs=sector_inputs,
            )
            if peer_ev.unavailable_reasons and peer_ev.peer_count == 0:
                warnings.append(_WARN_PEER_UNAVAILABLE)
            else:
                shown_peers = tuple(peer_ev.peer_tickers[:peers_limit])
                peer_facts = SectorPeerContextFacts(
                    sector_label=peer_ev.sector or sector_group,
                    peer_count=min(peer_ev.peer_count, peers_limit),
                    peer_tickers=shown_peers,
                    sector_20d_return=peer_ev.sector_20d_return,
                    sector_vs_ihsg_20d=peer_ev.sector_vs_ihsg_20d,
                    sector_breadth=peer_ev.sector_breadth,
                    ticker_vs_sector_rs=peer_ev.ticker_vs_sector_rs,
                    sector_regime=peer_ev.sector_regime,
                )
                if peer_facts.peer_count == 0:
                    warnings.append(_WARN_PEERS_THIN)
        except Exception:
            warnings.append(_WARN_PEER_UNAVAILABLE)

        try:
            smc_builder = self._smc_factory()
            sc_for_groups = self._sc_factory()
            resolved_group = smc_builder.resolve_sector_group(
                sc_for_groups.sector_groups_for_ticker(ticker)
            )
            if resolved_group is not None:
                sector_group = sector_group or resolved_group
            series_tickers = smc_builder.config.series_for_group(resolved_group)
            policy_series = smc_builder.config.policy_series_for_group(resolved_group)
            policy_lookback = smc_builder.config.max_policy_lookback_days_for_group(resolved_group)
            smc_inputs = self._data_loader.load_sector_macro_context_inputs(
                series_tickers=series_tickers,
                snapshot_date=as_of,
                policy_series=policy_series,
                policy_lookback_days=policy_lookback,
            )
            macro_ev = self._smc_assembler.assemble(
                builder=smc_builder,
                ticker=ticker,
                snapshot_date=as_of,
                sector_group=resolved_group,
                inputs=smc_inputs,
            )
            if macro_ev.unavailable_reasons and not macro_ev.factors:
                warnings.append(_WARN_MACRO_UNAVAILABLE)
            else:
                macro_facts = SectorMacroContextFacts(
                    sector_group=macro_ev.sector_group or resolved_group,
                    macro_regime=macro_ev.macro_regime,
                    factors=tuple(
                        SectorMacroFactorFact(
                            name=f.name,
                            series=f.series,
                            value=f.value,
                            label=f.label,
                            rationale=f.rationale,
                        )
                        for f in macro_ev.factors
                    ),
                )
                if not macro_facts.factors:
                    warnings.append(_WARN_MACRO_UNAVAILABLE)
                    macro_facts = None
        except Exception:
            warnings.append(_WARN_MACRO_UNAVAILABLE)

        if peer_facts is None and macro_facts is None:
            return None

        return TickerSectorContextResult(
            ticker=ticker,
            as_of=as_of,
            sector_group=sector_group,
            peer_context=peer_facts,
            macro_context=macro_facts,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _resolve_as_of(self, ticker: str) -> date | None:
        if self._market_repo is None:
            return date.today()
        try:
            candles = self._market_repo.get_candles(ticker)
            if not candles:
                return None
            return candles[-1].date
        except Exception:
            return None
