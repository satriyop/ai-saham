"""
SwingTradePlan — typed trade-structure artifact for plan swing (ADR-054 S5).

Holds geometry (entry/stop/target/lots) plus a frozen judgment reference.
Does not re-decide Action; Action is a snapshot from screen/plan judgment rules.

Layer: Domain
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

SWING_TRADE_PLAN_ARTIFACT_TYPE = "swing_trade_plan"
SWING_TRADE_PLAN_SCHEMA_VERSION = 1
SWING_TRADE_PLAN_HORIZON = "swing"


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except Exception:
        return None
    return d


@dataclass(frozen=True)
class SwingTradePlan:
    """Immutable swing trade structure plan."""

    ticker: str
    as_of: date
    horizon: str
    action: str | None
    action_source: str
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
    with_market_context: bool
    with_technical_gate: bool
    created_at: datetime
    plan_id: str
    incomplete_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.ticker or not str(self.ticker).strip():
            raise ValueError("ticker is required")
        if self.horizon != SWING_TRADE_PLAN_HORIZON:
            raise ValueError(f"horizon must be {SWING_TRADE_PLAN_HORIZON!r}")
        if not self.plan_id:
            raise ValueError("plan_id is required")

    @property
    def is_complete(self) -> bool:
        """True when entry/stop/target/lots are all present for journal handoff."""
        return (
            self.entry_price is not None
            and self.stop_price is not None
            and self.target_price is not None
            and self.lots is not None
            and self.lots > 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": SWING_TRADE_PLAN_ARTIFACT_TYPE,
            "schema_version": SWING_TRADE_PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "ticker": self.ticker,
            "as_of": self.as_of.isoformat(),
            "horizon": self.horizon,
            "judgment_ref": {
                "action": self.action,
                "action_source": self.action_source,
            },
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
                "with_market_context": self.with_market_context,
                "with_technical_gate": self.with_technical_gate,
                "created_at": self.created_at.isoformat(),
                "incomplete_reason": self.incomplete_reason,
                "is_complete": self.is_complete,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwingTradePlan":
        if not isinstance(data, dict):
            raise ValueError("swing_trade_plan payload must be an object")
        artifact = data.get("artifact_type")
        if artifact is not None and artifact != SWING_TRADE_PLAN_ARTIFACT_TYPE:
            raise ValueError(
                f"expected artifact_type={SWING_TRADE_PLAN_ARTIFACT_TYPE!r}, got {artifact!r}"
            )
        judgment = data.get("judgment_ref") or {}
        geometry = data.get("geometry") or {}
        setup_lens = data.get("setup_lens") or {}
        provenance = data.get("provenance") or {}

        # Allow nested (full plan file) or flat geometry for flexibility
        if "entry_price" in data and "geometry" not in data:
            geometry = data
            judgment = {
                "action": data.get("action"),
                "action_source": data.get("action_source", "unknown"),
            }
            setup_lens = {
                "setup_name": data.get("setup_name"),
                "setup_match": data.get("setup_match"),
            }
            provenance = data

        as_of_raw = data.get("as_of")
        if not as_of_raw:
            raise ValueError("as_of is required")
        as_of = date.fromisoformat(str(as_of_raw)[:10])

        created_raw = provenance.get("created_at") or data.get("created_at")
        if created_raw:
            created_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
        else:
            created_at = datetime.now().astimezone()

        plan_id = str(data.get("plan_id") or "")
        if not plan_id:
            raise ValueError("plan_id is required")

        return cls(
            ticker=str(data.get("ticker", "")).upper(),
            as_of=as_of,
            horizon=str(data.get("horizon") or SWING_TRADE_PLAN_HORIZON),
            action=(str(judgment.get("action")) if judgment.get("action") is not None else None),
            action_source=str(judgment.get("action_source") or "unknown"),
            entry_price=_dec(geometry.get("entry_price")),
            stop_price=_dec(geometry.get("stop_price")),
            target_price=_dec(geometry.get("target_price")),
            lots=int(geometry["lots"]) if geometry.get("lots") is not None else None,
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
            with_market_context=bool(provenance.get("with_market_context", False)),
            with_technical_gate=bool(provenance.get("with_technical_gate", False)),
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
