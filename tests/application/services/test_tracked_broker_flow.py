"""Tests for TrackedBrokerFlowSnapshot, classify_broker_tier, and compute functions.

`compute_tracked_broker_flow` sources exclusively from `broker_daily_flow`
(via `get_broker_daily_flows()`) — configured tracked broker codes only, NOT
full-market broker composition. `get_broker_summaries()` must never be called
by this module; that is a separate data product.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.services.tracked_broker_flow import (
    TrackedBrokerFlowSnapshot,
    classify_broker_tier,
    compute_quality_label,
    compute_tracked_broker_flow,
    compute_tracked_broker_flow_batch,
)

_SMART = ("AK", "BK", "ZP")
_NOISE = ("YP", "PD")


# ── classify_broker_tier ───────────────────────────────────────────────────────

def test_smart_broker_classified_correctly():
    assert classify_broker_tier("AK", _SMART, _NOISE) == "smart"


def test_noise_broker_classified_correctly():
    assert classify_broker_tier("YP", _SMART, _NOISE) == "noise"


def test_unknown_broker_classified_as_neutral():
    assert classify_broker_tier("CS", _SMART, _NOISE) == "neutral"


def test_broker_tier_case_insensitive():
    assert classify_broker_tier("ak", _SMART, _NOISE) == "smart"
    assert classify_broker_tier("yp", _SMART, _NOISE) == "noise"


# ── compute_quality_label ──────────────────────────────────────────────────────

def test_label_smart_plus_when_smart_dominates_buying():
    label = compute_quality_label(Decimal("100"), Decimal("20"), Decimal("10"))
    assert label == "smart+"


def test_label_noise_plus_when_noise_dominates_buying():
    label = compute_quality_label(Decimal("10"), Decimal("100"), Decimal("5"))
    assert label == "noise+"


def test_label_smart_minus_when_smart_leads_selling():
    label = compute_quality_label(Decimal("-100"), Decimal("-10"), Decimal("0"))
    assert label == "smart-"


def test_label_noise_minus_when_noise_sells_more():
    label = compute_quality_label(Decimal("0"), Decimal("-50"), Decimal("-10"))
    assert label == "noise-"


def test_label_dist_when_smart_sells_but_noise_buys():
    # Smart slightly selling, noise is buying → not noise- or smart-, net negative via neutral
    label = compute_quality_label(Decimal("-5"), Decimal("10"), Decimal("-30"))
    assert label == "dist"


def test_label_mixed_when_all_small_positive():
    label = compute_quality_label(Decimal("5"), Decimal("5"), Decimal("10"))
    assert label == "mixed"


def test_label_na_when_all_zero():
    label = compute_quality_label(Decimal("0"), Decimal("0"), Decimal("0"))
    assert label == "n/a"


# ── compute_tracked_broker_flow (unit with mock repo) ──────────────────────────

@dataclass
class _FakeDailyFlow:
    broker_code: str
    net_value: Decimal
    date: date
    source: str = "stockbit"


def _make_repo(flows):
    repo = MagicMock()
    repo.get_broker_daily_flows.return_value = flows
    return repo


def test_compute_tracked_broker_flow_returns_none_when_no_rows():
    repo = _make_repo([])
    result = compute_tracked_broker_flow("BBCA", repo, _SMART, _NOISE)
    assert result is None


def test_compute_tracked_broker_flow_basic_smart_buying():
    flows = [_FakeDailyFlow("AK", Decimal("100"), date(2026, 6, 20))]
    result = compute_tracked_broker_flow("BBCA", _make_repo(flows), _SMART, _NOISE)
    assert result is not None
    assert result.smart_flow == Decimal("100")
    assert result.noise_flow == Decimal("0")
    assert result.label == "smart+"
    assert result.sessions == 1
    assert result.through_date == date(2026, 6, 20)
    assert result.scope == "tracked_brokers"


def test_compute_tracked_broker_flow_mixed_smart_and_noise():
    flows = [
        _FakeDailyFlow("AK", Decimal("50"), date(2026, 6, 20)),
        _FakeDailyFlow("YP", Decimal("60"), date(2026, 6, 20)),
    ]
    result = compute_tracked_broker_flow("BBCA", _make_repo(flows), _SMART, _NOISE)
    assert result is not None
    assert result.smart_flow == Decimal("50")
    assert result.noise_flow == Decimal("60")
    assert result.label == "noise+"


def test_compute_tracked_broker_flow_respects_window_sessions():
    flows = [
        _FakeDailyFlow("AK", Decimal("10"), date(2026, 6, i)) for i in range(1, 11)
    ]
    result = compute_tracked_broker_flow(
        "BBCA", _make_repo(flows), _SMART, _NOISE, window_sessions=3
    )
    assert result is not None
    assert result.sessions == 3


def test_compute_tracked_broker_flow_counts_distinct_dates_not_rows():
    """Sessions must count distinct trading dates, not per-broker rows —
    broker_daily_flow has multiple broker rows per date."""
    flows = [
        _FakeDailyFlow("AK", Decimal("10"), date(2026, 6, 20)),
        _FakeDailyFlow("YP", Decimal("5"), date(2026, 6, 20)),
        _FakeDailyFlow("BK", Decimal("15"), date(2026, 6, 19)),
    ]
    result = compute_tracked_broker_flow("BBCA", _make_repo(flows), _SMART, _NOISE)
    assert result is not None
    assert result.sessions == 2


def test_compute_tracked_broker_flow_calls_get_broker_daily_flows_not_summaries():
    repo = _make_repo([_FakeDailyFlow("AK", Decimal("10"), date(2026, 6, 20))])
    compute_tracked_broker_flow("BBCA", repo, _SMART, _NOISE)

    repo.get_broker_daily_flows.assert_called_once()
    repo.get_broker_summaries.assert_not_called()


# ── compute_tracked_broker_flow_batch ──────────────────────────────────────────

def test_batch_returns_dict_by_ticker():
    flows = [_FakeDailyFlow("AK", Decimal("100"), date(2026, 6, 20))]
    repo = _make_repo(flows)
    result = compute_tracked_broker_flow_batch(["bbca", "BBRI"], repo, _SMART, _NOISE)
    assert "BBCA" in result
    assert "BBRI" in result


def test_batch_excludes_tickers_with_no_rows():
    repo = _make_repo([])
    result = compute_tracked_broker_flow_batch(["BBCA"], repo, _SMART, _NOISE)
    assert result == {}


# ── TrackedBrokerFlowSnapshot.to_dict ──────────────────────────────────────────

def test_to_dict_serialization():
    snap = TrackedBrokerFlowSnapshot(
        label="smart+",
        smart_flow=Decimal("100"),
        noise_flow=Decimal("0"),
        neutral_flow=Decimal("50"),
        sessions=3,
        through_date=date(2026, 6, 20),
    )
    d = snap.to_dict()
    assert d["label"] == "smart+"
    assert d["smart_flow"] == "100"
    assert d["through"] == "2026-06-20"
    assert d["sessions"] == 3
    assert d["source"] == "broker_daily_flow"
    assert d["scope"] == "tracked_brokers"


def test_source_rejects_non_broker_daily_flow_value():
    with pytest.raises(ValueError, match="broker_daily_flow"):
        TrackedBrokerFlowSnapshot(
            label="smart+",
            smart_flow=Decimal("100"),
            noise_flow=Decimal("0"),
            neutral_flow=Decimal("0"),
            sessions=1,
            through_date=date(2026, 6, 20),
            source="stockbit",
        )


def test_scope_rejects_non_tracked_brokers_value():
    with pytest.raises(ValueError, match="tracked_brokers"):
        TrackedBrokerFlowSnapshot(
            label="smart+",
            smart_flow=Decimal("100"),
            noise_flow=Decimal("0"),
            neutral_flow=Decimal("0"),
            sessions=1,
            through_date=date(2026, 6, 20),
            scope="full_market",
        )
