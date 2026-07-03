"""Deterministic attribution summary for swing backtest tuning.

Intent:
    This module turns completed swing backtest trades into grouped evidence for
    human/AI-assisted YAML tuning. It is a reporting/learning artifact only.
    It must not be used by live entry logic, backtest entry filtering, or risk
    decisions.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from src.application.services.stats import average, profit_factor, win_rate

MIN_TUNING_SAMPLE_SIZE = 30


@dataclass(frozen=True)
class AttributionGroupStat:
    """Performance stats for one tuning dimension bucket."""

    dimension: str
    bucket: str
    trade_count: int
    win_rate_pct: float | None
    avg_return_pct: float | None
    total_pnl: Decimal
    profit_factor: float | None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "bucket": self.bucket,
            "trade_count": self.trade_count,
            "win_rate_pct": self.win_rate_pct,
            "avg_return_pct": self.avg_return_pct,
            "total_pnl": str(self.total_pnl),
            "profit_factor": self.profit_factor,
        }


@dataclass(frozen=True)
class SampleQuality:
    """Deterministic readiness gate for attribution-driven tuning."""

    status: str
    completed_trade_count: int
    candidate_observation_count: int
    min_sample_size: int
    trade_sample_ready: bool
    candidate_sample_ready: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "completed_trade_count": self.completed_trade_count,
            "candidate_observation_count": self.candidate_observation_count,
            "min_sample_size": self.min_sample_size,
            "trade_sample_ready": self.trade_sample_ready,
            "candidate_sample_ready": self.candidate_sample_ready,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CandidateAttributionStat:
    """Forward-return stats for screened candidates, including rejected setups."""

    dimension: str
    bucket: str
    observation_count: int
    win_rate_pct: float | None
    avg_forward_return_pct: float | None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "bucket": self.bucket,
            "observation_count": self.observation_count,
            "win_rate_pct": self.win_rate_pct,
            "avg_forward_return_pct": self.avg_forward_return_pct,
        }


@dataclass(frozen=True)
class TuningTarget:
    """Allowlisted config target for one attribution dimension."""

    dimension: str
    source_scope: str
    source_field: str
    meaning: str
    config_family: str
    yaml_paths: tuple[str, ...]
    allowed_use: str
    warning: str | None = None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "source_scope": self.source_scope,
            "source_field": self.source_field,
            "meaning": self.meaning,
            "config_family": self.config_family,
            "yaml_paths": list(self.yaml_paths),
            "allowed_use": self.allowed_use,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class AttributionBucketPolicy:
    """Score bucket boundaries for attribution grouping only."""

    high_min_score: float = 70.0
    mid_min_score: float = 45.0

    def __post_init__(self) -> None:
        if self.high_min_score <= self.mid_min_score:
            raise ValueError("high_min_score must be greater than mid_min_score")

    def to_dict(self) -> dict:
        return {
            "high_min_score": self.high_min_score,
            "mid_min_score": self.mid_min_score,
        }


@dataclass(frozen=True)
class SwingBacktestAttributionSummary:
    """Grouped deterministic evidence for tuning swing workflow YAML."""

    intent: str = "learning_summary_only_not_entry_logic"
    bucket_policy: AttributionBucketPolicy = field(default_factory=AttributionBucketPolicy)
    sample_quality: SampleQuality = field(
        default_factory=lambda: _build_sample_quality(0, 0)
    )
    group_stats: tuple[AttributionGroupStat, ...] = field(default_factory=tuple)
    candidate_group_stats: tuple[CandidateAttributionStat, ...] = field(default_factory=tuple)
    tuning_targets: tuple[TuningTarget, ...] = field(
        default_factory=lambda: DEFAULT_TUNING_TARGETS
    )

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "bucket_policy": self.bucket_policy.to_dict(),
            "sample_quality": self.sample_quality.to_dict(),
            "group_stats": [stat.to_dict() for stat in self.group_stats],
            "candidate_group_stats": [
                stat.to_dict() for stat in self.candidate_group_stats
            ],
            "tuning_targets": [target.to_dict() for target in self.tuning_targets],
        }


DEFAULT_TUNING_TARGETS: tuple[TuningTarget, ...] = (
    TuningTarget(
        dimension="trade_setup_action",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.trade_setup_action",
        meaning="Final TradeSetup action observed on executed portfolio trades.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.classification",
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
            "config/signal_engine.yaml:signal_engine.classification.moderate_min_score",
            "config/signal_engine.yaml:signal_engine.evidence_groups",
            "config/risk_engine.yaml:risk_engine.gates",
        ),
        allowed_use="Tune final signal/risk thresholds only from executed-trade outcomes.",
    ),
    TuningTarget(
        dimension="signal_strength",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.signal_strength",
        meaning="SignalAssessment strength bucket on executed portfolio trades.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
            "config/signal_engine.yaml:signal_engine.classification.moderate_min_score",
        ),
        allowed_use="Tune signal classification thresholds from completed trade outcomes.",
    ),
    TuningTarget(
        dimension="signal_score_bucket",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.signal_score",
        meaning="Bucketed SignalEngine total score on executed portfolio trades.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.classification",
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
            "config/signal_engine.yaml:signal_engine.classification.moderate_min_score",
            "config/swing_backtest.yaml:swing_backtest.attribution.score_buckets",
            "config/swing_backtest.yaml:swing_backtest.attribution.score_buckets.high_min_score",
            "config/swing_backtest.yaml:swing_backtest.attribution.score_buckets.mid_min_score",
        ),
        allowed_use="Tune score thresholds; attribution buckets are reporting-only.",
    ),
    TuningTarget(
        dimension="signal_factor_bucket",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.signal_breakdown",
        meaning="Bucketed SignalEngine evidence group scores on executed portfolio trades.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.evidence_groups",
            "config/signal_engine.yaml:signal_engine.evidence_groups.setup_quality.weight",
            "config/signal_engine.yaml:signal_engine.evidence_groups.flow_confirmation.weight",
            "config/signal_engine.yaml:signal_engine.flags",
            "config/signal_engine.yaml:signal_engine.flags.valuation_stretched.score_penalty",
            "config/signal_engine.yaml:signal_engine.flags.analyst_bearish.score_penalty",
            "config/signal_engine.yaml:signal_engine.flags.insider_selling.score_penalty",
            "config/signal_engine.yaml:signal_engine.scoring.bandar",
        ),
        allowed_use="Tune evidence group weights and flag penalty thresholds.",
    ),
    TuningTarget(
        dimension="risk_status",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.risk_status",
        meaning="RiskEngine OPEN/BLOCKED status recorded on executed portfolio trades.",
        config_family="risk",
        yaml_paths=(
            "config/risk_engine.yaml:risk_engine.gates",
            "config/risk_engine.yaml:risk_engine.gates.fundamental.piotroski_min",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.median_tx_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.free_float.min_free_float_pct",
        ),
        allowed_use="Tune risk gate policy only with candidate stats as a bias check.",
        warning="Completed trades can underrepresent blocked/rejected candidates.",
    ),
    TuningTarget(
        dimension="risk_gate",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.risk_gate",
        meaning="Risk gate label recorded on executed portfolio trades.",
        config_family="risk",
        yaml_paths=(
            "config/risk_engine.yaml:risk_engine.gates",
            "config/risk_engine.yaml:risk_engine.gates.fundamental.piotroski_min",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.median_tx_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.free_float.min_free_float_pct",
        ),
        allowed_use="Tune gate thresholds only with candidate stats as a bias check.",
        warning="Completed trades can underrepresent blocked/rejected candidates.",
    ),
    TuningTarget(
        dimension="setup_gate",
        source_scope="completed_trades_and_screened_candidates",
        source_field="SetupGate.label + SetupGate.passed",
        meaning="Pass/fail state for named swing setup gates.",
        config_family="setup",
        yaml_paths=("config/swing_setups.yaml:setups.*.gates",),
        allowed_use="Tune setup gates using candidate_group_stats first; trades are confirmation.",
    ),
    TuningTarget(
        dimension="regime",
        source_scope="completed_trades",
        source_field="SwingBacktestTrade.regime",
        meaning="MarketContext regime on executed portfolio trades.",
        config_family="market_context",
        yaml_paths=(
            "config/market_context_engine.yaml:market_context_engine",
            "config/market_context_engine.yaml:market_context_engine.regime_thresholds.risk_on_min_score",
            "config/market_context_engine.yaml:market_context_engine.regime_thresholds.risk_off_max_score",
            "config/market_context_engine.yaml:market_context_engine.regime_thresholds.volatile_vix_override",
            "config/market_context_engine.yaml:market_context_engine.regime_effects.RISK_OFF.signal_multiplier",
            "config/market_context_engine.yaml:market_context_engine.regime_effects.VOLATILE.signal_multiplier",
            "config/swing_targets.yaml:setup_targets",
            "config/swing_targets.yaml:setup_targets.risk_on.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.risk_on.stop_loss_pct",
            "config/swing_targets.yaml:setup_targets.neutral.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.neutral.stop_loss_pct",
            "config/swing_targets.yaml:setup_targets.risk_off.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.risk_off.stop_loss_pct",
            "config/swing_targets.yaml:setup_targets.volatile.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.volatile.stop_loss_pct",
        ),
        allowed_use="Tune regime context and regime-adaptive exits from executed trades.",
    ),
    TuningTarget(
        dimension="candidate_setup_match",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.setup_match",
        meaning="Setup fit result for every screened candidate with forward data.",
        config_family="setup",
        yaml_paths=(
            "config/swing_setups.yaml:setups.*.gates",
            "config/swing_setups.yaml:setups.*.partial_max_failed_gates",
        ),
        allowed_use="Primary evidence for setup gate tuning; not an executed trade result.",
    ),
    TuningTarget(
        dimension="candidate_signal_strength",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.signal_strength",
        meaning="Signal strength on every screened candidate with forward data.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.classification",
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
            "config/signal_engine.yaml:signal_engine.classification.moderate_min_score",
        ),
        allowed_use="Bias check for signal thresholds before validating on completed trades.",
    ),
    TuningTarget(
        dimension="candidate_signal_score_bucket",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.signal_score",
        meaning="Bucketed SignalEngine score on every screened candidate with forward data.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.classification",
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
            "config/signal_engine.yaml:signal_engine.classification.moderate_min_score",
            "config/swing_backtest.yaml:swing_backtest.attribution.score_buckets",
            "config/swing_backtest.yaml:swing_backtest.attribution.score_buckets.high_min_score",
            "config/swing_backtest.yaml:swing_backtest.attribution.score_buckets.mid_min_score",
        ),
        allowed_use="Bias check for signal score thresholds; buckets are reporting-only.",
    ),
    TuningTarget(
        dimension="candidate_signal_factor_bucket",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.signal_breakdown",
        meaning="Bucketed evidence group scores on every screened candidate with forward data.",
        config_family="signal",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine.evidence_groups",
            "config/signal_engine.yaml:signal_engine.evidence_groups.setup_quality.weight",
            "config/signal_engine.yaml:signal_engine.evidence_groups.flow_confirmation.weight",
            "config/signal_engine.yaml:signal_engine.flags",
            "config/signal_engine.yaml:signal_engine.flags.valuation_stretched.score_penalty",
            "config/signal_engine.yaml:signal_engine.flags.analyst_bearish.score_penalty",
            "config/signal_engine.yaml:signal_engine.flags.insider_selling.score_penalty",
            "config/signal_engine.yaml:signal_engine.scoring.bandar",
        ),
        allowed_use="Bias check for evidence group tuning before completed-trade validation.",
    ),
    TuningTarget(
        dimension="candidate_risk_status",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.risk_status",
        meaning="RiskEngine OPEN/BLOCKED status on every screened candidate with forward data.",
        config_family="risk",
        yaml_paths=(
            "config/risk_engine.yaml:risk_engine.gates",
            "config/risk_engine.yaml:risk_engine.gates.fundamental.piotroski_min",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.median_tx_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.free_float.min_free_float_pct",
        ),
        allowed_use="Primary evidence for risk gate tuning; not an executed trade result.",
    ),
    TuningTarget(
        dimension="candidate_risk_gate",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.risk_gate",
        meaning="Risk gate label on every screened candidate with forward data.",
        config_family="risk",
        yaml_paths=(
            "config/risk_engine.yaml:risk_engine.gates",
            "config/risk_engine.yaml:risk_engine.gates.fundamental.piotroski_min",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.median_tx_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.free_float.min_free_float_pct",
        ),
        allowed_use="Primary evidence for risk gate threshold tuning.",
    ),
    TuningTarget(
        dimension="candidate_trade_setup_action",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.trade_setup_action",
        meaning="TradeSetup action on every screened candidate with forward data.",
        config_family="signal_and_risk",
        yaml_paths=(
            "config/signal_engine.yaml:signal_engine",
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score",
            "config/signal_engine.yaml:signal_engine.classification.moderate_min_score",
            "config/risk_engine.yaml:risk_engine",
            "config/risk_engine.yaml:risk_engine.gates.fundamental.piotroski_min",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.liquidity.median_tx_floor_idr",
            "config/risk_engine.yaml:risk_engine.gates.free_float.min_free_float_pct",
        ),
        allowed_use="Bias check for final action composition; not portfolio execution.",
    ),
    TuningTarget(
        dimension="candidate_regime",
        source_scope="screened_candidates",
        source_field="SwingBacktestCandidateObservation.regime",
        meaning="MarketContext regime on every screened candidate with forward data.",
        config_family="market_context",
        yaml_paths=(
            "config/market_context_engine.yaml:market_context_engine",
            "config/market_context_engine.yaml:market_context_engine.regime_thresholds.risk_on_min_score",
            "config/market_context_engine.yaml:market_context_engine.regime_thresholds.risk_off_max_score",
            "config/market_context_engine.yaml:market_context_engine.regime_thresholds.volatile_vix_override",
            "config/market_context_engine.yaml:market_context_engine.regime_effects.RISK_OFF.signal_multiplier",
            "config/market_context_engine.yaml:market_context_engine.regime_effects.VOLATILE.signal_multiplier",
            "config/swing_targets.yaml:setup_targets",
            "config/swing_targets.yaml:setup_targets.risk_on.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.risk_on.stop_loss_pct",
            "config/swing_targets.yaml:setup_targets.neutral.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.neutral.stop_loss_pct",
            "config/swing_targets.yaml:setup_targets.risk_off.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.risk_off.stop_loss_pct",
            "config/swing_targets.yaml:setup_targets.volatile.take_profit_pct",
            "config/swing_targets.yaml:setup_targets.volatile.stop_loss_pct",
        ),
        allowed_use="Bias check for market context tuning before completed-trade validation.",
    ),
)


def _build_sample_quality(
    completed_trade_count: int,
    candidate_observation_count: int,
    min_sample_size: int = MIN_TUNING_SAMPLE_SIZE,
) -> SampleQuality:
    trade_ready = completed_trade_count >= min_sample_size
    candidate_ready = candidate_observation_count >= min_sample_size

    notes: list[str] = []
    if completed_trade_count == 0 and candidate_observation_count == 0:
        status = "INSUFFICIENT_SAMPLE"
        notes.append("No completed trades or candidate observations are available.")
    elif trade_ready and candidate_ready:
        status = "MIXED_READY"
        notes.append("Completed-trade and screened-candidate samples meet the minimum.")
    elif trade_ready:
        status = "TRADE_READY"
        notes.append("Completed-trade sample meets the minimum.")
        notes.append("Candidate sample is below the minimum; setup/risk gate tuning is weaker.")
    elif candidate_ready:
        status = "CANDIDATE_ONLY"
        notes.append("Screened-candidate sample meets the minimum.")
        notes.append(
            "Completed-trade sample is below the minimum; "
            "portfolio outcome tuning is blocked."
        )
    else:
        status = "INSUFFICIENT_SAMPLE"
        notes.append("Samples are below the minimum required for tuning suggestions.")

    if completed_trade_count < min_sample_size:
        notes.append(
            f"Completed trades: {completed_trade_count}/{min_sample_size} minimum."
        )
    if candidate_observation_count < min_sample_size:
        notes.append(
            f"Candidate observations: {candidate_observation_count}/{min_sample_size} minimum."
        )

    return SampleQuality(
        status=status,
        completed_trade_count=completed_trade_count,
        candidate_observation_count=candidate_observation_count,
        min_sample_size=min_sample_size,
        trade_sample_ready=trade_ready,
        candidate_sample_ready=candidate_ready,
        notes=tuple(notes),
    )


def summarize_swing_backtest_attribution(
    trades: Iterable[Any],
    candidate_observations: Iterable[Any] = (),
    bucket_policy: AttributionBucketPolicy | None = None,
) -> SwingBacktestAttributionSummary:
    """Build deterministic grouped attribution from completed backtest trades."""
    rows = list(trades)
    groups: dict[tuple[str, str], list[Any]] = {}
    observation_rows = list(candidate_observations)
    candidate_groups: dict[tuple[str, str], list[Any]] = {}
    policy = bucket_policy or AttributionBucketPolicy()

    for trade in rows:
        for dimension, bucket in _trade_buckets(trade, policy):
            groups.setdefault((dimension, bucket), []).append(trade)

    for observation in observation_rows:
        for dimension, bucket in _candidate_buckets(observation, policy):
            candidate_groups.setdefault((dimension, bucket), []).append(observation)

    stats = tuple(
        sorted(
            (
                _build_stat(dimension, bucket, bucket_trades)
                for (dimension, bucket), bucket_trades in groups.items()
            ),
            key=lambda stat: (stat.dimension, -stat.trade_count, stat.bucket),
        )
    )
    candidate_stats = tuple(
        sorted(
            (
                _build_candidate_stat(dimension, bucket, bucket_observations)
                for (dimension, bucket), bucket_observations in candidate_groups.items()
            ),
            key=lambda stat: (stat.dimension, -stat.observation_count, stat.bucket),
        )
    )
    return SwingBacktestAttributionSummary(
        bucket_policy=policy,
        sample_quality=_build_sample_quality(
            completed_trade_count=len(rows),
            candidate_observation_count=len(observation_rows),
        ),
        group_stats=stats,
        candidate_group_stats=candidate_stats,
    )


def _trade_buckets(
    trade: Any,
    bucket_policy: AttributionBucketPolicy,
) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "trade_setup_action", getattr(trade, "trade_setup_action", None))
    _add(buckets, "risk_status", getattr(trade, "risk_status", None))
    _add(buckets, "risk_gate", getattr(trade, "risk_gate", None))
    _add(buckets, "signal_strength", getattr(trade, "signal_strength", None))
    _add(
        buckets,
        "signal_score_bucket",
        _score_bucket(getattr(trade, "signal_score", None), bucket_policy),
    )
    _add(buckets, "regime", getattr(trade, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(trade, "setup_gates", ()))
    _add_signal_factor_buckets(
        buckets,
        getattr(trade, "signal_breakdown", ()),
        bucket_policy,
    )
    return tuple(buckets)


def _candidate_buckets(
    observation: Any,
    bucket_policy: AttributionBucketPolicy,
) -> tuple[tuple[str, str], ...]:
    buckets: list[tuple[str, str]] = []
    _add(buckets, "candidate_setup_match", getattr(observation, "setup_match", None))
    _add(buckets, "candidate_signal_strength", getattr(observation, "signal_strength", None))
    _add(
        buckets,
        "candidate_signal_score_bucket",
        _score_bucket(getattr(observation, "signal_score", None), bucket_policy),
    )
    _add(buckets, "candidate_risk_status", getattr(observation, "risk_status", None))
    _add(buckets, "candidate_risk_gate", getattr(observation, "risk_gate", None))
    _add(buckets, "candidate_trade_setup_action", getattr(observation, "trade_setup_action", None))
    _add(buckets, "candidate_regime", getattr(observation, "regime", None))
    _add_setup_gate_buckets(buckets, getattr(observation, "setup_gates", ()))
    _add_signal_factor_buckets(
        buckets,
        getattr(observation, "signal_breakdown", ()),
        bucket_policy,
        dimension="candidate_signal_factor_bucket",
    )
    return tuple(buckets)


def _add(buckets: list[tuple[str, str]], dimension: str, bucket: object | None) -> None:
    if bucket is None:
        return
    bucket_text = str(bucket)
    if bucket_text:
        buckets.append((dimension, bucket_text))


def _add_setup_gate_buckets(
    buckets: list[tuple[str, str]],
    setup_gates: Iterable[Any],
) -> None:
    for gate in setup_gates:
        label = getattr(gate, "label", None)
        if not label:
            continue
        status = "PASS" if getattr(gate, "passed", False) else "FAIL"
        buckets.append(("setup_gate", f"{label}:{status}"))


def _add_signal_factor_buckets(
    buckets: list[tuple[str, str]],
    signal_breakdown: Iterable[tuple[str, float]],
    bucket_policy: AttributionBucketPolicy,
    dimension: str = "signal_factor_bucket",
) -> None:
    for name, value in signal_breakdown:
        buckets.append((
            dimension,
            f"{name}:{_score_bucket(value, bucket_policy)}",
        ))


def _score_bucket(
    value: int | float | None,
    bucket_policy: AttributionBucketPolicy,
) -> str | None:
    if value is None:
        return None
    high = _format_threshold(bucket_policy.high_min_score)
    mid = _format_threshold(bucket_policy.mid_min_score)
    high_floor = _format_threshold(bucket_policy.high_min_score - 1)
    if value >= bucket_policy.high_min_score:
        return f"HIGH_{high}_PLUS"
    if value >= bucket_policy.mid_min_score:
        return f"MID_{mid}_{high_floor}"
    return f"LOW_BELOW_{mid}"


def _format_threshold(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value).replace(".", "_")


def _build_stat(
    dimension: str,
    bucket: str,
    trades: list[Any],
) -> AttributionGroupStat:
    return AttributionGroupStat(
        dimension=dimension,
        bucket=bucket,
        trade_count=len(trades),
        win_rate_pct=win_rate((trade.net_return_pct for trade in trades), precision=2),
        avg_return_pct=average((trade.net_return_pct for trade in trades), precision=4),
        total_pnl=sum((trade.pnl for trade in trades), Decimal("0")),
        profit_factor=profit_factor((trade.pnl for trade in trades), precision=4),
    )


def _build_candidate_stat(
    dimension: str,
    bucket: str,
    observations: list[Any],
) -> CandidateAttributionStat:
    return CandidateAttributionStat(
        dimension=dimension,
        bucket=bucket,
        observation_count=len(observations),
        win_rate_pct=win_rate(
            (observation.forward_return_pct for observation in observations),
            precision=2,
        ),
        avg_forward_return_pct=average(
            (observation.forward_return_pct for observation in observations),
            precision=4,
        ),
    )
