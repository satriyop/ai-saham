"""Canonical semantic payloads for accumulation diagnostic producers.

The input bundle is assembled once at the production composition root and the
same typed objects are passed to both live diagnostic builders and this
serializer. No YAML re-read or private-builder inspection is permitted here.

Layer: Application (pure serialization; no I/O).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Mapping

from src.application.config.market_context_config import MarketContextConfig
from src.application.dto.ticker_profile import TickerProfileConfig
from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextConfig,
)
from src.application.services.institutional_flow_config import (
    InstitutionalAccumulationConfig,
)
from src.application.services.sector_context_evidence_builder import SectorContextConfig
from src.application.services.signal_engine_config import AlphaTriggerConfig
from src.application.services.signal_scoring_config import SignalScoringConfig
from src.domain.value_objects.diagnostic_producer_identity import (
    ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS,
    PRODUCER_ID_ALPHA_TRIGGER,
    PRODUCER_ID_COMPANY_QUALITY,
    PRODUCER_ID_INSTITUTIONAL_ACCUMULATION,
    PRODUCER_ID_MARKET_CONTEXT,
    PRODUCER_ID_SECTOR_PEER_CONTEXT,
    PRODUCER_ID_TICKER_PROFILE,
)


@dataclass(frozen=True)
class AccumulationDiagnosticProducerInputs:
    """One resolved, typed producer graph for a corpus capture run."""

    alpha_trigger_config: AlphaTriggerConfig
    sector_context_config: SectorContextConfig
    sector_universe_index: tuple[tuple[str, tuple[str, ...]], ...]
    institutional_accumulation_config: InstitutionalAccumulationConfig
    company_quality_context_config: CompanyQualityContextConfig
    signal_scoring_config: SignalScoringConfig
    company_quality_neutral_score: float
    ticker_profile_config: TickerProfileConfig
    ticker_universe_index: tuple[tuple[str, tuple[str, ...]], ...]
    market_context_config: MarketContextConfig
    market_context_universe: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticProducerPayloadDescriptor:
    producer_contract_id: str
    formula_id: str
    canonical_payload: Mapping[str, Any]


def _json_material(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _json_material(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_material(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_material(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_material(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported diagnostic producer material: {type(value).__name__}")


def _ordered_groups(
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[dict[str, Any]]:
    return [{"group": group, "tickers": list(tickers)} for group, tickers in groups]


def _ticker_membership(
    index: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[dict[str, Any]]:
    return [
        {"ticker": ticker, "memberships": list(memberships)}
        for ticker, memberships in sorted(index)
    ]


def build_all_accumulation_diagnostic_producer_payloads(
    inputs: AccumulationDiagnosticProducerInputs,
) -> dict[str, DiagnosticProducerPayloadDescriptor]:
    """Serialize the exact closed diagnostic producer set."""

    payloads = {
        PRODUCER_ID_ALPHA_TRIGGER: DiagnosticProducerPayloadDescriptor(
            producer_contract_id="diagnostic.alpha_trigger_projection.accum.v1",
            formula_id="signal_alpha_trigger_projection.build_score.v1",
            canonical_payload={
                "formula_id": "signal_alpha_trigger_projection.build_score.v1",
                "config": _json_material(inputs.alpha_trigger_config),
            },
        ),
        PRODUCER_ID_SECTOR_PEER_CONTEXT: DiagnosticProducerPayloadDescriptor(
            producer_contract_id="diagnostic.sector_peer_context.v1",
            formula_id="sector_context_evidence_builder.build.v1",
            canonical_payload={
                "formula_id": "sector_context_evidence_builder.build.v1",
                "config": _json_material(inputs.sector_context_config),
                # Order is semantic: first matching group wins.
                "ordered_sector_universe": _ordered_groups(inputs.sector_universe_index),
            },
        ),
        PRODUCER_ID_INSTITUTIONAL_ACCUMULATION: DiagnosticProducerPayloadDescriptor(
            producer_contract_id="diagnostic.institutional_accumulation.v1",
            formula_id="institutional_accumulation_evidence_builder.build.v1",
            canonical_payload={
                "formula_id": "institutional_accumulation_evidence_builder.build.v1",
                "config": _json_material(inputs.institutional_accumulation_config),
            },
        ),
        PRODUCER_ID_COMPANY_QUALITY: DiagnosticProducerPayloadDescriptor(
            producer_contract_id="diagnostic.company_quality_context.v1",
            formula_id="company_quality_context_evidence_builder.build.v1",
            canonical_payload={
                "formula_id": "company_quality_context_evidence_builder.build.v1",
                "config": _json_material(inputs.company_quality_context_config),
                "signal_scoring_config": _json_material(inputs.signal_scoring_config),
                "neutral_score": float(inputs.company_quality_neutral_score),
            },
        ),
        PRODUCER_ID_TICKER_PROFILE: DiagnosticProducerPayloadDescriptor(
            producer_contract_id="diagnostic.ticker_profile.v1",
            formula_id="ticker_profile_classifier.classify.v1",
            canonical_payload={
                "formula_id": "ticker_profile_classifier.classify.v1",
                "config": _json_material(inputs.ticker_profile_config),
                "universe_membership": _ticker_membership(inputs.ticker_universe_index),
            },
        ),
        PRODUCER_ID_MARKET_CONTEXT: DiagnosticProducerPayloadDescriptor(
            producer_contract_id="diagnostic.market_context.frozen.v1",
            formula_id="market_context_engine.evaluate.v1",
            canonical_payload={
                "formula_id": "market_context_engine.evaluate.v1",
                "config": _json_material(inputs.market_context_config),
                "evaluation_universe": list(inputs.market_context_universe),
                "serialization_formula_id": "market_context.to_dict.v1",
            },
        ),
    }
    if set(payloads) != set(ACCUMULATION_DIAGNOSTIC_PRODUCER_IDS):
        raise RuntimeError("diagnostic producer payload builder emitted an incomplete set")
    return payloads
