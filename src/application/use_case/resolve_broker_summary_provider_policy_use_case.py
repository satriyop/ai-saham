"""
Broker summary provider selection policy for `saham fetch market`.

Decides whether the IDX daily-summary role should be filled by reusing the
already-selected broker provider (when it is IDX itself, or when Stockbit
is the configured summary source) or by constructing a dedicated IDX
summary provider. Pure decision logic: no I/O, no infrastructure imports.

Layer: Application
"""

from dataclasses import dataclass
from enum import Enum


class BrokerSummaryProviderKind(Enum):
    REUSE_BROKER_PROVIDER = "reuse_broker_provider"
    IDX_SUMMARY_PROVIDER = "idx_summary_provider"


@dataclass(frozen=True)
class ResolveBrokerSummaryProviderPolicyRequest:
    broker_provider_name: str
    configured_summary_source: str


@dataclass(frozen=True)
class ResolveBrokerSummaryProviderPolicyResponse:
    kind: BrokerSummaryProviderKind


class ResolveBrokerSummaryProviderPolicyUseCase:
    """Pure broker-summary-provider selection decision."""

    def execute(
        self, request: ResolveBrokerSummaryProviderPolicyRequest
    ) -> ResolveBrokerSummaryProviderPolicyResponse:
        if request.broker_provider_name == "idx":
            return ResolveBrokerSummaryProviderPolicyResponse(
                BrokerSummaryProviderKind.REUSE_BROKER_PROVIDER
            )
        if request.configured_summary_source == "stockbit":
            # Stockbit now returns accurate total_value for summaries too.
            return ResolveBrokerSummaryProviderPolicyResponse(
                BrokerSummaryProviderKind.REUSE_BROKER_PROVIDER
            )
        return ResolveBrokerSummaryProviderPolicyResponse(
            BrokerSummaryProviderKind.IDX_SUMMARY_PROVIDER
        )
