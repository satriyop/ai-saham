"""Tests for StockbitBrokerDistributionProvider and BrokerDistributionSnapshot."""

from datetime import date, datetime

import pytest

from src.domain.value_objects.broker_distribution import (
    BrokerCounterparty,
    BrokerDistributionEntry,
    BrokerDistributionSnapshot,
)
from src.infrastructure.browser.stockbit_broker_distribution import (
    StockbitBrokerDistributionProvider,
    _parse_counterparties,
    _parse_entries,
    _parse_response,
)

# ── Fixtures / helpers ────────────────────────────────────────────────────────


def _make_body(
    date_info="2026-06-19",
    buy_entries=None,
    sell_entries=None,
) -> dict:
    if buy_entries is None:
        buy_entries = [
            {
                "detail": {"code": "YU", "type": "Asing", "amount": 510553670000},
                "distribute_to": [
                    {"code": "ZP", "type": "Asing", "amount": 163554732500},
                    {"code": "AK", "type": "Asing", "amount": 138896915000},
                    {"code": "SQ", "type": "Lokal", "amount": 27915345000},
                ],
            },
        ]
    if sell_entries is None:
        sell_entries = [
            {
                "detail": {"code": "ZP", "type": "Asing", "amount": 662721285000},
                "distribute_to": [
                    {"code": "YU", "type": "Asing", "amount": 176591092500},
                    {"code": "AK", "type": "Asing", "amount": 169764202500},
                ],
            },
        ]
    return {
        "data": {
            "date_info": date_info,
            "by_value": {
                "top_broker_buy": buy_entries,
                "top_broker_sell": sell_entries,
            },
        }
    }


# ── Parser tests ──────────────────────────────────────────────────────────────


def test_parse_counterparties_basic():
    raw = [
        {"code": "ZP", "type": "Asing", "amount": 163554732500},
        {"code": "SQ", "type": "Lokal", "amount": 27915345000},
    ]
    result = _parse_counterparties(raw)
    assert len(result) == 2
    assert result[0].broker_code == "ZP"
    assert result[0].amount_idr == 163554732500
    assert result[1].broker_code == "SQ"


def test_parse_counterparties_sorted_descending():
    raw = [
        {"code": "AK", "type": "Asing", "amount": 50_000},
        {"code": "ZP", "type": "Asing", "amount": 200_000},
    ]
    result = _parse_counterparties(raw)
    assert result[0].broker_code == "ZP"
    assert result[1].broker_code == "AK"


def test_parse_counterparties_skips_missing_code():
    raw = [
        {"code": "", "type": "Asing", "amount": 100},
        {"code": "AK", "type": "Asing", "amount": 200},
    ]
    result = _parse_counterparties(raw)
    assert len(result) == 1
    assert result[0].broker_code == "AK"


def test_parse_entries_basic():
    raw = [
        {
            "detail": {"code": "YU", "type": "Asing", "amount": 510553670000},
            "distribute_to": [{"code": "ZP", "type": "Asing", "amount": 163554732500}],
        }
    ]
    entries = _parse_entries(raw)
    assert len(entries) == 1
    assert entries[0].broker_code == "YU"
    assert entries[0].amount_idr == 510553670000
    assert len(entries[0].counterparties) == 1
    assert entries[0].counterparties[0].broker_code == "ZP"


def test_parse_response_full():
    snapshot = _parse_response("BBCA", _make_body())
    assert snapshot is not None
    assert snapshot.ticker == "BBCA"
    assert snapshot.date == date(2026, 6, 19)
    assert len(snapshot.top_buyers) == 1
    assert snapshot.top_buyers[0].broker_code == "YU"
    assert len(snapshot.top_sellers) == 1
    assert snapshot.top_sellers[0].broker_code == "ZP"


def test_parse_response_returns_none_on_empty_data():
    assert _parse_response("BBCA", {}) is None
    assert _parse_response("BBCA", {"data": {}}) is None


def test_parse_response_returns_none_when_no_entries():
    body = _make_body(buy_entries=[], sell_entries=[])
    assert _parse_response("BBCA", body) is None


# ── BrokerDistributionEntry properties ───────────────────────────────────────


def test_is_foreign_asing():
    entry = BrokerDistributionEntry(
        broker_code="YU", broker_type="Asing", amount_idr=100, counterparties=()
    )
    assert entry.is_foreign is True


def test_is_foreign_lokal():
    entry = BrokerDistributionEntry(
        broker_code="SQ", broker_type="Lokal", amount_idr=100, counterparties=()
    )
    assert entry.is_foreign is False


def test_domestic_counterparty_pct():
    entry = BrokerDistributionEntry(
        broker_code="YU",
        broker_type="Asing",
        amount_idr=200,
        counterparties=(
            BrokerCounterparty("ZP", "Asing", 100),
            BrokerCounterparty("SQ", "Lokal", 100),
        ),
    )
    assert entry.foreign_counterparty_pct == pytest.approx(50.0)
    assert entry.domestic_counterparty_pct == pytest.approx(50.0)


# ── BrokerDistributionSnapshot properties ────────────────────────────────────


def _make_snapshot(
    buyer_type="Asing", counterparty_type="Lokal", buy_pct=0.7
) -> BrokerDistributionSnapshot:
    cp_amount = int(100_000 * buy_pct)
    entry = BrokerDistributionEntry(
        broker_code="YU",
        broker_type=buyer_type,
        amount_idr=100_000,
        counterparties=(BrokerCounterparty("SQ", counterparty_type, cp_amount),),
    )
    return BrokerDistributionSnapshot(
        ticker="BBCA",
        date=date(2026, 6, 19),
        top_buyers=(entry,),
        top_sellers=(),
    )


def test_net_foreign_buyer_dominance_true_when_majority_foreign():
    snap = _make_snapshot(buyer_type="Asing")
    assert snap.net_foreign_buyer_dominance is True


def test_net_foreign_buyer_dominance_false_when_local():
    snap = _make_snapshot(buyer_type="Lokal")
    assert snap.net_foreign_buyer_dominance is False


def test_foreign_buying_from_domestic_true_when_dominant():
    snap = _make_snapshot(buyer_type="Asing", counterparty_type="Lokal", buy_pct=0.7)
    assert snap.foreign_buying_from_domestic is True


def test_foreign_buying_from_domestic_false_when_foreign_counterparty():
    snap = _make_snapshot(buyer_type="Asing", counterparty_type="Asing", buy_pct=0.7)
    assert snap.foreign_buying_from_domestic is False


# ── Cache round-trip ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_provider(tmp_path):
    return StockbitBrokerDistributionProvider(api_client=None, db_path=tmp_path / "test.db")


def test_schema_created(tmp_provider):
    with tmp_provider._get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_distribution_cache'"
        ).fetchone()
    assert row is not None


def test_write_then_read(tmp_provider):
    snapshot = _parse_response("BBCA", _make_body())
    snapshot = BrokerDistributionSnapshot(
        ticker="BBCA",
        date=date(2026, 6, 19),
        top_buyers=snapshot.top_buyers,
        top_sellers=snapshot.top_sellers,
        fetched_at=datetime.now(),
    )
    tmp_provider._write(snapshot)
    result = tmp_provider._read_cache("BBCA", None)
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.date == date(2026, 6, 19)
    assert len(result.top_buyers) == 1
    assert result.top_buyers[0].broker_code == "YU"
    assert len(result.top_buyers[0].counterparties) == 3


def test_is_cache_fresh_false_when_empty(tmp_provider):
    assert tmp_provider.is_cache_fresh("BBCA") is False


def test_get_distribution_returns_none_without_provider(tmp_provider):
    result = tmp_provider.get_distribution("BBCA")
    assert result is None
