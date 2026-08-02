"""Immutable trading-session calendar snapshot (path-label / readiness authority).

Contract ``stockbit.trading_sessions.ihsg_history.v1``:
A successfully completed, strict Stockbit IHSG historical query defines the
observed market-session dates for its requested range. This is Stockbit-attested
observation — not official IDX calendar reconstruction.

Layer: Domain (pure)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.learning_artifacts import (
    LearningContractError,
    artifact_digest,
)

STOCKBIT_TRADING_SESSIONS_CONTRACT = "stockbit.trading_sessions.ihsg_history.v1"
TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT = "stockbit"
TRADING_SESSION_CALENDAR_BENCHMARK_IHSG = "IHSG"
# Path-label metrics that bind windows to an immutable calendar snapshot.
PATH_LABEL_METRICS_SCHEMA_VERSION = 3
_CALENDAR_SNAPSHOT_KEYS: frozenset[str] = frozenset(
    {
        "snapshot_id",
        "contract_id",
        "source",
        "benchmark",
        "coverage_start",
        "coverage_end",
        "ordered_sessions",
        "source_revision",
        "captured_at",
        "payload_digest",
    }
)


def label_window_digest(
    *,
    calendar_snapshot_id: str,
    label_contract_id: str,
    signal_date: date,
    sessions: Sequence[date],
) -> str:
    """Stable identity for a first-N window bound to one calendar snapshot."""
    return artifact_digest(
        {
            "calendar_snapshot_id": calendar_snapshot_id,
            "label_contract_id": label_contract_id,
            "signal_date": signal_date.isoformat(),
            "sessions": [session.isoformat() for session in sessions],
        }
    )


@dataclass(frozen=True)
class TradingSessionCalendarSnapshot:
    """Immutable attested session calendar for a coverage window."""

    snapshot_id: str
    contract_id: str
    source: str
    benchmark: str
    coverage_start: date
    coverage_end: date
    ordered_sessions: tuple[date, ...]
    source_revision: str
    captured_at: datetime
    payload_digest: str

    def to_known_calendar(self) -> KnownTradingSessionCalendar:
        return KnownTradingSessionCalendar(
            sessions=self.ordered_sessions,
            coverage_start=self.coverage_start,
            coverage_end=self.coverage_end,
        )

    def first_n_sessions_after(self, earlier: date, n: int) -> tuple[date, ...] | None:
        return self.to_known_calendar().first_n_sessions_after(earlier, n)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "contract_id": self.contract_id,
            "source": self.source,
            "benchmark": self.benchmark,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
            "ordered_sessions": [s.isoformat() for s in self.ordered_sessions],
            "source_revision": self.source_revision,
            "captured_at": self.captured_at.isoformat(),
            "payload_digest": self.payload_digest,
        }

    @classmethod
    def create(
        cls,
        *,
        coverage_start: date,
        coverage_end: date,
        ordered_sessions: Sequence[date],
        source_revision: str,
        captured_at: datetime,
        contract_id: str = STOCKBIT_TRADING_SESSIONS_CONTRACT,
        source: str = TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT,
        benchmark: str = TRADING_SESSION_CALENDAR_BENCHMARK_IHSG,
    ) -> TradingSessionCalendarSnapshot:
        if coverage_start > coverage_end:
            raise LearningContractError("coverage_start must not be after coverage_end")
        if type(source_revision) is not str or not source_revision:
            raise LearningContractError("source_revision must be non-empty str")
        if source_revision != source_revision.strip():
            raise LearningContractError(
                f"source_revision must not have surrounding whitespace (got {source_revision!r})"
            )
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise LearningContractError("captured_at must be timezone-aware")
        sessions = tuple(ordered_sessions)
        _validate_sessions(sessions, coverage_start=coverage_start, coverage_end=coverage_end)
        payload = {
            "contract_id": contract_id,
            "source": source,
            "benchmark": benchmark,
            "coverage_start": coverage_start.isoformat(),
            "coverage_end": coverage_end.isoformat(),
            "ordered_sessions": [s.isoformat() for s in sessions],
            "source_revision": source_revision,
        }
        digest = artifact_digest(payload)
        # Identity excludes captured_at (operational). Digest covers content.
        snapshot_id = artifact_digest(
            {
                "contract_id": contract_id,
                "coverage_start": coverage_start.isoformat(),
                "coverage_end": coverage_end.isoformat(),
                "ordered_sessions": [s.isoformat() for s in sessions],
                "source_revision": source_revision,
                "payload_digest": digest,
            }
        )
        return cls(
            snapshot_id=snapshot_id,
            contract_id=contract_id,
            source=source,
            benchmark=benchmark,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            ordered_sessions=sessions,
            source_revision=source_revision,
            captured_at=captured_at,
            payload_digest=digest,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> TradingSessionCalendarSnapshot:
        """Parse stored mapping without str() coercion of authority fields."""
        if not isinstance(raw, Mapping):
            raise LearningContractError(
                f"calendar snapshot must be a mapping, got {type(raw).__name__}"
            )
        keys = frozenset(raw.keys())
        if keys != _CALENDAR_SNAPSHOT_KEYS:
            raise LearningContractError(
                "calendar snapshot key set mismatch "
                f"missing={sorted(_CALENDAR_SNAPSHOT_KEYS - keys)!r} "
                f"extra={sorted(keys - _CALENDAR_SNAPSHOT_KEYS)!r}"
            )

        def _exact_str(field: str) -> str:
            value = raw[field]
            if type(value) is not str:
                raise LearningContractError(
                    f"calendar snapshot.{field} must be exact str, "
                    f"got {type(value).__name__}={value!r}"
                )
            if not value or value != value.strip():
                raise LearningContractError(
                    f"calendar snapshot.{field} must be non-empty without "
                    f"surrounding whitespace, got {value!r}"
                )
            return value

        try:
            coverage_start_s = _exact_str("coverage_start")
            coverage_end_s = _exact_str("coverage_end")
            coverage_start = date.fromisoformat(coverage_start_s)
            coverage_end = date.fromisoformat(coverage_end_s)
            if coverage_start.isoformat() != coverage_start_s:
                raise LearningContractError(
                    f"coverage_start must be canonical YYYY-MM-DD (got {coverage_start_s!r})"
                )
            if coverage_end.isoformat() != coverage_end_s:
                raise LearningContractError(
                    f"coverage_end must be canonical YYYY-MM-DD (got {coverage_end_s!r})"
                )
            raw_sessions = raw["ordered_sessions"]
            if not isinstance(raw_sessions, list):
                raise LearningContractError("ordered_sessions must be a list of date strings")
            sessions_list: list[date] = []
            for i, item in enumerate(raw_sessions):
                if type(item) is not str:
                    raise LearningContractError(
                        f"ordered_sessions[{i}] must be str, got {type(item).__name__}"
                    )
                session = date.fromisoformat(item)
                if session.isoformat() != item:
                    raise LearningContractError(
                        f"ordered_sessions[{i}] must be canonical YYYY-MM-DD (got {item!r})"
                    )
                sessions_list.append(session)
            sessions = tuple(sessions_list)
            captured_at_s = _exact_str("captured_at")
            if captured_at_s.endswith("Z") or captured_at_s.endswith("z"):
                raise LearningContractError(
                    f"captured_at must not use Z alias (got {captured_at_s!r})"
                )
            captured_at = datetime.fromisoformat(captured_at_s)
            if captured_at.tzinfo is None or captured_at.utcoffset() is None:
                raise LearningContractError("captured_at must be timezone-aware")
            if captured_at.isoformat() != captured_at_s:
                raise LearningContractError(
                    "captured_at must equal its parsed.isoformat() form "
                    f"(got {captured_at_s!r}, canonical={captured_at.isoformat()!r})"
                )
        except LearningContractError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise LearningContractError(f"calendar snapshot malformed: {exc}") from exc
        return cls(
            snapshot_id=_exact_str("snapshot_id"),
            contract_id=_exact_str("contract_id"),
            source=_exact_str("source"),
            benchmark=_exact_str("benchmark"),
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            ordered_sessions=sessions,
            source_revision=_exact_str("source_revision"),
            captured_at=captured_at,
            payload_digest=_exact_str("payload_digest"),
        )


def validate_trading_session_calendar_snapshot(
    snapshot: TradingSessionCalendarSnapshot,
) -> None:
    """Structural integrity only: recompute identity; do not grant active authority.

    Arbitrary contract/source/benchmark that rehash consistently still pass here.
    Use :func:`validate_active_stockbit_calendar_snapshot` at authority boundaries.
    """
    rebuilt = TradingSessionCalendarSnapshot.create(
        coverage_start=snapshot.coverage_start,
        coverage_end=snapshot.coverage_end,
        ordered_sessions=snapshot.ordered_sessions,
        source_revision=snapshot.source_revision,
        captured_at=snapshot.captured_at,
        contract_id=snapshot.contract_id,
        source=snapshot.source,
        benchmark=snapshot.benchmark,
    )
    if rebuilt.payload_digest != snapshot.payload_digest:
        raise LearningContractError(
            "calendar snapshot payload_digest mismatch: "
            f"stored={snapshot.payload_digest!r}, expected={rebuilt.payload_digest!r}"
        )
    if rebuilt.snapshot_id != snapshot.snapshot_id:
        raise LearningContractError(
            "calendar snapshot_id mismatch: "
            f"stored={snapshot.snapshot_id!r}, expected={rebuilt.snapshot_id!r}"
        )


def validate_active_stockbit_calendar_snapshot(
    snapshot: TradingSessionCalendarSnapshot,
) -> None:
    """Active path-label authority: Stockbit IHSG contract only."""
    validate_trading_session_calendar_snapshot(snapshot)
    if snapshot.contract_id != STOCKBIT_TRADING_SESSIONS_CONTRACT:
        raise LearningContractError(
            f"unsupported calendar contract: {snapshot.contract_id!r} "
            f"(expected {STOCKBIT_TRADING_SESSIONS_CONTRACT!r})"
        )
    if snapshot.source != TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT:
        raise LearningContractError(f"calendar source must be stockbit, got {snapshot.source!r}")
    if snapshot.benchmark != TRADING_SESSION_CALENDAR_BENCHMARK_IHSG:
        raise LearningContractError(f"calendar benchmark must be IHSG, got {snapshot.benchmark!r}")
    if type(snapshot.source_revision) is not str or not snapshot.source_revision:
        raise LearningContractError("calendar source_revision must be non-empty")
    if snapshot.source_revision != snapshot.source_revision.strip():
        raise LearningContractError(
            "calendar source_revision must not have surrounding whitespace "
            f"(got {snapshot.source_revision!r})"
        )


def _validate_sessions(
    sessions: tuple[date, ...],
    *,
    coverage_start: date,
    coverage_end: date,
) -> None:
    if list(sessions) != sorted(sessions):
        raise LearningContractError("ordered_sessions must be sorted ascending")
    if len(set(sessions)) != len(sessions):
        raise LearningContractError("ordered_sessions must not contain duplicates")
    for session in sessions:
        if session < coverage_start or session > coverage_end:
            raise LearningContractError(
                f"session {session.isoformat()} outside coverage "
                f"[{coverage_start.isoformat()}, {coverage_end.isoformat()}]"
            )
        if session.weekday() >= 5:
            raise LearningContractError(
                f"session {session.isoformat()} falls on a weekend; not a market session"
            )
