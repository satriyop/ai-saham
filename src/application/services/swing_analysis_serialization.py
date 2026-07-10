"""Serialization helpers for swing analysis DTO output."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.application.services.volatility_context import build_volatility_context

if TYPE_CHECKING:
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse


def signal_response_to_dict(
    response: "AssessSignalResponse | None",
) -> dict[str, Any] | None:
    if response is None:
        return None
    return {
        "score": response.assessment.score,
        "raw_exact_score": response.assessment.raw_exact_score,
        "strength": response.assessment.strength.value,
        "entry_quality": response.assessment.entry_quality.value,
        "breakdown": response.assessment.breakdown_dict,
        "coverage_score": response.coverage_score,             # canonical
        "evidence_confidence": response.evidence_confidence,   # legacy alias
        "confidence_score": response.assessment.confidence_score,  # legacy alias
        "coverage_warning": response.coverage_warning,
        "alpha_trigger_score": (
            response.assessment.alpha_trigger_score.to_dict()
            if response.assessment.alpha_trigger_score else None
        ),
        "decision_constraints": (
            response.assessment.decision_constraints.to_dict()
            if getattr(response.assessment, "decision_constraints", None) else None
        ),
    }


def volatility_context_to_dict(
    *,
    atr_value: Decimal | None,
    latest_close: Decimal | None,
) -> dict[str, Any]:
    vc = build_volatility_context(atr_value=atr_value, latest_close=latest_close)
    return {
        "atr_20": vc.atr_at_signal,
        "atr_pct": vc.atr_pct_at_signal,
        "volatility_bucket": vc.volatility_bucket_at_signal,
        "stop_model_hint": "ATR_MULTIPLE",
        "suggested_stop_atr": 2.0,
        "suggested_target_atr": 3.0,
        "volatility_size_multiplier": vc.volatility_size_multiplier_at_signal,
    }


def object_to_dict(value: Any | None) -> Any | None:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return value


def risk_response_to_dict(response: Any | None) -> dict[str, Any] | None:
    if response is None:
        return None
    assessment = response.assessment
    return {
        "risk_status": assessment.risk_level_name,
        "confidence": assessment.confidence,
        "sma20": float(assessment.indicators.sma),
        "ema20": float(assessment.indicators.ema),
        "rsi14": float(assessment.indicators.rsi),
        "gate_triggered": assessment.gate_triggered,
    }


def risk_response_to_preview_dict(response: Any | None) -> dict[str, Any] | None:
    if response is None:
        return None
    return {
        "level": response.assessment.risk_level_name,
        "gate_triggered": response.assessment.gate_triggered,
    }


def candidate_accumulation_to_dict(candidate: Any | None) -> dict[str, Any]:
    if candidate is None:
        return {
            "foreign_flow_score": None,
            "streak": None,
            "trend": None,
            "flow_pct": None,
            "vwap_disc_pct": None,
            "bb_width_pctile": None,
            "foreign_flow_evidence": None,
            "dividend_risk": False,
            "rights_issue_risk": False,
            "upcoming_rups": [],
            "seasonal_score": None,
            "seasonal_label": None,
            "insider_buying": False,
            "recent_insider_buys": [],
            "analyst_consensus": None,
            "shareholding": None,
            "bandar_detector": None,
            "fundamentals": None,
            "ticker_notation": None,
        }
    return {
        "foreign_flow_score": candidate.foreign_flow_score,
        "streak": candidate.consecutive_streak,
        "trend": candidate.trend,
        "flow_pct": candidate.avg_flow_ratio,
        "vwap_disc_pct": candidate.vwap_discount_pct,
        "bb_width_pctile": candidate.bb_width_pctile,
        "foreign_flow_evidence": (
            candidate.foreign_flow_evidence.to_dict()
            if getattr(candidate, "foreign_flow_evidence", None) else None
        ),
        "dividend_risk": candidate.dividend_risk,
        "rights_issue_risk": candidate.rights_issue_risk,
        "upcoming_rups": candidate.upcoming_rups,
        "seasonal_score": (
            candidate.seasonal_edge.score if candidate.seasonal_edge else None
        ),
        "seasonal_label": (
            candidate.seasonal_edge.label if candidate.seasonal_edge else None
        ),
        "insider_buying": candidate.insider_buying,
        "recent_insider_buys": candidate.recent_insider_buys,
        "analyst_consensus": (
            candidate.analyst_consensus.to_dict()
            if candidate.analyst_consensus else None
        ),
        "shareholding": (
            candidate.shareholding.to_dict() if candidate.shareholding else None
        ),
        "bandar_detector": (
            candidate.bandar_detector.to_dict() if candidate.bandar_detector else None
        ),
        "fundamentals": (
            candidate.fundamentals.to_dict() if candidate.fundamentals else None
        ),
        "ticker_notation": (
            candidate.ticker_notation.to_dict() if candidate.ticker_notation else None
        ),
    }
