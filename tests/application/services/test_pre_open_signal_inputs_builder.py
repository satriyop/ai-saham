from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.application.services.pre_open_signal_inputs_builder import (
    PreOpenSignalInputsBuilder,
)

DAY = date(2026, 6, 18)
STARTED_AT = datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta"))
DECISION_AT = datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))


def _candidate(**overrides):
    values = {
        "ticker": "BBRI",
        "iev": 250_000,
        "prev_close": Decimal("5000"),
        "gap_pct": Decimal("1.2"),
        "iep": 5060,
        "iep_gap_pct": Decimal("1.2"),
        "bid_gap_pct": Decimal("0.8"),
        "gap_price_source": "IEP",
        "bid_offer_imbalance": 0.62,
        "spread_pct": Decimal("0.4"),
        "trend_signal": "BULLISH",
        "unusual_volume": False,
        "iev_intensity": 2.0,
        "atr": Decimal("50"),
        "rsi": Decimal("55"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _build(candidate=None, **overrides):
    return PreOpenSignalInputsBuilder().build(
        candidate or _candidate(),
        trade_date=DAY,
        collection_started_at=STARTED_AT,
        decision_at=DECISION_AT,
        capture_phase="NCP_LOCKED",
        source_is_live=True,
        snapshot_ref="test:ncp",
        **overrides,
    )


def test_builder_preserves_canonical_auction_fields_and_locked_delta():
    evaluation_input = _build(delta_iev=12_345)

    auction = evaluation_input.evidence.auction_ncp
    assert evaluation_input.ticker == "BBRI"
    assert evaluation_input.snapshot_date == DAY
    assert auction is not None
    assert auction.delta_iev == 12_345
    assert auction.iep == 5060
    assert auction.iep_gap_pct == Decimal("1.2")
    assert auction.bid_gap_pct == Decimal("0.8")
    assert auction.gap_price_source == "IEP"


@pytest.mark.parametrize(
    ("source_is_live", "capture_phase", "snapshot_ref"),
    (
        (False, "NCP_LOCKED", "test:ncp"),
        (True, "PRE_NCP", "test:ncp"),
        (True, "NCP_LOCKED", None),
    ),
)
def test_builder_keeps_unproven_auction_discovery_only(
    source_is_live,
    capture_phase,
    snapshot_ref,
):
    evaluation_input = PreOpenSignalInputsBuilder().build(
        _candidate(),
        trade_date=DAY,
        collection_started_at=STARTED_AT,
        decision_at=DECISION_AT,
        capture_phase=capture_phase,
        source_is_live=source_is_live,
        snapshot_ref=snapshot_ref,
    )

    assert evaluation_input.evidence.auction_ncp is None
    assert evaluation_input.evidence.open_viability is not None


def test_builder_has_no_scoring_api():
    assert not hasattr(PreOpenSignalInputsBuilder(), "evaluate")
