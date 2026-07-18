"""Deterministic setup phase detector.

Layer: Application
Depends on: domain value objects + stdlib only. No IO, repositories, providers,
CLI, or AI.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Compatibility surface:
# - Canonical import(s):
#   - SetupPhaseConfig, SetupPhaseRequirementConfig,
#     SetupPhaseThresholdsConfig, VolumeTriggerEvidence,
#     VolumeTriggerValidityConfig -> src.application.services.setup_phase_config
# - Allowed contents:
#   - re-export only for the config DTOs above. This module remains canonical
#     for SetupPhaseDetector itself, which is not part of the compatibility
#     surface.
# - Expiry:
#   - permanent public API, or remove after internal imports migrate to
#     src.application.services.setup_phase_config directly.
from src.application.services.setup_phase_config import (
    SetupPhaseConfig,
    SetupPhaseRequirementConfig,  # noqa: F401 — re-exported for backward compat
    SetupPhaseThresholdsConfig,
    VolumeTriggerEvidence,
    VolumeTriggerValidityConfig,  # noqa: F401 — re-exported for backward compat
)
from src.application.services.setup_phase_sequence_policy import (
    validate_setup_phase_sequence,
)
from src.application.services.setup_phase_volume_trigger import (
    volume_trigger_evidence as _volume_trigger_evidence,
)
from src.domain.value_objects.setup_phase import (
    SetupPhaseHistoryEntry,
    SetupPhaseSnapshot,
    SetupPhaseState,
)

__all__ = [
    "SetupPhaseDetector",
    "SetupPhaseConfig",
    "SetupPhaseRequirementConfig",
    "SetupPhaseThresholdsConfig",
    "VolumeTriggerEvidence",
    "VolumeTriggerValidityConfig",
]


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
    sequence_valid, sequence_reason = validate_setup_phase_sequence(
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
        phase_detection_strength=strength,
        phase_input_coverage=coverage,
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


def _gate_map(setup_eval: Any | None) -> dict[str, bool]:
    return {
        str(getattr(gate, "label", "")): bool(getattr(gate, "passed", False))
        for gate in getattr(setup_eval, "gates", ()) or ()
    }


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


def _pct_change(value: Decimal, base: Decimal) -> float:
    if base == 0:
        return 0.0
    return float((value - base) / base * Decimal("100"))
