"""Tests for ResolveBrokerSummaryProviderPolicyUseCase — pure summary-provider selection."""

from src.application.use_case.resolve_broker_summary_provider_policy_use_case import (
    BrokerSummaryProviderKind,
    ResolveBrokerSummaryProviderPolicyRequest,
    ResolveBrokerSummaryProviderPolicyUseCase,
)

USE_CASE = ResolveBrokerSummaryProviderPolicyUseCase()


def test_idx_broker_provider_is_reused_regardless_of_config():
    response = USE_CASE.execute(
        ResolveBrokerSummaryProviderPolicyRequest(
            broker_provider_name="idx",
            configured_summary_source="idx",
        )
    )
    assert response.kind == BrokerSummaryProviderKind.REUSE_BROKER_PROVIDER


def test_stockbit_broker_provider_is_reused_when_configured_as_summary_source():
    response = USE_CASE.execute(
        ResolveBrokerSummaryProviderPolicyRequest(
            broker_provider_name="stockbit",
            configured_summary_source="stockbit",
        )
    )
    assert response.kind == BrokerSummaryProviderKind.REUSE_BROKER_PROVIDER


def test_stockbit_broker_provider_requires_dedicated_idx_provider_by_default():
    response = USE_CASE.execute(
        ResolveBrokerSummaryProviderPolicyRequest(
            broker_provider_name="stockbit",
            configured_summary_source="idx",
        )
    )
    assert response.kind == BrokerSummaryProviderKind.IDX_SUMMARY_PROVIDER
