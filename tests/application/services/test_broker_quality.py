"""Tests for BrokerQualitySnapshot, classify_broker_tier, and compute functions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.services.broker_quality import (
    BrokerQualitySnapshot,
    classify_broker_tier,
    compute_broker_quality,
    compute_broker_quality_batch,
    compute_quality_label,
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


# ── compute_broker_quality (unit with mock repo) ───────────────────────────────

@dataclass
class _FakeTx:
    broker_code: str
    net_value: Decimal


@dataclass
class _FakeSummary:
    top_buyers: list
    top_sellers: list
    date: date
    source: str = "stockbit"


def _make_repo(summaries):
    repo = MagicMock()
    repo.get_broker_summaries.return_value = summaries
    return repo


def test_compute_broker_quality_returns_none_when_no_named_rows():
    repo = _make_repo([_FakeSummary(top_buyers=[], top_sellers=[], date=date(2026, 6, 20))])
    result = compute_broker_quality("BBCA", repo, _SMART, _NOISE)
    assert result is None


def test_compute_broker_quality_basic_smart_buying():
    summaries = [
        _FakeSummary(
            top_buyers=[_FakeTx("AK", Decimal("100"))],
            top_sellers=[],
            date=date(2026, 6, 20),
        )
    ]
    result = compute_broker_quality("BBCA", _make_repo(summaries), _SMART, _NOISE)
    assert result is not None
    assert result.smart_flow == Decimal("100")
    assert result.noise_flow == Decimal("0")
    assert result.label == "smart+"
    assert result.sessions == 1
    assert result.through_date == date(2026, 6, 20)


def test_compute_broker_quality_mixed_smart_and_noise():
    summaries = [
        _FakeSummary(
            top_buyers=[_FakeTx("AK", Decimal("50")), _FakeTx("YP", Decimal("60"))],
            top_sellers=[],
            date=date(2026, 6, 20),
        )
    ]
    result = compute_broker_quality("BBCA", _make_repo(summaries), _SMART, _NOISE)
    assert result is not None
    assert result.smart_flow == Decimal("50")
    assert result.noise_flow == Decimal("60")
    assert result.label == "noise+"


def test_compute_broker_quality_respects_window_sessions():
    summaries = [
        _FakeSummary(top_buyers=[_FakeTx("AK", Decimal("10"))], top_sellers=[], date=date(2026, 6, i))
        for i in range(1, 11)
    ]
    result = compute_broker_quality("BBCA", _make_repo(summaries), _SMART, _NOISE, window_sessions=3)
    assert result is not None
    assert result.sessions == 3


# ── compute_broker_quality_batch ───────────────────────────────────────────────

def test_batch_returns_dict_by_ticker():
    summaries = [
        _FakeSummary(top_buyers=[_FakeTx("AK", Decimal("100"))], top_sellers=[], date=date(2026, 6, 20))
    ]
    repo = _make_repo(summaries)
    result = compute_broker_quality_batch(["bbca", "BBRI"], repo, _SMART, _NOISE)
    assert "BBCA" in result
    assert "BBRI" in result


def test_batch_excludes_tickers_with_no_named_rows():
    repo = _make_repo([_FakeSummary(top_buyers=[], top_sellers=[], date=date(2026, 6, 20))])
    result = compute_broker_quality_batch(["BBCA"], repo, _SMART, _NOISE)
    assert result == {}


# ── BrokerQualitySnapshot.to_dict ─────────────────────────────────────────────

def test_to_dict_serialization():
    snap = BrokerQualitySnapshot(
        label="smart+",
        smart_flow=Decimal("100"),
        noise_flow=Decimal("0"),
        neutral_flow=Decimal("50"),
        sessions=3,
        through_date=date(2026, 6, 20),
        source="stockbit",
    )
    d = snap.to_dict()
    assert d["label"] == "smart+"
    assert d["smart_flow"] == "100"
    assert d["through"] == "2026-06-20"
    assert d["sessions"] == 3
