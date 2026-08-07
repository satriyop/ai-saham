"""Typed swing structure artifact with a frozen screen-judgment reference.

Layer: Domain. The artifact contains no IO and never derives or changes Action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from src.domain.value_objects.trade_setup import SetupAction

SWING_TRADE_PLAN_ARTIFACT_TYPE = "swing_trade_plan"
SWING_TRADE_PLAN_SCHEMA_VERSION = 2
SWING_TRADE_PLAN_HORIZON = "swing"


class SwingPlanJudgmentStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SwingPlanJudgmentSource(str, Enum):
    SCREEN_ACCUM = "screen_accum"


class SwingPlanJudgmentUnavailableReason(str, Enum):
    NO_SCREEN_CANDIDATE = "no_screen_candidate"
    NO_SCREEN_SIGNAL_ASSESSMENT = "no_screen_signal_assessment"
    NO_SCREEN_RISK_ASSESSMENT = "no_screen_risk_assessment"
    NO_SCREEN_TRADE_SETUP = "no_screen_trade_setup"


@dataclass(frozen=True)
class SwingPlanJudgmentReference:
    """Serialized authority proof for a structure artifact."""

    status: SwingPlanJudgmentStatus
    source: SwingPlanJudgmentSource
    ticker: str
    snapshot_date: date
    action: SetupAction | None
    unavailable_reason: SwingPlanJudgmentUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SwingPlanJudgmentStatus):
            raise TypeError("status must be a SwingPlanJudgmentStatus")
        if not isinstance(self.source, SwingPlanJudgmentSource):
            raise TypeError("source must be a SwingPlanJudgmentSource")
        if self.source != SwingPlanJudgmentSource.SCREEN_ACCUM:
            raise ValueError("judgment source must be screen_accum")
        if not self.ticker or self.ticker != self.ticker.upper():
            raise ValueError("judgment ticker must be canonical uppercase")
        if not isinstance(self.snapshot_date, date):
            raise TypeError("judgment snapshot_date must be a date")
        if self.status == SwingPlanJudgmentStatus.AVAILABLE:
            if not isinstance(self.action, SetupAction):
                raise ValueError("AVAILABLE judgment requires a valid SetupAction")
            if self.unavailable_reason is not None:
                raise ValueError("AVAILABLE judgment cannot have an unavailable reason")
        else:
            if self.action is not None:
                raise ValueError("UNAVAILABLE judgment cannot carry an Action")
            if not isinstance(self.unavailable_reason, SwingPlanJudgmentUnavailableReason):
                raise ValueError("UNAVAILABLE judgment requires a valid reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "source": self.source.value,
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "action": self.action.value if self.action is not None else None,
            "unavailable_reason": (
                self.unavailable_reason.value if self.unavailable_reason is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SwingPlanJudgmentReference":
        if not isinstance(data, dict):
            raise ValueError("judgment_ref must be an object")
        try:
            status = SwingPlanJudgmentStatus(data["status"])
            source = SwingPlanJudgmentSource(data["source"])
            ticker = str(data["ticker"])
            snapshot_date = date.fromisoformat(str(data["snapshot_date"]))
            action = SetupAction(data["action"]) if data.get("action") is not None else None
            reason = (
                SwingPlanJudgmentUnavailableReason(data["unavailable_reason"])
                if data.get("unavailable_reason") is not None
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid swing plan judgment_ref: {exc}") from exc
        return cls(
            status=status,
            source=source,
            ticker=ticker,
            snapshot_date=snapshot_date,
            action=action,
            unavailable_reason=reason,
        )


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc


@dataclass(frozen=True)
class SwingTradePlan:
    """Immutable swing geometry plus a non-inferred screen judgment reference."""

    ticker: str
    as_of: date
    horizon: str
    judgment_ref: SwingPlanJudgmentReference
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    lots: int | None
    capital: Decimal | None
    risk_pct: Decimal | None
    risk_amount: Decimal | None
    setup_name: str | None
    setup_match: str | None
    max_hold_days: int | None
    stop_loss_pct: Decimal | None
    take_profit_pct: Decimal | None
    created_at: datetime
    plan_id: str
    incomplete_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.ticker or self.ticker != self.ticker.upper():
            raise ValueError("ticker must be canonical uppercase")
        if self.horizon != SWING_TRADE_PLAN_HORIZON:
            raise ValueError(f"horizon must be {SWING_TRADE_PLAN_HORIZON!r}")
        if not self.plan_id:
            raise ValueError("plan_id is required")
        if self.judgment_ref.ticker != self.ticker:
            raise ValueError("plan and judgment tickers must match")
        if self.judgment_ref.snapshot_date != self.as_of:
            raise ValueError("plan as_of and judgment snapshot_date must match")

    @property
    def geometry_complete(self) -> bool:
        return (
            self.entry_price is not None
            and self.stop_price is not None
            and self.target_price is not None
            and self.lots is not None
            and self.lots > 0
        )

    @property
    def handoff_ready(self) -> bool:
        return (
            self.geometry_complete and self.judgment_ref.status == SwingPlanJudgmentStatus.AVAILABLE
        )

    @property
    def judgment_available(self) -> bool:
        return self.judgment_ref.status == SwingPlanJudgmentStatus.AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": SWING_TRADE_PLAN_ARTIFACT_TYPE,
            "schema_version": SWING_TRADE_PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "ticker": self.ticker,
            "as_of": self.as_of.isoformat(),
            "horizon": self.horizon,
            "judgment_ref": self.judgment_ref.to_dict(),
            "geometry": {
                "entry_price": str(self.entry_price) if self.entry_price is not None else None,
                "stop_price": str(self.stop_price) if self.stop_price is not None else None,
                "target_price": str(self.target_price) if self.target_price is not None else None,
                "lots": self.lots,
                "capital": str(self.capital) if self.capital is not None else None,
                "risk_pct": str(self.risk_pct) if self.risk_pct is not None else None,
                "risk_amount": str(self.risk_amount) if self.risk_amount is not None else None,
                "stop_loss_pct": (
                    str(self.stop_loss_pct) if self.stop_loss_pct is not None else None
                ),
                "take_profit_pct": (
                    str(self.take_profit_pct) if self.take_profit_pct is not None else None
                ),
                "max_hold_days": self.max_hold_days,
            },
            "setup_lens": {
                "setup_name": self.setup_name,
                "setup_match": self.setup_match,
            },
            "provenance": {
                "created_at": self.created_at.isoformat(),
                "incomplete_reason": self.incomplete_reason,
                "geometry_complete": self.geometry_complete,
                "handoff_ready": self.handoff_ready,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwingTradePlan":
        if not isinstance(data, dict):
            raise ValueError("swing_trade_plan payload must be an object")
        if data.get("artifact_type") != SWING_TRADE_PLAN_ARTIFACT_TYPE:
            raise ValueError(f"artifact_type must be {SWING_TRADE_PLAN_ARTIFACT_TYPE!r}")
        if data.get("schema_version") != SWING_TRADE_PLAN_SCHEMA_VERSION:
            raise ValueError(
                "unsupported swing_trade_plan schema_version; rerun screen and plan to create v2"
            )

        judgment = SwingPlanJudgmentReference.from_dict(data.get("judgment_ref"))
        geometry = data.get("geometry")
        setup_lens = data.get("setup_lens")
        provenance = data.get("provenance")
        if not isinstance(geometry, dict):
            raise ValueError("geometry must be an object")
        if not isinstance(setup_lens, dict):
            raise ValueError("setup_lens must be an object")
        if not isinstance(provenance, dict):
            raise ValueError("provenance must be an object")

        try:
            as_of = date.fromisoformat(str(data["as_of"]))
            created_at = datetime.fromisoformat(
                str(provenance["created_at"]).replace("Z", "+00:00")
            )
            plan_id = str(data["plan_id"])
            lots = int(geometry["lots"]) if geometry.get("lots") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid swing_trade_plan identity: {exc}") from exc

        return cls(
            ticker=str(data.get("ticker", "")),
            as_of=as_of,
            horizon=str(data.get("horizon", "")),
            judgment_ref=judgment,
            entry_price=_dec(geometry.get("entry_price")),
            stop_price=_dec(geometry.get("stop_price")),
            target_price=_dec(geometry.get("target_price")),
            lots=lots,
            capital=_dec(geometry.get("capital")),
            risk_pct=_dec(geometry.get("risk_pct")),
            risk_amount=_dec(geometry.get("risk_amount")),
            setup_name=(
                str(setup_lens["setup_name"]) if setup_lens.get("setup_name") is not None else None
            ),
            setup_match=(
                str(setup_lens["setup_match"])
                if setup_lens.get("setup_match") is not None
                else None
            ),
            max_hold_days=(
                int(geometry["max_hold_days"])
                if geometry.get("max_hold_days") is not None
                else None
            ),
            stop_loss_pct=_dec(geometry.get("stop_loss_pct")),
            take_profit_pct=_dec(geometry.get("take_profit_pct")),
            created_at=created_at,
            plan_id=plan_id,
            incomplete_reason=(
                str(provenance["incomplete_reason"])
                if provenance.get("incomplete_reason") is not None
                else None
            ),
        )


def compute_plan_id(payload_without_id: dict[str, Any]) -> str:
    """Stable content hash for plan identity (excludes plan_id itself)."""

    canonical = json.dumps(payload_without_id, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
