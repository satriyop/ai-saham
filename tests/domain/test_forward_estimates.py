from datetime import datetime

from src.domain.value_objects.forward_estimates import (
    ForwardEstimates,
    derive_forward_pe,
)


def test_derive_forward_pe_uses_price_over_eps():
    assert derive_forward_pe(10.0, 123.4) == 12.3


def test_derive_forward_pe_returns_none_when_eps_or_price_unusable():
    assert derive_forward_pe(None, 100.0) is None
    assert derive_forward_pe(0.0, 100.0) is None
    assert derive_forward_pe(10.0, None) is None


def test_forward_estimates_with_current_price_recomputes_pe_without_mutating_source():
    fetched_at = datetime(2026, 6, 27, 9, 0, 0)
    original = ForwardEstimates(
        ticker="BBCA",
        forward_eps_1y=10.0,
        revenue_forward_1y=100.0,
        current_price=None,
        forward_pe=None,
        fetched_at=fetched_at,
    )

    updated = original.with_current_price(123.4)

    assert original.forward_pe is None
    assert updated.forward_pe == 12.3
    assert updated.current_price == 123.4
    assert updated.fetched_at == fetched_at
