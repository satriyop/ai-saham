"""Repository port for deterministic signal forward labels."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalLabelHorizon,
)


class SignalForwardLabelsRepository(Protocol):
    """Local repository for schema-versioned signal forward labels."""

    def save_many(self, labels: list[SignalForwardLabel]) -> None:
        """Persist labels idempotently."""
        ...

    def get(
        self,
        ticker: str,
        signal_date: date,
        horizon: SignalLabelHorizon,
    ) -> SignalForwardLabel | None:
        """Return the latest label for ticker/date/horizon, if available."""
        ...

    def get_at(
        self,
        ticker: str,
        signal_date: date,
        horizon: SignalLabelHorizon,
        observation_captured_at,
    ) -> SignalForwardLabel | None:
        """Return the exact label for ticker/date/horizon/captured_at, if available."""
        ...

    def list(
        self,
        *,
        signal_date: date | None = None,
        horizon: SignalLabelHorizon | None = None,
        ticker: str | None = None,
    ) -> list[SignalForwardLabel]:
        """Return saved labels matching optional filters."""
        ...
