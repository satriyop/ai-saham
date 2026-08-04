"""Deterministic offline runner for the ADR-068 behavioural probe set.

Layer: Application

Drives the frozen probe set from ``behavioral_probe_set`` through the **real
production accum decision path** and projects each probe's canonical output —
ordering, inclusion/exclusion, Accum score, Signal score, Risk gate, Action,
setup phase and readiness. The digest over ``{probe_id -> projection}`` is the
behavioural identity candidate described in ADR-068 §2.

What is real here, and what is not
----------------------------------

Real production classes, unchanged and undecorated:

- ``AccumulationScreenUseCase`` and every collaborator it builds internally
  (evaluator, structural filter, enricher, signal assessor, evidence builder,
  ``ScreenAssessmentPipeline``, ``AccumulationRiskFunnel``)
- ``SignalEngine`` with its code-default ``SignalEngineConfig``
- ``ScoreAccumUseCase`` with its code-default ``AccumScorePolicy``
- ``AssessRiskUseCase`` with the gates produced by the production resolver
  ``resolve_risk_gates`` — a pure dict-to-gates function, called with an empty
  mapping so every gate takes its in-code default threshold
- ``AssessTradeSetupUseCase`` action derivation and the production sort key

Substituted at the port boundary only, and only with frozen in-memory data:

- ``MarketDataRepository`` / ``BrokerDataRepository``
- ``FundamentalsProvider`` / ``ShareholdingProvider`` / ``BandarDetectorProvider``
- ``RulesLoader`` (never invoked — probes set no ``strategy_name``)

Why config values are not read from disk
----------------------------------------

ADR-068 §1 splits identity into three orthogonal parts. The probe digest owns
the *code* axis; declared policy resolved from YAML owns the *snapshot payload
digest* axis. Reading ``config/*.yaml`` here would both violate the no-IO
precondition (§4) and duplicate the snapshot axis. Every typed policy the
runner builds therefore uses its in-code default, so changing a default
constant moves the probe digest while a YAML edit moves the snapshot digest.

Determinism preconditions (ADR-068 §4): no clock, network, database, or
filesystem access, and no iteration-order dependence. Every probe supplies its
own ``as_of_date``, so the ``date.today()`` fallback inside
``AccumulationScreenUseCase.execute`` is never reachable.

This module computes and returns a digest. Wiring it into cohort identity is
deliberately **not** done here — see ADR-068 §7 trust ordering and slices 3-4
of the implementation task.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
    AccumulationScreenResponse,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.ports.rules_loader import RulesLoader
from src.application.rules.schema import RuleSet
from src.application.services.behavioral_probe_set import (
    CORE_PROBE_SET_ID,
    BehavioralProbe,
    ProbeTicker,
    build_probe_broker_summaries,
    build_probe_candles,
    build_probe_daily_flows,
    core_probe_set,
    probe_sessions,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    CoiledSpringSetupConfig,
    ForeignBounceSetupConfig,
    PullbackContinuationSetupConfig,
    SmartMoneyConfirmedSetupConfig,
    SwingSetupCatalogConfig,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.shareholding_provider import ShareholdingProvider
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

# Version of the projection shape itself. A change here alters the digest for
# reasons unrelated to engine behaviour, so it is a deliberate cohort boundary.
PROBE_PROJECTION_CONTRACT = "accum_behavioral_projection.v1"

# Fixed decimal places for every projected float. Guards the digest against
# last-bit float noise while staying far more precise than any threshold in
# the accum decision path.
_FLOAT_PRECISION = 6

# Frozen session envelope. Supplied so no resolver ever consults a clock.
_PROBE_RUN_AT = datetime(2026, 6, 19, 16, 30)
_PROBE_DECISION_AT = datetime(2026, 6, 19, 16, 30)

# Frozen swing setup catalog for probes that declare
# ``swing_setup_families_enabled``. Every gate threshold stays at its in-code
# default; only the entry-authority metadata is stated explicitly, because the
# in-code default for ``family`` is the sentinel ``"unknown"`` which the family
# resolver discards, leaving setup readiness structurally unreachable.
#
# The values mirror what ``config/swing_setups.yaml`` declares today. They are
# frozen **probe input**, not a config read: this module performs no IO, and the
# declared-policy axis of identity belongs to the ADR-059 snapshot digest, not
# to the probe digest (ADR-068 §1). No core probe enables the catalog, so this
# constant cannot move cohort identity.
_PROBE_SWING_SETUP_CATALOG = SwingSetupCatalogConfig(
    foreign_bounce=ForeignBounceSetupConfig(
        family="accumulation",
        entry_authority=True,
        can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    ),
    coiled_spring=CoiledSpringSetupConfig(
        family="breakout",
        entry_authority=True,
        can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    ),
    smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
        family="confirmation",
        entry_authority=False,
        can_enter_from_phases=(),
    ),
    pullback_continuation=PullbackContinuationSetupConfig(
        family="pullback",
        entry_authority=True,
        can_enter_from_phases=("BREAKOUT_CONFIRMATION",),
    ),
)


class ProbeIOForbiddenError(RuntimeError):
    """Raised when a probe run attempts a write or an unsupported read.

    A probe must never persist, and must never reach a code path the frozen
    in-memory fixture cannot answer. Both are contract violations, not missing
    data, so they fail closed rather than degrading to ``None``.
    """


# ── Frozen in-memory ports ──────────────────────────────────────────────────


class FrozenProbeMarketRepository(MarketDataRepository):
    """Serves frozen candles from memory. Every write fails closed."""

    def __init__(self, candles: tuple[Candle, ...]) -> None:
        self._by_ticker: dict[str, tuple[Candle, ...]] = {}
        for candle in candles:
            self._by_ticker.setdefault(candle.ticker, ())
        for ticker in self._by_ticker:
            self._by_ticker[ticker] = tuple(
                sorted((c for c in candles if c.ticker == ticker), key=lambda c: c.date)
            )

    def save_candles(self, candles: list[Candle]) -> None:
        raise ProbeIOForbiddenError("probe run attempted to persist candles")

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        rows = list(self._by_ticker.get(ticker.upper(), ()))
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return rows

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        span = self.get_date_range(ticker)
        return bool(span and span[0] <= start_date and span[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self._by_ticker.get(ticker.upper(), ())
        return (rows[0].date, rows[-1].date) if rows else None

    def list_tickers_with_candles_between(self, start_date: date, end_date: date) -> list[str]:
        return sorted(
            ticker
            for ticker, rows in self._by_ticker.items()
            if any(start_date <= c.date <= end_date for c in rows)
        )


class FrozenProbeBrokerRepository(BrokerDataRepository):
    """Serves frozen broker summaries/daily flows. Every write fails closed."""

    def __init__(
        self,
        summaries: tuple[BrokerSummary, ...],
        daily_flows: tuple[BrokerDailyFlow, ...],
    ) -> None:
        self._summaries = tuple(sorted(summaries, key=lambda s: (s.ticker, s.date)))
        self._daily_flows = tuple(
            sorted(daily_flows, key=lambda f: (f.ticker, f.date, f.broker_code))
        )

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        raise ProbeIOForbiddenError("probe run attempted to persist a broker summary")

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        raise ProbeIOForbiddenError("probe run attempted to persist broker summaries")

    def save_broker_daily_flows(self, flows: list[BrokerDailyFlow]) -> None:
        raise ProbeIOForbiddenError("probe run attempted to persist broker daily flows")

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        for summary in self._summaries:
            if summary.ticker == ticker.upper() and summary.date == target_date:
                return summary
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[BrokerSummary]:
        rows = [s for s in self._summaries if s.ticker == ticker.upper()]
        if start_date is not None:
            rows = [s for s in rows if s.date >= start_date]
        if end_date is not None:
            rows = [s for s in rows if s.date <= end_date]
        return sorted(rows, key=lambda s: s.date)

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        source: str | None = None,
    ) -> bool:
        span = self.get_date_range(ticker)
        return bool(span and span[0] <= start_date and span[1] >= end_date)

    def get_date_range(self, ticker: str, source: str | None = None) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        return (rows[0].date, rows[-1].date) if rows else None

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        broker_codes: list[str] | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        rows = [f for f in self._daily_flows if f.ticker == ticker.upper()]
        if start_date is not None:
            rows = [f for f in rows if f.date >= start_date]
        if end_date is not None:
            rows = [f for f in rows if f.date <= end_date]
        if broker_codes:
            allowed = set(broker_codes)
            rows = [f for f in rows if f.broker_code in allowed]
        return sorted(rows, key=lambda f: (f.date, f.broker_code))


class FrozenProbeFundamentalsProvider(FundamentalsProvider):
    """Returns frozen fundamentals, or ``None`` when the probe declares none."""

    def __init__(self, by_ticker: dict[str, CompanyFundamentals]) -> None:
        self._by_ticker = dict(by_ticker)

    def get_fundamentals(
        self, ticker: str, as_of_date: date | None = None
    ) -> CompanyFundamentals | None:
        return self._by_ticker.get(ticker.upper())


class FrozenProbeShareholdingProvider(ShareholdingProvider):
    """Returns frozen shareholding, or ``None`` when the probe declares none."""

    def __init__(self, by_ticker: dict[str, ShareholdingComposition]) -> None:
        self._by_ticker = dict(by_ticker)

    def get_composition(
        self, ticker: str, as_of_date: date | None = None
    ) -> ShareholdingComposition | None:
        return self._by_ticker.get(ticker.upper())

    def get_history(
        self, ticker: str, limit: int, as_of_date: date | None = None
    ) -> tuple[ShareholdingComposition, ...]:
        row = self._by_ticker.get(ticker.upper())
        return (row,) if row is not None and limit > 0 else ()


class FrozenProbeBandarProvider(BandarDetectorProvider):
    """Returns a frozen bandar snapshot, or ``None`` when none is declared."""

    def __init__(self, by_ticker: dict[str, BandarDetectorSnapshot]) -> None:
        self._by_ticker = dict(by_ticker)

    def get_snapshot(
        self, ticker: str, session_date: date | None = None
    ) -> BandarDetectorSnapshot | None:
        return self._by_ticker.get(ticker.upper())


class ProbeRulesLoader(RulesLoader):
    """Fails closed. Probes never set ``strategy_name``, so this is unreachable."""

    def load(self, path: Path | str | None = None, registry: Any = None) -> RuleSet:
        raise ProbeIOForbiddenError("probe run attempted to load a rules file")

    def load_from_string(
        self, content: str, registry: Any = None, source_name: str = "<generated>"
    ) -> RuleSet:
        raise ProbeIOForbiddenError("probe run attempted to parse rules")


# ── Probe execution ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProbeRunResult:
    """One probe's identity-material projection plus its executed request."""

    probe_id: str
    request: AccumulationScreenRequest
    projection: dict[str, Any]


def _market_context(probe: BehavioralProbe) -> MarketContext | None:
    if probe.regime is None:
        return None
    return MarketContext(
        regime=MarketRegime(probe.regime),
        conviction=probe.regime_conviction,
        factors=(),
        signal_multiplier=probe.regime_signal_multiplier,
        gate_tightening=probe.regime_gate_tightening,
        as_of_date=probe.as_of_date,
    )


def _probe_session_calendar(probe: BehavioralProbe) -> KnownTradingSessionCalendar:
    """Build a proven session calendar from the probe's own frozen sessions.

    Pure in-memory construction over the widest candle span the probe
    declares — never an exchange calendar lookup, file, or database read.
    """
    span = max((spec.candle_sessions for spec in probe.tickers), default=0)
    span = max(span, max((spec.broker_sessions for spec in probe.tickers), default=0), 1)
    sessions = probe_sessions(end_date=probe.as_of_date, count=span)
    return KnownTradingSessionCalendar(
        sessions=sessions,
        coverage_start=sessions[0],
        coverage_end=sessions[-1],
    )


def _execution_context(probe: BehavioralProbe) -> SignalEvidenceExecutionContext:
    availability_use_case = (
        AssessSourceAvailabilityUseCase(calendar=_probe_session_calendar(probe))
        if probe.source_availability_enabled
        else None
    )
    return SignalEvidenceExecutionContext(
        effective_session=EffectiveMarketSession(
            run_at=_PROBE_RUN_AT,
            decision_at=_PROBE_DECISION_AT,
            latest_completed_session=probe.as_of_date,
            analysis_as_of=probe.as_of_date,
            market_session_name="AFTER_CLOSE",
            is_eod_pending=False,
            resolution_source="behavioral_probe",
        ),
        source_availability_use_case=availability_use_case,
    )


def build_probe_request(probe: BehavioralProbe) -> AccumulationScreenRequest:
    """Build the exact screen request one probe executes.

    ``as_of_date`` is always populated so the use case's ``date.today()``
    fallback is unreachable (ADR-068 §4).
    """
    return AccumulationScreenRequest(
        tickers=[spec.ticker for spec in probe.tickers],
        window_days=probe.window_days,
        min_net_buy_days=probe.min_net_buy_days,
        min_accum_score=probe.min_accum_score,
        min_accum_score_enabled=probe.min_accum_score_enabled,
        min_signal_score=probe.min_signal_score,
        min_signal_score_enabled=probe.min_signal_score_enabled,
        rsi_period=probe.rsi_period,
        sma_period=probe.sma_period,
        as_of_date=probe.as_of_date,
        resistance_gate_enabled=probe.resistance_gate_enabled,
        resistance_headroom_min_pct=probe.resistance_headroom_min_pct,
        min_market_cap_idr=probe.min_market_cap_idr,
        min_piotroski=probe.min_piotroski,
        market_context=_market_context(probe),
    )


def _expand_universe(
    probe: BehavioralProbe,
) -> tuple[
    tuple[Candle, ...],
    tuple[BrokerSummary, ...],
    tuple[BrokerDailyFlow, ...],
    dict[str, CompanyFundamentals],
    dict[str, ShareholdingComposition],
    dict[str, BandarDetectorSnapshot],
]:
    candles: list[Candle] = []
    summaries: list[BrokerSummary] = []
    flows: list[BrokerDailyFlow] = []
    fundamentals: dict[str, CompanyFundamentals] = {}
    shareholding: dict[str, ShareholdingComposition] = {}
    bandar: dict[str, BandarDetectorSnapshot] = {}

    spec: ProbeTicker
    for spec in probe.tickers:
        candles.extend(build_probe_candles(spec, as_of_date=probe.as_of_date))
        summaries.extend(build_probe_broker_summaries(spec, as_of_date=probe.as_of_date))
        flows.extend(build_probe_daily_flows(spec, as_of_date=probe.as_of_date))
        if not probe.enrichment_providers_enabled:
            continue
        if spec.fundamentals is not None:
            fundamentals[spec.ticker] = spec.fundamentals.to_value_object(spec.ticker)
        if spec.shareholding is not None:
            shareholding[spec.ticker] = spec.shareholding.to_value_object(spec.ticker)
        if spec.bandar is not None:
            bandar[spec.ticker] = spec.bandar.to_value_object(spec.ticker, probe.as_of_date)

    return (
        tuple(candles),
        tuple(summaries),
        tuple(flows),
        fundamentals,
        shareholding,
        bandar,
    )


def build_probe_screen_use_case(probe: BehavioralProbe) -> AccumulationScreenUseCase:
    """Assemble the real accum screen use case over one probe's frozen universe.

    Only repositories and enrichment providers are substituted. Every scoring,
    gate, setup-phase, signal, risk, and action component is the production
    class with its in-code default policy.
    """
    candles, summaries, flows, fundamentals, shareholding, bandar = _expand_universe(probe)

    market_repository = FrozenProbeMarketRepository(candles)
    broker_repository = FrozenProbeBrokerRepository(summaries, flows)

    # Production gate resolver, called with an empty mapping so every gate keeps
    # its in-code default. Pure function of the dict — reads no file.
    structural_gates, execution_gates = resolve_risk_gates({})
    risk_use_case = AssessRiskUseCase(
        repository=market_repository,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
    )

    return AccumulationScreenUseCase(
        broker_repository=broker_repository,
        market_repository=market_repository,
        fundamentals_provider=(
            FrozenProbeFundamentalsProvider(fundamentals)
            if probe.enrichment_providers_enabled
            else None
        ),
        shareholding_provider=(
            FrozenProbeShareholdingProvider(shareholding)
            if probe.enrichment_providers_enabled
            else None
        ),
        bandar_detector_provider=(
            FrozenProbeBandarProvider(bandar) if probe.enrichment_providers_enabled else None
        ),
        risk_use_case=risk_use_case,
        candidate_observations_repository=None,
        setup_phase_history_repository=None,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
        indicator_registry=IndicatorRegistry(),
        rules_loader=ProbeRulesLoader(),
        swing_setup_catalog=(
            _PROBE_SWING_SETUP_CATALOG if probe.swing_setup_families_enabled else None
        ),
    )


# ── Canonical output projection ─────────────────────────────────────────────


def _num(value: float | Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), _FLOAT_PRECISION)


def _project_candidate(candidate: Any) -> dict[str, Any]:
    """Project one candidate's canonical decision output.

    Deliberately excludes diagnostic-only enrichment (seasonality, analyst,
    notation) and anything that is not part of the Accum / Signal / Risk /
    Action / readiness decision surface named in ADR-068 §2.
    """
    signal_response = candidate.signal_assessment
    assessment = signal_response.assessment if signal_response is not None else None
    constraints = assessment.decision_constraints if assessment is not None else None
    readiness = signal_response.setup_readiness if signal_response is not None else None
    breakdown = candidate.accum_score_breakdown
    phase = candidate.setup_phase
    risk = candidate.risk_assessment
    setup = candidate.trade_setup
    family_result = candidate.setup_family_result

    return {
        "accum_score": _num(candidate.accum_score),
        "accum_components": (
            {
                component.key: {
                    "score_points": _num(component.score_points),
                    "max_points": _num(component.max_points),
                    "status": component.status.value,
                }
                for component in breakdown.components
            }
            if breakdown is not None
            else None
        ),
        "bci_label": candidate.bci_label,
        "bci_tier1_count": candidate.bci_tier1_count,
        "trend": candidate.trend,
        "signal_score": assessment.score if assessment is not None else None,
        "signal_score_raw_exact": (
            _num(assessment.raw_exact_score) if assessment is not None else None
        ),
        "signal_strength": assessment.strength.value if assessment is not None else None,
        "entry_quality": assessment.entry_quality.value if assessment is not None else None,
        "signal_authority_coverage": (
            _num(assessment.signal_authority_coverage) if assessment is not None else None
        ),
        "signal_breakdown": (
            {key: _num(score) for key, score in assessment.breakdown} if assessment else None
        ),
        "decision_constraints": (
            {
                "max_decision": constraints.max_decision,
                "regime": constraints.regime,
                "regime_enter_allowed": constraints.regime_enter_allowed,
                "regime_size_multiplier": _num(constraints.regime_size_multiplier),
                "setup_family": constraints.setup_family,
                "setup_regime_action": constraints.setup_regime_action,
                "effective_size_multiplier": _num(constraints.effective_size_multiplier),
            }
            if constraints is not None
            else None
        ),
        "setup_family": (family_result.primary_setup_family if family_result is not None else None),
        "setup_phase": phase.current_phase.value if phase is not None else None,
        "setup_phase_sequence_valid": phase.sequence_valid if phase is not None else None,
        "setup_phase_age_sessions": phase.phase_age_sessions if phase is not None else None,
        "setup_readiness": readiness.status.value if readiness is not None else None,
        "setup_readiness_family": readiness.setup_family if readiness is not None else None,
        "risk_gate_triggered": risk.gate_triggered if risk is not None else None,
        "risk_gate_is_structural": risk.gate_is_structural if risk is not None else None,
        "risk_gate_confidence": risk.gate_confidence if risk is not None else None,
        "risk_gate_evaluations": (
            [
                {
                    "gate": record.gate,
                    "tier": str(record.tier),
                    "order": record.order,
                    "evaluated": record.evaluated,
                    "outcome": str(record.outcome),
                    "triggered": record.triggered,
                    "confidence": record.confidence,
                }
                for record in candidate.risk_gate_evaluations
            ]
            if candidate.risk_gate_evaluations
            else None
        ),
        "action": setup.action.value if setup is not None else None,
        "blocking_gates": list(setup.blocking_gates) if setup is not None else None,
    }


def project_probe_response(
    probe: BehavioralProbe,
    response: AccumulationScreenResponse,
) -> dict[str, Any]:
    """Build the canonical output projection for one executed probe."""
    evaluated_order = [
        observation.evaluation_result.candidate.ticker
        for observation in response.observation_candidates
    ]
    requested = [spec.ticker for spec in probe.tickers]
    return {
        "included_order": [candidate.ticker for candidate in response.candidates],
        "evaluated_order": evaluated_order,
        "not_evaluated": [t for t in requested if t not in set(evaluated_order)],
        "screen_results": {
            observation.evaluation_result.candidate.ticker: observation.screen_result
            for observation in response.observation_candidates
        },
        "tickers_skipped": response.tickers_skipped,
        "total_tickers_checked": response.total_tickers_checked,
        "provider": response.provider,
        "window_days": response.window_days,
        "candidates": {
            observation.evaluation_result.candidate.ticker: _project_candidate(
                observation.evaluation_result.candidate
            )
            for observation in response.observation_candidates
        },
    }


def run_probe(probe: BehavioralProbe) -> ProbeRunResult:
    """Execute one probe through the real accum decision path."""
    use_case = build_probe_screen_use_case(probe)
    request = build_probe_request(probe)
    response = use_case.execute(request, execution_context=_execution_context(probe))
    return ProbeRunResult(
        probe_id=probe.probe_id,
        request=request,
        projection=project_probe_response(probe, response),
    )


def run_probe_set(
    probes: tuple[BehavioralProbe, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run a probe set and return ``{probe_id -> canonical output projection}``.

    Defaults to the frozen core set. Probe ids must be unique — a duplicate is
    a probe-set authoring error and fails closed rather than silently
    collapsing two measurements into one.
    """
    selected = core_probe_set() if probes is None else probes
    projections: dict[str, dict[str, Any]] = {}
    for probe in selected:
        if probe.probe_id in projections:
            raise ValueError(f"duplicate probe_id in probe set: {probe.probe_id}")
        projections[probe.probe_id] = run_probe(probe).projection
    return projections


# ── Digests ─────────────────────────────────────────────────────────────────


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_probe_input_digest(
    probes: tuple[BehavioralProbe, ...] | None = None,
) -> str:
    """Digest the frozen probe **inputs**.

    Recorded separately from the output digest so a moved behavioural digest
    can be attributed: inputs unchanged means the engine changed, which is the
    signal ADR-068 relies on.
    """
    selected = core_probe_set() if probes is None else probes
    payload: dict[str, Any] = {}
    for probe in selected:
        candles: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        flows: list[dict[str, Any]] = []
        for spec in probe.tickers:
            candles.extend(
                c.to_dict() for c in build_probe_candles(spec, as_of_date=probe.as_of_date)
            )
            summaries.extend(
                {
                    "ticker": s.ticker,
                    "date": s.date.isoformat(),
                    "foreign_buy_value": str(s.foreign_buy_value),
                    "foreign_sell_value": str(s.foreign_sell_value),
                    "foreign_buy_lot": s.foreign_buy_lot,
                    "foreign_sell_lot": s.foreign_sell_lot,
                    "total_value": str(s.total_value),
                    "total_lot": s.total_lot,
                }
                for s in build_probe_broker_summaries(spec, as_of_date=probe.as_of_date)
            )
            flows.extend(
                {
                    "ticker": f.ticker,
                    "date": f.date.isoformat(),
                    "broker_code": f.broker_code,
                    "net_lot": f.net_lot,
                    "net_value": str(f.net_value),
                }
                for f in build_probe_daily_flows(spec, as_of_date=probe.as_of_date)
            )
        request = build_probe_request(probe)
        payload[probe.probe_id] = {
            "surface": probe.surface,
            "as_of_date": probe.as_of_date.isoformat(),
            "regime": probe.regime,
            "enrichment_providers_enabled": probe.enrichment_providers_enabled,
            "request": {
                "tickers": list(request.tickers),
                "window_days": request.window_days,
                "min_net_buy_days": request.min_net_buy_days,
                "min_accum_score": request.min_accum_score,
                "min_accum_score_enabled": request.min_accum_score_enabled,
                "min_signal_score": request.min_signal_score,
                "min_signal_score_enabled": request.min_signal_score_enabled,
                "min_market_cap_idr": request.min_market_cap_idr,
                "min_piotroski": request.min_piotroski,
                "resistance_gate_enabled": request.resistance_gate_enabled,
                "resistance_headroom_min_pct": request.resistance_headroom_min_pct,
            },
            "candles": candles,
            "broker_summaries": summaries,
            "broker_daily_flows": flows,
        }
    return _sha256({"probe_set_id": CORE_PROBE_SET_ID, "probes": payload})


def compute_behavioral_probe_digest(
    probes: tuple[BehavioralProbe, ...] | None = None,
) -> str:
    """Digest ``{probe_id -> canonical output projection}`` (ADR-068 §2).

    This is the behavioural identity **candidate**. It is intentionally not
    consumed by ``resolve_lean_semantic_compatibility_id`` or any other
    identity path yet: ADR-068 §7 requires the probe set to prove it detects
    deliberate scoring changes before the digest may become authoritative.
    """
    return _sha256(
        {
            "projection_contract": PROBE_PROJECTION_CONTRACT,
            "probe_set_id": CORE_PROBE_SET_ID,
            "probes": run_probe_set(probes),
        }
    )
