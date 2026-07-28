"""
Broker-flow display helpers for saham plan swing commands.

Layer: Adapter
"""

from decimal import Decimal

from src.application.dto.swing_broker_detail import BrokerDetailLine


def fmt_money_short(value: Decimal) -> str:
    abs_value = abs(value)
    if abs_value >= Decimal("1000000000000"):
        return f"{value / Decimal('1000000000000'):.2f}T"
    if abs_value >= Decimal("1000000000"):
        return f"{value / Decimal('1000000000'):.2f}B"
    if abs_value >= Decimal("1000000"):
        return f"{value / Decimal('1000000'):.2f}M"
    if abs_value >= Decimal("1000"):
        return f"{value / Decimal('1000'):.2f}K"
    return f"{value:.2f}"


def fmt_money_short_signed(value: Decimal) -> str:
    sign = "+" if value > Decimal("0") else ""
    return f"{sign}{fmt_money_short(value)}"


def fmt_broker_detail_lines(lines: tuple[BrokerDetailLine, ...]) -> str:
    if not lines:
        return "none"
    parts = []
    for line in lines[:3]:
        parts.append(
            f"{line.broker_code} {fmt_money_short(line.net_value)} ({line.active_sessions}s)"
        )
    return ", ".join(parts)
