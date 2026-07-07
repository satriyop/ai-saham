from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)


def test_save_and_get_signal_forward_label(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = SignalForwardLabel(
        ticker="bbca",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=10.0,
        max_forward_return=12.0,
        max_adverse_excursion=-2.0,
        days_to_peak=8,
        days_to_trough=2,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )

    repo.save_many([label])
    restored = repo.get("BBCA", date(2026, 7, 1), SignalLabelHorizon.SWING_10D)

    assert restored is not None
    assert restored.ticker == "BBCA"
    assert restored.entry_reference_price == Decimal("100")
    assert restored.outcome_label == SignalForwardOutcome.SUCCESS
    assert restored.target_would_trigger is True
    assert restored.stop_would_trigger is False
    assert restored.fingerprint.setup_family == "foreign_bounce"
    assert restored.fingerprint.market_regime == {"regime": "RISK_ON"}


def test_get_at_and_list_signal_forward_labels(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    day = date(2026, 7, 1)
    older = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=4.0)
    newer = _label(captured_at=datetime(2026, 7, 1, 10, 0, 0), close_return=5.0)
    repo.save_many([older, newer])

    exact = repo.get_at("bbca", day, SignalLabelHorizon.SWING_10D, older.observation_captured_at)
    latest = repo.get("bbca", day, SignalLabelHorizon.SWING_10D)
    listed = repo.list(signal_date=day, horizon=SignalLabelHorizon.SWING_10D, ticker="BBCA")

    assert exact is not None
    assert exact.close_return == 4.0
    assert latest is not None
    assert latest.close_return == 5.0
    assert [label.close_return for label in listed] == [5.0, 4.0]


def test_save_many_is_idempotent_for_same_observation(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteSignalForwardLabelsRepository(db_path)
    label = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=4.0)
    updated = _label(captured_at=datetime(2026, 7, 1, 9, 0, 0), close_return=5.0)

    repo.save_many([label])
    repo.save_many([updated])
    listed = repo.list(signal_date=date(2026, 7, 1), horizon=SignalLabelHorizon.SWING_10D)

    assert len(listed) == 1
    assert listed[0].close_return == 5.0


def test_schema_created_via_migration_runner(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteSignalForwardLabelsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        versions = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace=?",
            ("signal_forward_labels",),
        ).fetchall()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

    assert {row[0] for row in versions} == {0, 1}
    assert "signal_forward_labels" in {row[0] for row in tables}


def _label(*, captured_at: datetime, close_return: float) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=close_return,
        max_forward_return=close_return,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            coverage=0.8,
            conviction=0.8,
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=captured_at,
    )
