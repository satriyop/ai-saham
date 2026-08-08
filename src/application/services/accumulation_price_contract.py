"""Canonical persisted price representation for ACCUM corpus artifacts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_canonical_positive_decimal_text(raw: object) -> Decimal | None:
    """Return a positive finite Decimal only for its canonical text spelling.

    The canonical ACCUM observation writer serializes a ``Decimal`` with
    ``str(value)``. Requiring the inverse round trip keeps producer and consumer
    symmetric without accepting JSON numbers or value-equivalent aliases that
    the writer does not emit.
    """
    if type(raw) is not str or not raw:
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value <= 0:
        return None
    if str(value) != raw:
        return None
    return value
