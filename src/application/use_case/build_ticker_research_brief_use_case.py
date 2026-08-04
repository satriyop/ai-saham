"""Compose a PIT-aligned ticker research brief from existing read-only sources.

Authority (ADR-042): surfaces the deterministic Judge Action and engine facts
verbatim. Does **not** mint a new verdict, score, ranking, or brief conclusion.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
    build_agent_accumulation_context,
)
from src.application.services.ticker_dashboard_flow import window_buy_sell_days, window_net
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowResult,
)
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryRequest,
    ViewTickerForeignHistoryResult,
)
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersRequest,
    ViewTickerTopBrokersResult,
)
from src.domain.entities.broker_flow import BrokerTransaction, ForeignFlowPoint
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.corporate_action_calendar import CorporateActionCalendarEvent
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

_SCHEMA_ID = "application.ticker_research_brief.v1"

SECTION_JUDGE = "judge"
SECTION_BROKER_FLOW = "broker_flow"
SECTION_FOREIGN_FLOW = "foreign_flow"
SECTION_OWNERSHIP = "ownership"
SECTION_CORPORATE_ACTIONS = "corporate_actions"
SECTION_REGIME = "regime"

DEFAULT_SECTIONS: tuple[str, ...] = (
    SECTION_JUDGE,
    SECTION_BROKER_FLOW,
    SECTION_FOREIGN_FLOW,
    SECTION_OWNERSHIP,
    SECTION_CORPORATE_ACTIONS,
    SECTION_REGIME,
)
_KNOWN_SECTIONS = frozenset(DEFAULT_SECTIONS)

STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_FAILED = "FAILED"

_DEFAULT_DESK_LIMIT = 5
_MAX_DESK_LIMIT = 10
_DEFAULT_FOREIGN_DAYS = 30
_DEFAULT_CORP_WINDOW_DAYS = 90
_MAX_CORP_EVENTS = 5


class _TopBrokersUseCase(Protocol):
    def execute(
        self, request: ViewTickerTopBrokersRequest
    ) -> ViewTickerTopBrokersResult | None: ...


class _BandarCacheSource(Protocol):
    def get_bandar(self, ticker: str, session_date: date) -> BandarDetectorSnapshot | None: ...


class _ForeignHistoryUseCase(Protocol):
    def execute(
        self, request: ViewTickerForeignHistoryRequest
    ) -> ViewTickerForeignHistoryResult | None: ...


class _OwnershipCacheSource(Protocol):
    def get_ownership(self, ticker: str) -> object | None: ...


class _CorpActionSource(Protocol):
    def get_events_for_ticker(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[CorporateActionCalendarEvent]: ...


class _MarketContextReader(Protocol):
    def get(
        self,
        as_of_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> MarketContext | None: ...

    def get_recent(
        self,
        limit: int = 30,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> list[MarketContext]: ...


@dataclass(frozen=True)
class BuildTickerResearchBriefRequest:
    ticker: str
    as_of: date | None = None
    sections: tuple[str, ...] = DEFAULT_SECTIONS
    desk_limit: int = _DEFAULT_DESK_LIMIT
    foreign_days: int = _DEFAULT_FOREIGN_DAYS
    corp_window_days: int = _DEFAULT_CORP_WINDOW_DAYS


@dataclass(frozen=True)
class BriefSectionMeta:
    name: str
    status: str
    as_of: date | None = None
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class BriefJudgeFacts:
    """Surfaced deterministic Judge Action + key engine facts (not a new verdict)."""

    action: str
    as_of: date
    signal_score: int
    signal_strength: str
    blocking_gates: tuple[str, ...]
    accum_score: float
    consecutive_streak: int
    net_buy_ratio: float
    bb_width_pctile: float | None
    bci_label: str | None
    current_phase: str | None
    phase_age_sessions: int | None
    trade_setup_rationale: str


@dataclass(frozen=True)
class BriefDeskRow:
    broker_code: str
    net_value_idr: str
    avg_buy_price: str
    avg_sell_price: str


@dataclass(frozen=True)
class BriefBrokerFlowFacts:
    as_of: date
    tops_source: str | None
    top_accumulating: tuple[BriefDeskRow, ...]
    top_distributing: tuple[BriefDeskRow, ...]
    total_buyers: int | None
    total_sellers: int | None
    broker_accdist: str | None
    five_day_accdist: str | None


@dataclass(frozen=True)
class BriefForeignFlowFacts:
    as_of: date
    days: int
    cumulative_net_idr: str
    latest_net_idr: str
    net_buy_sessions: int
    active_sessions: int
    trend_direction: str
    resolved_source: str


@dataclass(frozen=True)
class BriefOwnershipFacts:
    report_date: date | None
    institution_pct: float
    individual_pct: float
    top_holder_name: str
    top_holder_pct: float
    total_shares: int | None


@dataclass(frozen=True)
class BriefCorpActionRow:
    event_type: str
    earliest_date: date | None
    amount_value: str | None
    company_name: str | None


@dataclass(frozen=True)
class BriefCorporateActionsFacts:
    as_of: date
    upcoming: tuple[BriefCorpActionRow, ...]
    upcoming_count: int


@dataclass(frozen=True)
class BriefRegimeFactor:
    name: str
    value: float | None
    label: str


@dataclass(frozen=True)
class BriefRegimeFacts:
    as_of: date
    regime: str
    conviction: float
    regime_confidence: float | None
    signal_multiplier: float
    gate_tightening: bool
    regime_stability: str | None
    days_in_regime: int | None
    cohort_id: str
    factors: tuple[BriefRegimeFactor, ...]


@dataclass(frozen=True)
class TickerResearchBriefResult:
    schema_id: str
    ticker: str
    as_of: date | None
    sections_requested: tuple[str, ...]
    overall_status: str
    warnings: tuple[str, ...]
    section_meta: tuple[BriefSectionMeta, ...]
    judge: BriefJudgeFacts | None
    broker_flow: BriefBrokerFlowFacts | None
    foreign_flow: BriefForeignFlowFacts | None
    ownership: BriefOwnershipFacts | None
    corporate_actions: BriefCorporateActionsFacts | None
    regime: BriefRegimeFacts | None


class BuildTickerResearchBriefUseCase:
    """Orchestrate read-only sub-sources into one descriptive brief bundle."""

    def __init__(
        self,
        *,
        top_brokers: _TopBrokersUseCase | None = None,
        bandar_source: _BandarCacheSource | None = None,
        foreign_history: _ForeignHistoryUseCase | None = None,
        ownership_source: _OwnershipCacheSource | None = None,
        corp_actions_source: _CorpActionSource | None = None,
        market_context_repository: _MarketContextReader | None = None,
        regime_cohort_id: str = "",
        judge_ticker: Callable[[str], RunAccumulationScreenWorkflowResult] | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._top_brokers = top_brokers
        self._bandar_source = bandar_source
        self._foreign_history = foreign_history
        self._ownership_source = ownership_source
        self._corp_actions_source = corp_actions_source
        self._market_context_repository = market_context_repository
        self._regime_cohort_id = regime_cohort_id
        self._judge_ticker = judge_ticker
        self._today = today

    def execute(self, request: BuildTickerResearchBriefRequest) -> TickerResearchBriefResult:
        ticker = request.ticker.strip().upper()
        sections = normalize_sections(request.sections)
        desk_limit = max(1, min(int(request.desk_limit), _MAX_DESK_LIMIT))
        foreign_days = max(1, min(int(request.foreign_days), 60))
        corp_window = max(1, min(int(request.corp_window_days), 365))

        metas: list[BriefSectionMeta] = []
        warnings: list[str] = []
        judge: BriefJudgeFacts | None = None
        broker_flow: BriefBrokerFlowFacts | None = None
        foreign_flow: BriefForeignFlowFacts | None = None
        ownership: BriefOwnershipFacts | None = None
        corporate_actions: BriefCorporateActionsFacts | None = None
        regime: BriefRegimeFacts | None = None
        as_of_candidates: list[date] = []

        if SECTION_JUDGE in sections:
            judge, meta = self._section_judge(ticker)
            metas.append(meta)
            warnings.extend(meta.warnings)
            if meta.error_code:
                warnings.append(f"SECTION_{SECTION_JUDGE.upper()}_{meta.status}")
            if judge is not None:
                as_of_candidates.append(judge.as_of)

        if SECTION_BROKER_FLOW in sections:
            broker_flow, meta = self._section_broker_flow(ticker, request.as_of, desk_limit)
            metas.append(meta)
            warnings.extend(meta.warnings)
            if meta.error_code:
                warnings.append(f"SECTION_{SECTION_BROKER_FLOW.upper()}_{meta.status}")
            if broker_flow is not None:
                as_of_candidates.append(broker_flow.as_of)

        if SECTION_FOREIGN_FLOW in sections:
            foreign_flow, meta = self._section_foreign_flow(ticker, foreign_days)
            metas.append(meta)
            warnings.extend(meta.warnings)
            if meta.error_code:
                warnings.append(f"SECTION_{SECTION_FOREIGN_FLOW.upper()}_{meta.status}")
            if foreign_flow is not None:
                as_of_candidates.append(foreign_flow.as_of)

        if SECTION_OWNERSHIP in sections:
            ownership, meta = self._section_ownership(ticker)
            metas.append(meta)
            warnings.extend(meta.warnings)
            if meta.error_code:
                warnings.append(f"SECTION_{SECTION_OWNERSHIP.upper()}_{meta.status}")
            if ownership is not None and ownership.report_date is not None:
                as_of_candidates.append(ownership.report_date)

        if SECTION_CORPORATE_ACTIONS in sections:
            corporate_actions, meta = self._section_corporate_actions(
                ticker, request.as_of, corp_window
            )
            metas.append(meta)
            warnings.extend(meta.warnings)
            if meta.error_code:
                warnings.append(f"SECTION_{SECTION_CORPORATE_ACTIONS.upper()}_{meta.status}")
            if corporate_actions is not None:
                as_of_candidates.append(corporate_actions.as_of)

        if SECTION_REGIME in sections:
            regime, meta = self._section_regime(request.as_of)
            metas.append(meta)
            warnings.extend(meta.warnings)
            if meta.error_code:
                warnings.append(f"SECTION_{SECTION_REGIME.upper()}_{meta.status}")
            if regime is not None:
                as_of_candidates.append(regime.as_of)

        overall = _overall_status(metas)
        uniq_warnings = tuple(dict.fromkeys(warnings))
        overall_as_of = max(as_of_candidates) if as_of_candidates else request.as_of
        return TickerResearchBriefResult(
            schema_id=_SCHEMA_ID,
            ticker=ticker,
            as_of=overall_as_of,
            sections_requested=sections,
            overall_status=overall,
            warnings=uniq_warnings,
            section_meta=tuple(metas),
            judge=judge,
            broker_flow=broker_flow,
            foreign_flow=foreign_flow,
            ownership=ownership,
            corporate_actions=corporate_actions,
            regime=regime,
        )

    def _section_judge(self, ticker: str) -> tuple[BriefJudgeFacts | None, BriefSectionMeta]:
        if self._judge_ticker is None:
            return None, BriefSectionMeta(
                name=SECTION_JUDGE,
                status=STATUS_UNAVAILABLE,
                error_code="JUDGE_NOT_WIRED",
                error_message="Accumulation judge runner is not available for this brief",
            )
        try:
            result = self._judge_ticker(ticker)
            projection = result.single_projection
            candidates = tuple(projection.candidates) if projection is not None else ()
            if not candidates:
                return None, BriefSectionMeta(
                    name=SECTION_JUDGE,
                    status=STATUS_UNAVAILABLE,
                    error_code="ACCUMULATION_JUDGMENT_UNAVAILABLE",
                    error_message="No canonical accumulation candidate for this ticker",
                )
            if len(candidates) != 1 or candidates[0].ticker != ticker:
                return None, BriefSectionMeta(
                    name=SECTION_JUDGE,
                    status=STATUS_FAILED,
                    error_code="ACCUMULATION_JUDGMENT_INVARIANT",
                    error_message="Canonical accumulation result failed identity checks",
                )
            judgment = build_agent_accumulation_context(candidates[0])
        except AgentContextUnavailableError:
            return None, BriefSectionMeta(
                name=SECTION_JUDGE,
                status=STATUS_UNAVAILABLE,
                error_code="ACCUMULATION_JUDGMENT_UNAVAILABLE",
                error_message="Full canonical accumulation judgment is unavailable",
            )
        except AgentContextInvariantError:
            return None, BriefSectionMeta(
                name=SECTION_JUDGE,
                status=STATUS_FAILED,
                error_code="ACCUMULATION_JUDGMENT_INVARIANT",
                error_message="Canonical accumulation result failed identity checks",
            )
        except Exception:
            return None, BriefSectionMeta(
                name=SECTION_JUDGE,
                status=STATUS_FAILED,
                error_code="ACCUMULATION_JUDGMENT_FAILED",
                error_message="Local accumulation judgment failed safely",
            )

        phase = judgment.setup_phase_diagnostic
        facts = BriefJudgeFacts(
            action=judgment.trade_setup.action,
            as_of=judgment.as_of,
            signal_score=judgment.trade_setup.signal_score,
            signal_strength=judgment.trade_setup.signal_strength,
            blocking_gates=judgment.trade_setup.blocking_gates,
            accum_score=judgment.accumulation.accum_score,
            consecutive_streak=judgment.accumulation.consecutive_streak,
            net_buy_ratio=judgment.accumulation.net_buy_ratio,
            bb_width_pctile=judgment.accumulation.bb_width_pctile,
            bci_label=judgment.accumulation.bci_label,
            current_phase=phase.current_phase if phase is not None else None,
            phase_age_sessions=phase.phase_age_sessions if phase is not None else None,
            trade_setup_rationale=judgment.trade_setup.rationale,
        )
        notes = tuple(dict.fromkeys((*result.warnings, *judgment.warnings)))
        status = STATUS_PARTIAL if notes else STATUS_SUCCESS
        return facts, BriefSectionMeta(
            name=SECTION_JUDGE,
            status=status,
            as_of=judgment.as_of,
            warnings=notes,
        )

    def _section_broker_flow(
        self,
        ticker: str,
        as_of: date | None,
        desk_limit: int,
    ) -> tuple[BriefBrokerFlowFacts | None, BriefSectionMeta]:
        if self._top_brokers is None and self._bandar_source is None:
            return None, BriefSectionMeta(
                name=SECTION_BROKER_FLOW,
                status=STATUS_UNAVAILABLE,
                error_code="BROKER_FLOW_NOT_WIRED",
                error_message="Broker-flow readers are not available",
            )
        try:
            tops = None
            if self._top_brokers is not None:
                tops = self._top_brokers.execute(
                    ViewTickerTopBrokersRequest(
                        ticker=ticker,
                        target_date=as_of,
                        limit=desk_limit,
                    )
                )
            bandar: BandarDetectorSnapshot | None = None
            session = tops.date if tops is not None else as_of
            if session is not None and self._bandar_source is not None:
                raw = self._bandar_source.get_bandar(ticker, session)
                if isinstance(raw, BandarDetectorSnapshot):
                    bandar = raw
        except Exception:
            return None, BriefSectionMeta(
                name=SECTION_BROKER_FLOW,
                status=STATUS_FAILED,
                error_code="BROKER_FLOW_READ_FAILED",
                error_message="Broker-flow cache could not be read",
            )

        if tops is None and bandar is None:
            return None, BriefSectionMeta(
                name=SECTION_BROKER_FLOW,
                status=STATUS_UNAVAILABLE,
                error_code="BROKER_FLOW_UNAVAILABLE",
                error_message="No cached top-broker or bandar data for this ticker",
            )

        notes: list[str] = []
        session_date = tops.date if tops is not None else bandar.session_date  # type: ignore[union-attr]
        buyers: tuple[BriefDeskRow, ...] = ()
        sellers: tuple[BriefDeskRow, ...] = ()
        tops_source = tops.tops_source if tops is not None else None
        if tops is None:
            notes.append("NAMED_TOPS_UNAVAILABLE")
        else:
            buyers = tuple(_desk_row(tx) for tx in tops.top_buyers[:desk_limit])
            sellers = tuple(_desk_row(tx) for tx in tops.top_sellers[:desk_limit])
            if not buyers and not sellers:
                notes.append("NO_NET_TOPS")
        total_buyers = total_sellers = None
        broker_accdist = five_day = None
        if bandar is None:
            notes.append("BANDAR_SNAPSHOT_UNAVAILABLE")
        else:
            total_buyers = bandar.total_buyer
            total_sellers = bandar.total_seller
            broker_accdist = bandar.broker_accdist
            five_day = bandar.five_day_accdist

        warn_codes = {
            "NAMED_TOPS_UNAVAILABLE",
            "BANDAR_SNAPSHOT_UNAVAILABLE",
        }
        status = STATUS_PARTIAL if any(n in warn_codes for n in notes) else STATUS_SUCCESS
        facts = BriefBrokerFlowFacts(
            as_of=session_date,
            tops_source=tops_source,
            top_accumulating=buyers,
            top_distributing=sellers,
            total_buyers=total_buyers,
            total_sellers=total_sellers,
            broker_accdist=broker_accdist,
            five_day_accdist=five_day,
        )
        return facts, BriefSectionMeta(
            name=SECTION_BROKER_FLOW,
            status=status,
            as_of=session_date,
            warnings=tuple(notes),
        )

    def _section_foreign_flow(
        self, ticker: str, days: int
    ) -> tuple[BriefForeignFlowFacts | None, BriefSectionMeta]:
        if self._foreign_history is None:
            return None, BriefSectionMeta(
                name=SECTION_FOREIGN_FLOW,
                status=STATUS_UNAVAILABLE,
                error_code="FOREIGN_FLOW_NOT_WIRED",
                error_message="Foreign history reader is not available",
            )
        try:
            result = self._foreign_history.execute(
                ViewTickerForeignHistoryRequest(ticker=ticker, days=days, source="auto")
            )
        except Exception:
            return None, BriefSectionMeta(
                name=SECTION_FOREIGN_FLOW,
                status=STATUS_FAILED,
                error_code="FOREIGN_FLOW_READ_FAILED",
                error_message="Foreign flow cache could not be read",
            )
        if result is None or not result.points or result.as_of is None:
            return None, BriefSectionMeta(
                name=SECTION_FOREIGN_FLOW,
                status=STATUS_UNAVAILABLE,
                error_code="FOREIGN_FLOW_UNAVAILABLE",
                error_message="No cached foreign flow points for this ticker",
            )
        points = list(result.points)
        active = len(points)
        cumulative = window_net(points, active)
        buy_days, _ = window_buy_sell_days(points, active)
        latest = points[-1]
        notes: list[str] = []
        if active < days:
            notes.append("FOREIGN_WINDOW_SHORT")
        status = STATUS_PARTIAL if notes else STATUS_SUCCESS
        facts = BriefForeignFlowFacts(
            as_of=result.as_of,
            days=active,
            cumulative_net_idr=str(cumulative if cumulative is not None else Decimal("0")),
            latest_net_idr=str(latest.net_val),
            net_buy_sessions=buy_days,
            active_sessions=active,
            trend_direction=_foreign_trend(points),
            resolved_source=result.resolved_source,
        )
        return facts, BriefSectionMeta(
            name=SECTION_FOREIGN_FLOW,
            status=status,
            as_of=result.as_of,
            warnings=tuple(notes),
        )

    def _section_ownership(
        self, ticker: str
    ) -> tuple[BriefOwnershipFacts | None, BriefSectionMeta]:
        if self._ownership_source is None:
            return None, BriefSectionMeta(
                name=SECTION_OWNERSHIP,
                status=STATUS_UNAVAILABLE,
                error_code="OWNERSHIP_NOT_WIRED",
                error_message="Ownership reader is not available",
            )
        try:
            composition = self._ownership_source.get_ownership(ticker)
        except Exception:
            return None, BriefSectionMeta(
                name=SECTION_OWNERSHIP,
                status=STATUS_FAILED,
                error_code="OWNERSHIP_READ_FAILED",
                error_message="Ownership cache could not be read",
            )
        if not isinstance(composition, ShareholdingComposition):
            return None, BriefSectionMeta(
                name=SECTION_OWNERSHIP,
                status=STATUS_UNAVAILABLE,
                error_code="OWNERSHIP_UNAVAILABLE",
                error_message="No cached ownership composition for this ticker",
            )
        notes: list[str] = []
        if not composition.top_holder_name.strip():
            notes.append("TOP_HOLDER_UNAVAILABLE")
        if composition.total_shares is None:
            notes.append("TOTAL_SHARES_UNAVAILABLE")
        if composition.report_date is None:
            notes.append("REPORT_DATE_UNAVAILABLE")
        warn = {
            "TOP_HOLDER_UNAVAILABLE",
            "TOTAL_SHARES_UNAVAILABLE",
            "REPORT_DATE_UNAVAILABLE",
        }
        status = STATUS_PARTIAL if any(n in warn for n in notes) else STATUS_SUCCESS
        facts = BriefOwnershipFacts(
            report_date=composition.report_date,
            institution_pct=composition.institution_pct,
            individual_pct=composition.individual_pct,
            top_holder_name=composition.top_holder_name,
            top_holder_pct=composition.top_holder_pct,
            total_shares=composition.total_shares,
        )
        return facts, BriefSectionMeta(
            name=SECTION_OWNERSHIP,
            status=status,
            as_of=composition.report_date,
            warnings=tuple(notes),
        )

    def _section_corporate_actions(
        self,
        ticker: str,
        as_of: date | None,
        window_days: int,
    ) -> tuple[BriefCorporateActionsFacts | None, BriefSectionMeta]:
        if self._corp_actions_source is None:
            return None, BriefSectionMeta(
                name=SECTION_CORPORATE_ACTIONS,
                status=STATUS_UNAVAILABLE,
                error_code="CORP_ACTIONS_NOT_WIRED",
                error_message="Corporate-action calendar reader is not available",
            )
        pivot = as_of or self._today()
        from_date = pivot - timedelta(days=window_days)
        to_date = pivot + timedelta(days=window_days)
        try:
            events = self._corp_actions_source.get_events_for_ticker(ticker, from_date, to_date)
        except Exception:
            return None, BriefSectionMeta(
                name=SECTION_CORPORATE_ACTIONS,
                status=STATUS_FAILED,
                error_code="CORP_ACTIONS_READ_FAILED",
                error_message="Corporate-action calendar could not be read",
            )

        upcoming_rows: list[BriefCorpActionRow] = []
        for event in events:
            earliest = _earliest_event_date(event)
            if earliest is None:
                continue
            if earliest >= pivot:
                upcoming_rows.append(
                    BriefCorpActionRow(
                        event_type=event.event_type.value,
                        earliest_date=earliest,
                        amount_value=event.amount_value,
                        company_name=event.company_name,
                    )
                )
        upcoming_rows.sort(key=lambda r: r.earliest_date or pivot)
        capped = tuple(upcoming_rows[:_MAX_CORP_EVENTS])
        notes: list[str] = []
        if not events:
            # Empty calendar is a true finding for this ticker/window.
            notes.append("NO_CORP_ACTIONS_IN_WINDOW")
        facts = BriefCorporateActionsFacts(
            as_of=pivot,
            upcoming=capped,
            upcoming_count=len(upcoming_rows),
        )
        return facts, BriefSectionMeta(
            name=SECTION_CORPORATE_ACTIONS,
            status=STATUS_SUCCESS,
            as_of=pivot,
            warnings=tuple(notes),
        )

    def _section_regime(
        self, as_of: date | None
    ) -> tuple[BriefRegimeFacts | None, BriefSectionMeta]:
        if self._market_context_repository is None or not self._regime_cohort_id:
            return None, BriefSectionMeta(
                name=SECTION_REGIME,
                status=STATUS_UNAVAILABLE,
                error_code="REGIME_NOT_WIRED",
                error_message="Market regime snapshot reader is not available",
            )
        try:
            if as_of is not None:
                if as_of > self._today():
                    return None, BriefSectionMeta(
                        name=SECTION_REGIME,
                        status=STATUS_UNAVAILABLE,
                        error_code="AS_OF_IN_FUTURE",
                        error_message="Requested as_of is in the future",
                    )
                snap = self._market_context_repository.get(
                    as_of,
                    semantic_compatibility_id=self._regime_cohort_id,
                )
            else:
                recent = self._market_context_repository.get_recent(
                    1,
                    semantic_compatibility_id=self._regime_cohort_id,
                )
                snap = recent[0] if recent else None
        except Exception:
            return None, BriefSectionMeta(
                name=SECTION_REGIME,
                status=STATUS_FAILED,
                error_code="REGIME_READ_FAILED",
                error_message="Market context snapshot could not be read",
            )
        if snap is None:
            return None, BriefSectionMeta(
                name=SECTION_REGIME,
                status=STATUS_UNAVAILABLE,
                error_code="REGIME_UNAVAILABLE",
                error_message="No stored market context snapshot for the canonical cohort",
            )
        notes: list[str] = []
        if snap.staleness_warning:
            notes.append("MARKET_CONTEXT_STALE")
        if snap.coverage_warning:
            notes.append("MARKET_CONTEXT_COVERAGE")
        missing = any(
            f.enabled and (f.value is None or f.label == "UNAVAILABLE") for f in snap.factors
        )
        if missing:
            notes.append("FACTOR_DATA_UNAVAILABLE")
        status = STATUS_PARTIAL if notes else STATUS_SUCCESS
        factors = tuple(
            BriefRegimeFactor(name=f.name, value=f.value, label=f.label) for f in snap.factors
        )
        facts = BriefRegimeFacts(
            as_of=snap.as_of_date,
            regime=snap.regime.value,
            conviction=snap.conviction,
            regime_confidence=snap.regime_confidence,
            signal_multiplier=snap.signal_multiplier,
            gate_tightening=snap.gate_tightening,
            regime_stability=snap.regime_stability,
            days_in_regime=snap.days_in_regime,
            cohort_id=self._regime_cohort_id,
            factors=factors,
        )
        return facts, BriefSectionMeta(
            name=SECTION_REGIME,
            status=status,
            as_of=snap.as_of_date,
            warnings=tuple(notes),
        )


def normalize_sections(sections: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not sections:
        return DEFAULT_SECTIONS
    out: list[str] = []
    for raw in sections:
        name = raw.strip().lower()
        if not name:
            continue
        if name not in _KNOWN_SECTIONS:
            raise ValueError(
                f"unknown brief section {raw!r}; expected one of {sorted(_KNOWN_SECTIONS)}"
            )
        if name not in out:
            out.append(name)
    if not out:
        return DEFAULT_SECTIONS
    # Preserve canonical order for requested subset
    return tuple(s for s in DEFAULT_SECTIONS if s in out)


def parse_sections_csv(raw: str) -> tuple[str, ...]:
    text = raw.strip()
    if not text:
        return DEFAULT_SECTIONS
    parts = tuple(p.strip() for p in text.split(",") if p.strip())
    return normalize_sections(parts)


def _overall_status(metas: list[BriefSectionMeta]) -> str:
    if not metas:
        return STATUS_UNAVAILABLE
    statuses = {m.status for m in metas}
    if statuses == {STATUS_SUCCESS}:
        return STATUS_SUCCESS
    if STATUS_FAILED in statuses and all(
        m.status in {STATUS_FAILED, STATUS_UNAVAILABLE} for m in metas
    ):
        # Prefer PARTIAL when the brief still has structure; only all-hard-fail
        # without any success/partial data still returns PARTIAL for honesty.
        return STATUS_PARTIAL
    if all(m.status == STATUS_UNAVAILABLE for m in metas):
        return STATUS_PARTIAL
    return STATUS_PARTIAL


def _desk_row(tx: BrokerTransaction) -> BriefDeskRow:
    return BriefDeskRow(
        broker_code=tx.broker_code,
        net_value_idr=str(tx.net_value),
        avg_buy_price=str(tx.avg_buy_price),
        avg_sell_price=str(tx.avg_sell_price),
    )


def _foreign_trend(points: list[ForeignFlowPoint]) -> str:
    n = len(points)
    if n < 2:
        return "flat"
    mid = n // 2
    first = sum((p.net_val for p in points[:mid]), Decimal("0"))
    second = sum((p.net_val for p in points[mid:]), Decimal("0"))
    if second > first:
        return "rising"
    if second < first:
        return "falling"
    return "flat"


def _earliest_event_date(event: CorporateActionCalendarEvent) -> date | None:
    if not event.dates:
        return None
    return min(d.event_date for d in event.dates)
