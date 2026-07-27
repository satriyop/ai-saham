"""Build pre-open observation payloads saved at capture time (ADR-048 Phase 2).

Payload holds decision-time signal/risk/TradeSetup/plan as written on capture.
Grade and labels must not rewrite these fields for production cohorts.

Layer: Application
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
    SignalClassificationConfig,
)
from src.domain.value_objects.pre_open_signal_evidence import (
    PRE_OPEN_HORIZON,
    PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT,
)
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_assessment import (
    PRE_OPEN_AUCTION_DIRECTION_IDENTITY,
)
from src.domain.value_objects.signal_observation_contracts import (
    PRE_OPEN_OBSERVATION_CONTRACT,
)

PRE_OPEN_WORKFLOW = "screen_pre_open"


def compute_pre_open_config_hash(
    *,
    signal_config: PreOpenDirectionalBaselineConfig,
    classification_config: SignalClassificationConfig,
    iev_min: int,
    top_n: int | None,
    evidence_contract: str = PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT,
) -> str:
    """Short material config hash for observation identity (not full sha256 id)."""
    material = {
        "signal_assessment_identity": PRE_OPEN_AUCTION_DIRECTION_IDENTITY.to_dict(),
        "evidence_contract": evidence_contract,
        "horizon": PRE_OPEN_HORIZON,
        "directional_baseline": asdict(signal_config),
        "classification": asdict(classification_config),
        "iev_min": iev_min,
        "top_n": top_n,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def compute_pre_open_semantic_compatibility_id(
    *,
    signal_config: PreOpenDirectionalBaselineConfig,
    classification_config: SignalClassificationConfig,
    iev_min: int,
    top_n: int | None,
) -> SemanticCompatibilityId:
    material = {
        "signal_assessment_identity": PRE_OPEN_AUCTION_DIRECTION_IDENTITY.to_dict(),
        "config_hash": compute_pre_open_config_hash(
            signal_config=signal_config,
            classification_config=classification_config,
            iev_min=iev_min,
            top_n=top_n,
        ),
        "contract": PRE_OPEN_OBSERVATION_CONTRACT,
        "evidence": PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT,
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return SemanticCompatibilityId(f"sha256:{digest}")


def derive_pre_open_screen_result(
    *,
    has_entry_range: bool,
    signal_summary: Any | None,
    trade_setup: Any | None,
) -> str:
    """Funnel label (not SetupAction)."""
    if not has_entry_range:
        return "rejected_plan"
    if signal_summary is None:
        return "rejected_auction_missing"
    eq = getattr(signal_summary, "entry_quality", None)
    if eq == "AVOID":
        return "rejected_signal"
    if trade_setup is not None:
        action = getattr(getattr(trade_setup, "action", None), "value", None)
        if action and str(action).startswith("BLOCKED"):
            return "rejected_risk"
    return "pass"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def build_pre_open_observation_payload(
    *,
    ticker: str,
    snapshot_date: date,
    captured_at: datetime,
    collection_started_at: datetime,
    decision_at: datetime,
    decision_snapshot_ref: str,
    screen_result: str,
    candidate: Any,
    signal_summary: Any | None,
    risk_summary: Any | None,
    trade_setup: Any | None,
    capture_phase: str,
    source_status: str | None,
    source_snapshot_ref: str | None,
    iev_min: int,
    horizon: str = PRE_OPEN_HORIZON,
    evidence_contract: str = PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT,
    market_regime: Any | None = None,
) -> dict:
    """Schema-versioned decision payload for one pre-open name (as saved on capture).

    ``market_regime`` is the session MarketContext (or dict) frozen at capture so
    post-open assess can apply regime gates without live MCE or sidecars.
    """
    candidate_dict: dict[str, Any]
    if hasattr(candidate, "to_dict") and callable(candidate.to_dict):
        candidate_dict = _jsonable(candidate.to_dict())
    elif is_dataclass(candidate) and not isinstance(candidate, type):
        # ScreenerCandidate is a plain dataclass (no to_dict)
        candidate_dict = _jsonable(asdict(candidate))
    else:
        candidate_dict = {"ticker": ticker}

    regime_payload: Any | None
    if market_regime is None:
        regime_payload = None
    elif hasattr(market_regime, "to_dict") and callable(market_regime.to_dict):
        regime_payload = _jsonable(market_regime.to_dict())
    elif isinstance(market_regime, dict):
        regime_payload = _jsonable(market_regime)
    else:
        regime_payload = str(market_regime)

    return {
        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        "artifact_type": "pre_open_candidate_observation",
        "signal_assessment_identity": (
            signal_summary.identity.to_dict() if signal_summary is not None else None
        ),
        "observation_contract": PRE_OPEN_OBSERVATION_CONTRACT,
        "evidence_contract_version": evidence_contract,
        "horizon": horizon,
        "ticker": ticker,
        "snapshot_date": snapshot_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "collection_started_at": collection_started_at.isoformat(),
        "decision_at": decision_at.isoformat(),
        "decision_snapshot_ref": decision_snapshot_ref,
        "workflow": PRE_OPEN_WORKFLOW,
        "screen_result": screen_result,
        "capture_phase": capture_phase,
        "source_status": source_status,
        "source_snapshot_ref": source_snapshot_ref,
        "request": {"iev_min": iev_min},
        "candidate": candidate_dict,
        "signal": _jsonable(signal_summary.to_dict()) if signal_summary is not None else None,
        "risk": _jsonable(risk_summary.to_dict()) if risk_summary is not None else None,
        "trade_setup": _jsonable(trade_setup.to_dict()) if trade_setup is not None else None,
        "market_regime": regime_payload,
    }
