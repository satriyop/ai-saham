"""Counterparty transfer logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.institutional_flow_config import InstitutionalAccumulationConfig
from src.application.services.institutional_flow_math import (
    _clamp01,
    _group_by_date,
)
from src.domain.entities.broker_flow import BrokerDailyFlow
from src.domain.value_objects.institutional_accumulation_evidence import (
    CounterpartyTransferEvidence,
)

if TYPE_CHECKING:
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceRequest,
    )



def _counterparty_hhi(
    flows: list[BrokerDailyFlow],
    config: InstitutionalAccumulationConfig,
) -> CounterpartyTransferEvidence:
    by_date = _group_by_date(flows)
    recent = sorted(by_date)[-config.counterparty_window_days:]
    net_buy: dict[str, float] = {}
    net_sell: dict[str, float] = {}
    for d in recent:
        for flow in by_date[d]:
            code = flow.broker_code.upper()
            net = float(flow.net_value)
            net_buy[code] = net_buy.get(code, 0.0) + max(net, 0.0)
            net_sell[code] = net_sell.get(code, 0.0) + abs(min(net, 0.0))
    total_net_buy = sum(net_buy.values())
    total_net_sell = sum(net_sell.values())
    if total_net_buy <= 0 or total_net_sell <= 0:
        return CounterpartyTransferEvidence(
            transfer_asymmetry_score=None,
            buy_side_hhi=None,
            sell_side_hhi=None,
            coverage_score=0.0,
            conviction_score=0.0,
            evidence_status=config.evidence_status,
            unavailable_reasons=("zero_net_buy_or_sell",),
        )
    buy_hhi = sum((v / total_net_buy) ** 2 for v in net_buy.values())
    sell_hhi = sum((v / total_net_sell) ** 2 for v in net_sell.values())
    raw_asymmetry = buy_hhi - sell_hhi
    transfer = _clamp01((raw_asymmetry + 1.0) / 2.0)
    return CounterpartyTransferEvidence(
        transfer_asymmetry_score=round(transfer, 4),
        buy_side_hhi=round(buy_hhi, 6),
        sell_side_hhi=round(sell_hhi, 6),
        coverage_score=1.0,
        conviction_score=round(transfer, 4),
        evidence_status=config.evidence_status,
        unavailable_reasons=(),
    )


def build_counterparty_transfer(
    *,
    request: InstitutionalAccumulationEvidenceRequest,
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
) -> CounterpartyTransferEvidence | None:
    flows = list(request.broker_daily_flows)
    if not flows:
        return None
    try:
        return _counterparty_hhi(flows, config)
    except Exception as exc:
        return CounterpartyTransferEvidence(
            transfer_asymmetry_score=None,
            buy_side_hhi=None,
            sell_side_hhi=None,
            coverage_score=0.0,
            conviction_score=0.0,
            evidence_status=config.evidence_status,
            unavailable_reasons=(f"counterparty_failed:{exc}",),
        )
