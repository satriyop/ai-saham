"""
Pure period-enum mapping for Stockbit broker/foreign-flow endpoints.

Maps a (start_date, end_date) range to the Stockbit Exodus API period enum
string closest to that range. No network, browser, or config I/O.

Extracted from stockbit_broker_provider.py (audit finding 16).

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date


def broker_summary_period_for_range(start_date: date, end_date: date) -> str:
    """
    Map a date range to the marketdetectors BROKER_SUMMARY_PERIOD_* enum.

    Confirmed valid periods as of 2026-06-13.
    """
    days = (end_date - start_date).days
    if days <= 1:
        return "BROKER_SUMMARY_PERIOD_LATEST"
    elif days <= 7:
        return "BROKER_SUMMARY_PERIOD_LAST_7_DAYS"
    elif days <= 30:
        return "BROKER_SUMMARY_PERIOD_LAST_1_MONTH"
    elif days <= 90:
        return "BROKER_SUMMARY_PERIOD_LAST_3_MONTHS"
    elif days <= 180:
        return "BROKER_SUMMARY_PERIOD_LAST_6_MONTHS"
    else:
        return "BROKER_SUMMARY_PERIOD_LAST_1_YEAR"


def foreign_top_period_for_range(start_date: date, end_date: date) -> str:
    """
    Map a date range to the broker/activity RT_PERIOD_* enum.

    Confirmed valid periods as of 2026-06-13: 1D, 3D, 7D, 1M, 3M, 1Y.
    LAST_1_WEEK and LAST_6_MONTHS are not valid values.
    """
    days = (end_date - start_date).days
    if days <= 1:
        return "RT_PERIOD_LAST_1_DAY"
    elif days <= 3:
        return "RT_PERIOD_LAST_3_DAYS"
    elif days <= 7:
        return "RT_PERIOD_LAST_7_DAYS"
    elif days <= 30:
        return "RT_PERIOD_LAST_1_MONTH"
    elif days <= 90:
        return "RT_PERIOD_LAST_3_MONTHS"
    else:
        return "RT_PERIOD_LAST_1_YEAR"
