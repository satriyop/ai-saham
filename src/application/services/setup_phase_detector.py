"""Deterministic setup phase detector.

Layer: Application
Depends on: domain value objects + stdlib only. No IO, repositories, providers,
CLI, or AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from src.domain.value_objects.factor_evidence import Freshness
from src.domain.value_objects.setup_phase import (
    SetupPhaseHistoryEntry,
    SetupPhaseSnapshot,
    SetupPhaseState,
)


@dataclass(frozen=True)
class SetupPhaseThresholdsConfig:
    # Rescaled 0-120 -> 0-100 (ADR-039). NOT currently read by
    # _constructive_phase()'s accumulation gate (uses passed_gates/flow_status
    # instead) — kept for potential future wiring, not an active lever.
    accumulation_min_flow_score: float = 50.0
    accumulation_min_flow_ratio_pct: float = 2.0
    compression_max_bb_width_pctile: float = 0.20
    breakout_min_close_above_prev_high_pct: float = 0.0
    # Superseded by volume_trigger.dry_up_max_ratio / expansion_min_ratio
    # (Point 3, explicit dry-up + expansion evidence). Kept for backward
    # compatibility with existing config/tuning-bounds entries; no longer an
    # active lever in _constructive_phase().
    breakout_min_volume_ratio: float = 1.2
    breakout_reclaim_vwap_min_pct: float = 0.0
    exhaustion_rsi_min: float = 72.0
    exhaustion_min_price_extension_pct: float = 8.0
    distribution_min_bandar_score: int = -4
    failed_max_drawdown_from_recent_high_pct: float = -7.0
    failed_breakdown_below_support_pct: float = -3.0


@dataclass(frozen=True)
class SetupPhaseRSPolicyConfig:
    lag_warning_below: float = -1.0
    hard_exclude_below: float = -4.0
    warning_max_decision: str = "WATCH"
    hard_exclude_max_decision: str = "AVOID"
    mean_reversion_exception_requires_support_reclaim: bool = True


@dataclass(frozen=True)
class VolumeTriggerValidityConfig:
    require_trusted_volume: bool = True
    trusted_benchmark_volume_sources: tuple[str, ...] = ("stockbit", "idx")
    min_valid_20d_sessions: int = 18
    zero_volume_tolerance: int = 1
    # Explicit dry-up/expansion evidence (Point 3). Requires
    # dry_up_reference_sessions + 1 total candles: the latest session is a
    # standalone expansion candidate, dry_up_lookback_sessions immediately
    # before it form the dry-up window, and the remaining
    # (dry_up_reference_sessions - dry_up_lookback_sessions) sessions before
    # that form the reference/baseline window. dry_up_ratio = avg(dry-up
    # window) / avg(reference window). expansion_ratio = latest session
    # volume / avg(dry-up window).
    dry_up_lookback_sessions: int = 5
    dry_up_reference_sessions: int = 20
    dry_up_max_ratio: float = 0.50
    expansion_min_ratio: float = 1.50
    expansion_requires_positive_close: bool = True


@dataclass(frozen=True)
class VolumeTriggerEvidence:
    """Explicit dry-up/expansion evidence — replaces a single loose ratio.

    volume_trigger_confirmed is the ONLY flag that may justify claiming a
    genuine "dry-up then expansion" breakout trigger. dry_up_confirmed or
    expansion_confirmed alone are honest partial evidence, not a trigger.
    """

    dry_up_ratio: float | None
    expansion_ratio: float | None
    dry_up_confirmed: bool
    expansion_confirmed: bool
    volume_trigger_confirmed: bool
    data_valid: bool
    unavailable_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetupPhaseRequirementConfig:
    required_sequence: tuple[SetupPhaseState, ...] = ()
    enter_phases: tuple[SetupPhaseState, ...] = ()
    requires_reclaim_or_pivot: bool = False
    entry_authority: bool | None = None


_ACCUMULATION_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(
    required_sequence=(
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ),
    enter_phases=(SetupPhaseState.BREAKOUT_CONFIRMATION,),
)
_BREAKOUT_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(
    required_sequence=(
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ),
    enter_phases=(SetupPhaseState.BREAKOUT_CONFIRMATION,),
)
_PULLBACK_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(
    enter_phases=(SetupPhaseState.BREAKOUT_CONFIRMATION,),
    requires_reclaim_or_pivot=True,
)
_CONFIRMATION_SEQUENCE_REQUIREMENT = SetupPhaseRequirementConfig(entry_authority=False)


@dataclass(frozen=True)
class SetupPhaseConfig:
    thresholds: SetupPhaseThresholdsConfig = field(
        default_factory=SetupPhaseThresholdsConfig
    )
    rs_policy_by_setup_family: dict[str, SetupPhaseRSPolicyConfig] = field(
        default_factory=lambda: {
            "foreign-bounce": SetupPhaseRSPolicyConfig(),
            "foreign_bounce": SetupPhaseRSPolicyConfig(),
            "accumulation": SetupPhaseRSPolicyConfig(),
            "breakout": SetupPhaseRSPolicyConfig(),
            "coiled-spring": SetupPhaseRSPolicyConfig(),
            "coiled_spring": SetupPhaseRSPolicyConfig(),
        }
    )
    requirements_by_family: dict[str, SetupPhaseRequirementConfig] = field(
        default_factory=lambda: {
            "accumulation": _ACCUMULATION_SEQUENCE_REQUIREMENT,
            "foreign-bounce": _ACCUMULATION_SEQUENCE_REQUIREMENT,
            "foreign_bounce": _ACCUMULATION_SEQUENCE_REQUIREMENT,
            "breakout": _BREAKOUT_SEQUENCE_REQUIREMENT,
            "coiled-spring": _BREAKOUT_SEQUENCE_REQUIREMENT,
            "coiled_spring": _BREAKOUT_SEQUENCE_REQUIREMENT,
            "pullback": _PULLBACK_SEQUENCE_REQUIREMENT,
            "pullback-continuation": _PULLBACK_SEQUENCE_REQUIREMENT,
            "pullback_continuation": _PULLBACK_SEQUENCE_REQUIREMENT,
            "confirmation": _CONFIRMATION_SEQUENCE_REQUIREMENT,
            "smart-money-confirmed": _CONFIRMATION_SEQUENCE_REQUIREMENT,
            "smart_money_confirmed": _CONFIRMATION_SEQUENCE_REQUIREMENT,
        }
    )
    volume_trigger: VolumeTriggerValidityConfig = field(
        default_factory=VolumeTriggerValidityConfig
    )

    def rs_policy_for(self, setup_family: str | None) -> SetupPhaseRSPolicyConfig | None:
        if not setup_family:
            return None
        key = setup_family.strip().lower()
        return self.rs_policy_by_setup_family.get(key) or self.rs_policy_by_setup_family.get(
            key.replace("-", "_")
        )

    def requirement_for(
        self, setup_family: str | None
    ) -> SetupPhaseRequirementConfig | None:
        if not setup_family:
            return None
        key = setup_family.strip().lower()
        return self.requirements_by_family.get(key) or self.requirements_by_family.get(
            key.replace("-", "_")
        )


class SetupPhaseDetector:
    """Detect setup phase from already-local candle and evidence inputs."""

    def detect(
        self,
        *,
        candles: list[Any],
        setup_eval: Any | None,
        setup_evidence: Any | None,
        flow_evidence: Any | None = None,
        setup_family: str | None = None,
        previous_phases: tuple[SetupPhaseState, ...] = (),
        config: SetupPhaseConfig | None = None,
    ) -> SetupPhaseSnapshot:
        cfg = config or SetupPhaseConfig()
        ordered = sorted(candles, key=lambda c: c.date)
        recent = ordered[-20:]
        reasons: list[str] = []
        unavailable: list[str] = []
        passed = _gate_map(setup_eval)
        latest = ordered[-1] if ordered else None
        previous = ordered[-2] if len(ordered) >= 2 else None

        # Pass the full ordered history, not `recent` (last 20) — the dry-up
        # evidence window needs dry_up_reference_sessions + 1 candles, which
        # can exceed 20 depending on config; the function slices internally.
        volume_evidence = _volume_trigger_evidence(
            ordered,
            setup_evidence=setup_evidence,
            cfg=cfg.volume_trigger,
        )
        unavailable.extend(volume_evidence.unavailable_reasons)

        rs_constraint_reasons = _rs_reasons(
            setup_evidence=setup_evidence,
            setup_family=setup_family,
            cfg=cfg,
            passed_gates=passed,
        )
        reasons.extend(rs_constraint_reasons)

        terminal = self._terminal_phase(
            latest=latest,
            recent=recent,
            setup_evidence=setup_evidence,
            flow_evidence=flow_evidence,
            thresholds=cfg.thresholds,
            reasons=reasons,
        )
        if terminal is not None:
            phase, strength = terminal
            return _snapshot(
                phase=phase,
                strength=strength,
                setup_family=setup_family,
                previous_phases=previous_phases,
                reasons=tuple(reasons),
                unavailable=tuple(unavailable),
                coverage=_coverage(setup_evidence, flow_evidence, volume_evidence.data_valid),
                config=cfg,
                volume_evidence=volume_evidence,
            )

        constructive = self._constructive_phase(
            latest=latest,
            previous=previous,
            recent=recent,
            setup_evidence=setup_evidence,
            flow_evidence=flow_evidence,
            thresholds=cfg.thresholds,
            volume_evidence=volume_evidence,
            passed_gates=passed,
            reasons=reasons,
        )
        if constructive is None:
            phase, strength = SetupPhaseState.NONE, 0.0
            reasons.append("no phase gate satisfied")
        else:
            phase, strength = constructive

        return _snapshot(
            phase=phase,
            strength=strength,
            setup_family=setup_family,
            previous_phases=previous_phases,
            reasons=tuple(reasons),
            unavailable=tuple(unavailable),
            coverage=_coverage(setup_evidence, flow_evidence, volume_evidence.data_valid),
            config=cfg,
            volume_evidence=volume_evidence,
        )

    def _terminal_phase(
        self,
        *,
        latest: Any | None,
        recent: list[Any],
        setup_evidence: Any | None,
        flow_evidence: Any | None,
        thresholds: SetupPhaseThresholdsConfig,
        reasons: list[str],
    ) -> tuple[SetupPhaseState, float] | None:
        flow_direction = getattr(flow_evidence, "flow_direction", None)
        bandar_score = getattr(flow_evidence, "bandar_broad_score", None)
        if flow_direction == "NEGATIVE" or (
            bandar_score is not None
            and bandar_score <= thresholds.distribution_min_bandar_score
        ):
            reasons.append("terminal: distribution flow detected")
            return SetupPhaseState.DISTRIBUTION, 0.9

        if latest is not None and recent:
            recent_high = max(c.high for c in recent)
            support = min(c.low for c in recent[:-1] or recent)
            drawdown = _pct_change(latest.close, recent_high)
            support_break = _pct_change(latest.close, support)
            if (
                drawdown <= thresholds.failed_max_drawdown_from_recent_high_pct
                or support_break <= thresholds.failed_breakdown_below_support_pct
            ):
                reasons.append(
                    "terminal: price failed recent high/support structure"
                )
                return SetupPhaseState.FAILED, 0.8

        rsi = getattr(setup_evidence, "rsi", None)
        if latest is not None and recent and rsi is not None:
            low = min(c.low for c in recent)
            extension = _pct_change(latest.close, low)
            if (
                rsi >= thresholds.exhaustion_rsi_min
                and extension >= thresholds.exhaustion_min_price_extension_pct
            ):
                reasons.append("terminal: exhausted extension with high RSI")
                return SetupPhaseState.EXHAUSTION, 0.75
        return None

    def _constructive_phase(
        self,
        *,
        latest: Any | None,
        previous: Any | None,
        recent: list[Any],
        setup_evidence: Any | None,
        flow_evidence: Any | None,
        thresholds: SetupPhaseThresholdsConfig,
        volume_evidence: VolumeTriggerEvidence,
        passed_gates: dict[str, bool],
        reasons: list[str],
    ) -> tuple[SetupPhaseState, float] | None:
        bb = getattr(setup_evidence, "bb_width_pctile", None)
        rsi = getattr(setup_evidence, "rsi", None)
        vwap_pct = getattr(setup_evidence, "vwap_pct", None)
        match_strength = float(getattr(setup_evidence, "match_strength", 0.0) or 0.0)
        flow_status = getattr(flow_evidence, "confirmation_status", None)

        price_gates = []
        if latest is not None and previous is not None:
            price_gates.append(
                (
                    "positive close above previous high",
                    _pct_change(latest.close, previous.high)
                    >= thresholds.breakout_min_close_above_prev_high_pct,
                )
            )
            price_gates.append(("positive close", latest.close > latest.open))
        if vwap_pct is not None:
            price_gates.append(
                (
                    "VWAP reclaim",
                    vwap_pct >= thresholds.breakout_reclaim_vwap_min_pct,
                )
            )
        price_hits = [label for label, ok in price_gates if ok]
        if price_hits and volume_evidence.volume_trigger_confirmed:
            reasons.extend(f"breakout: {label}" for label in price_hits)
            reasons.append("breakout: volume dry-up then expansion confirmed")
            strength = 0.65 + 0.05 * len(price_hits)
            if flow_status == "CONFIRMED":
                reasons.append("breakout strength: flow confirmation")
                strength += 0.1
            return SetupPhaseState.BREAKOUT_CONFIRMATION, min(1.0, strength)

        if (
            price_hits
            and volume_evidence.expansion_confirmed
            and not volume_evidence.dry_up_confirmed
        ):
            # Honest partial evidence only — expansion without a proven prior
            # dry-up is not the primary SWING_10D trigger. Config does not
            # currently allow this to substitute for the confirmed trigger
            # above; falls through to compression/accumulation checks below.
            reasons.append("breakout: volume expansion without prior dry-up")

        if bb is not None and bb <= thresholds.compression_max_bb_width_pctile:
            reasons.append("compression: BB width readiness")
            if volume_evidence.dry_up_confirmed and not volume_evidence.expansion_confirmed:
                reasons.append(
                    "compression: volume dry-up readiness, no expansion yet"
                )
            return SetupPhaseState.COMPRESSION, min(1.0, 0.55 + (match_strength / 250.0))

        accumulation_gates = (
            passed_gates.get("foreign_flow_score", False),
            passed_gates.get("flow_pct", False),
            flow_status in {"CONFIRMED", "WATCH_ZONE"},
        )
        if any(accumulation_gates):
            reasons.append("accumulation: flow/absorption evidence present")
            if volume_evidence.dry_up_confirmed and not volume_evidence.expansion_confirmed:
                reasons.append(
                    "accumulation: volume dry-up readiness, no expansion yet"
                )
            return SetupPhaseState.ACCUMULATION, min(1.0, 0.45 + (match_strength / 220.0))

        if rsi is not None and 40.0 <= rsi <= 60.0 and match_strength >= 60.0:
            reasons.append("accumulation: neutral RSI with partial setup fit")
            return SetupPhaseState.ACCUMULATION, 0.55

        return None


def _snapshot(
    *,
    phase: SetupPhaseState,
    strength: float,
    setup_family: str | None,
    previous_phases: tuple[SetupPhaseState, ...],
    reasons: tuple[str, ...],
    unavailable: tuple[str, ...],
    coverage: float,
    config: SetupPhaseConfig,
    volume_evidence: VolumeTriggerEvidence | None = None,
) -> SetupPhaseSnapshot:
    sequence_valid, sequence_reason = _sequence_validity(
        setup_family,
        phase,
        reasons,
        previous_phases,
        config,
    )
    out_reasons = list(reasons)
    if sequence_reason:
        out_reasons.append(sequence_reason)
    strength = max(0.0, min(1.0, round(strength, 4)))
    coverage = max(0.0, min(1.0, round(coverage, 4)))
    return SetupPhaseSnapshot(
        current_phase=phase,
        previous_phase=previous_phases[-1] if previous_phases else None,
        phase_age_sessions=1 if phase != SetupPhaseState.NONE else 0,
        phase_strength=strength,
        coverage_score=coverage,
        conviction_score=round(strength * coverage, 4),
        sequence_valid=sequence_valid,
        reasons=tuple(out_reasons),
        unavailable_evidence_reasons=unavailable,
        volume_dry_up_ratio=(
            volume_evidence.dry_up_ratio if volume_evidence is not None else None
        ),
        volume_expansion_ratio=(
            volume_evidence.expansion_ratio if volume_evidence is not None else None
        ),
        volume_dry_up_confirmed=(
            volume_evidence.dry_up_confirmed if volume_evidence is not None else None
        ),
        volume_expansion_confirmed=(
            volume_evidence.expansion_confirmed if volume_evidence is not None else None
        ),
        volume_trigger_confirmed=(
            volume_evidence.volume_trigger_confirmed if volume_evidence is not None else None
        ),
        history=tuple(
            SetupPhaseHistoryEntry(
                phase=previous_phase,
                started_at=None,
                ended_at=None,
                age_sessions=0,
                strength=0.0,
                reasons=("prior phase supplied for sequence validation",),
                sequence_valid_after_transition=None,
            )
            for previous_phase in previous_phases
        ),
    )


def _sequence_validity(
    setup_family: str | None,
    phase: SetupPhaseState,
    reasons: tuple[str, ...],
    previous_phases: tuple[SetupPhaseState, ...],
    config: SetupPhaseConfig,
) -> tuple[bool | None, str | None]:
    if phase in {
        SetupPhaseState.NONE,
        SetupPhaseState.FAILED,
        SetupPhaseState.DISTRIBUTION,
        SetupPhaseState.EXHAUSTION,
    }:
        return None, None
    requirement = config.requirement_for(setup_family)
    if requirement is None:
        return None, None
    if requirement.requires_reclaim_or_pivot:
        has_reclaim = any(
            "VWAP reclaim" in r or "support reclaim" in r for r in reasons
        )
        valid = phase == SetupPhaseState.BREAKOUT_CONFIRMATION and has_reclaim
        return valid, "sequence policy: trend support plus reclaim/pivot confirmation"
    if not requirement.required_sequence:
        return None, None
    seq = requirement.required_sequence
    if phase not in seq:
        valid = False
    else:
        idx = seq.index(phase)
        valid = True if idx == 0 else _contains_ordered(previous_phases, seq[:idx])
    return valid, _sequence_reason_text(seq)


def _sequence_reason_text(seq: tuple[SetupPhaseState, ...]) -> str:
    if seq == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    ):
        return "sequence policy: accumulation -> compression -> breakout"
    if seq == (SetupPhaseState.COMPRESSION, SetupPhaseState.BREAKOUT_CONFIRMATION):
        return "sequence policy: compression -> breakout"
    return "sequence policy: " + " -> ".join(p.value.lower() for p in seq)


def _contains_ordered(
    values: tuple[SetupPhaseState, ...],
    required: tuple[SetupPhaseState, ...],
) -> bool:
    index = 0
    for value in values:
        if value == required[index]:
            index += 1
            if index == len(required):
                return True
    return False


def _gate_map(setup_eval: Any | None) -> dict[str, bool]:
    return {
        str(getattr(gate, "label", "")): bool(getattr(gate, "passed", False))
        for gate in getattr(setup_eval, "gates", ()) or ()
    }


def _unavailable_volume_evidence(reasons: list[str]) -> VolumeTriggerEvidence:
    return VolumeTriggerEvidence(
        dry_up_ratio=None,
        expansion_ratio=None,
        dry_up_confirmed=False,
        expansion_confirmed=False,
        volume_trigger_confirmed=False,
        data_valid=False,
        unavailable_reasons=tuple(reasons),
    )


def _volume_trigger_evidence(
    candles: list[Any],
    *,
    setup_evidence: Any | None,
    cfg: VolumeTriggerValidityConfig,
) -> VolumeTriggerEvidence:
    ticker = getattr(setup_evidence, "ticker", None) or (
        getattr(candles[-1], "ticker", None) if candles else None
    )
    source = getattr(setup_evidence, "candle_source", None)
    source_reason = _volume_source_unavailable_reason(
        ticker=ticker,
        source=source,
        cfg=cfg,
    )
    if source_reason is not None:
        return _unavailable_volume_evidence([source_reason])

    reference_total = cfg.dry_up_reference_sessions
    lookback = cfg.dry_up_lookback_sessions
    # dry_up_reference_sessions is the reference+dry-up window size (matching
    # the min_valid_20d_sessions/zero_volume_tolerance data-quality check,
    # unchanged below). The latest session is a standalone expansion
    # candidate reserved OUTSIDE that window — a spike on the latest session
    # must not dilute its own baseline — so one extra candle is required
    # beyond reference_total, and reference_window ends up sized exactly
    # reference_total - lookback (matching the documented contract).
    total_required = reference_total + 1
    if len(candles) < total_required:
        return _unavailable_volume_evidence([
            f"volume trigger unavailable: required {total_required} sessions, "
            f"found {len(candles)}"
        ])
    if lookback <= 0 or lookback >= reference_total:
        return _unavailable_volume_evidence([
            "volume trigger unavailable: invalid dry-up window configuration"
        ])

    quality_window = candles[-reference_total:]
    zero_volume = sum(1 for candle in quality_window if int(candle.volume) <= 0)
    valid_sessions = reference_total - zero_volume
    if valid_sessions < cfg.min_valid_20d_sessions or zero_volume > cfg.zero_volume_tolerance:
        return _unavailable_volume_evidence([
            "volume trigger unavailable: insufficient valid 20d volume sessions"
        ])

    window = candles[-total_required:]
    latest = window[-1]
    dry_up_window = window[-(lookback + 1):-1]
    reference_window = window[:-(lookback + 1)]

    reference_avg = _avg_volume(reference_window)
    dry_up_avg = _avg_volume(dry_up_window)
    if reference_avg <= 0:
        return _unavailable_volume_evidence(
            ["volume trigger unavailable: invalid reference baseline"]
        )
    if dry_up_avg <= 0:
        return _unavailable_volume_evidence(
            ["volume trigger unavailable: invalid dry-up baseline"]
        )

    dry_up_ratio = round(dry_up_avg / reference_avg, 4)
    expansion_ratio = round(float(latest.volume) / dry_up_avg, 4)

    dry_up_confirmed = dry_up_ratio <= cfg.dry_up_max_ratio
    expansion_confirmed = expansion_ratio >= cfg.expansion_min_ratio
    if expansion_confirmed and cfg.expansion_requires_positive_close:
        expansion_confirmed = latest.close > latest.open

    return VolumeTriggerEvidence(
        dry_up_ratio=dry_up_ratio,
        expansion_ratio=expansion_ratio,
        dry_up_confirmed=dry_up_confirmed,
        expansion_confirmed=expansion_confirmed,
        volume_trigger_confirmed=dry_up_confirmed and expansion_confirmed,
        data_valid=True,
        unavailable_reasons=(),
    )


def _volume_source_unavailable_reason(
    *,
    ticker: str | None,
    source: str | None,
    cfg: VolumeTriggerValidityConfig,
) -> str | None:
    if not cfg.require_trusted_volume:
        return None
    source_key = (source or "").strip().lower()
    if _is_benchmark_ticker(ticker):
        trusted = {str(value).strip().lower() for value in cfg.trusted_benchmark_volume_sources}
        if source_key not in trusted:
            return (
                "volume trigger unavailable: benchmark source "
                f"{source or 'missing'} is not trusted"
            )
        return None
    if source_key in {"synthetic", "yahoo_inferred", "missing"}:
        return f"volume trigger unavailable: synthetic/missing source {source_key}"
    return None


def _is_benchmark_ticker(ticker: str | None) -> bool:
    if not ticker:
        return False
    key = ticker.upper().replace(".JK", "")
    return key in {"IHSG", "^JKSE", "JKSE", "COMPOSITE"}


def _avg_volume(candles: list[Any]) -> float:
    if not candles:
        return 0.0
    return sum(float(c.volume) for c in candles) / len(candles)


def _coverage(
    setup_evidence: Any | None,
    flow_evidence: Any | None,
    volume_valid: bool,
) -> float:
    present = 0
    present += 1 if setup_evidence is not None else 0
    present += 1 if flow_evidence is not None else 0
    present += 1 if volume_valid else 0
    return present / 3.0


def _rs_reasons(
    *,
    setup_evidence: Any | None,
    setup_family: str | None,
    cfg: SetupPhaseConfig,
    passed_gates: dict[str, bool],
) -> list[str]:
    policy = cfg.rs_policy_for(setup_family)
    if policy is None:
        return []
    freshness = getattr(setup_evidence, "rs_freshness", None)
    rs = getattr(setup_evidence, "rs_vs_ihsg_5d", None)
    if freshness != Freshness.FRESH or rs is None:
        return ["rs_policy_unavailable"]
    support_reclaim = passed_gates.get("fvwap%", False)
    if rs <= policy.hard_exclude_below:
        return [
            "rs_policy_hard_exclude: "
            f"RS {rs:.2f} <= {policy.hard_exclude_below:.2f}; "
            f"max_decision={policy.hard_exclude_max_decision}"
        ]
    if rs <= policy.lag_warning_below:
        exception = (
            " with support reclaim exception"
            if support_reclaim
            and not policy.mean_reversion_exception_requires_support_reclaim
            else ""
        )
        return [
            "rs_policy_warning: "
            f"RS {rs:.2f} <= {policy.lag_warning_below:.2f}; "
            f"max_decision={policy.warning_max_decision}{exception}"
        ]
    return ["rs_policy_passed"]


def _pct_change(value: Decimal, base: Decimal) -> float:
    if base == 0:
        return 0.0
    return float((value - base) / base * Decimal("100"))
