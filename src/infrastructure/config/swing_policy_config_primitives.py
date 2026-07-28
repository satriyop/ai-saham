"""
Primitive helpers for parsing configuration fields with default fallbacks.

Layer: Infrastructure
"""


def float_or_default(data: dict, key: str, default: float) -> float:
    return float(data[key]) if key in data else default


def int_or_default(data: dict, key: str, default: int) -> int:
    return int(data[key]) if key in data else default


def str_or_default(data: dict, key: str, default: str) -> str:
    return str(data[key]) if key in data else default


def bool_or_default(data: dict, key: str, default: bool) -> bool:
    return bool(data[key]) if key in data else default


def phase_names_or_default(data: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = data.get(key)
    if not isinstance(raw, list):
        return default
    return tuple(str(v).strip().upper() for v in raw if v)


def broker_codes_or_default(data: dict, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = data.get("brokers") or []
    parsed = tuple(str(c).strip().upper() for c in raw if c)
    return parsed if parsed else default
