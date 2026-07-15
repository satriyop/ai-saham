"""
Typed source status for `saham screen pre-open` results.

Distinguishes a genuine empty result from provider failure, outside-window
access, and snapshot fallback so "No candidates" is never ambiguous.

Layer: Domain
"""

from enum import Enum


class PreOpenSourceStatus(str, Enum):
    LIVE_SUCCESS = "LIVE_SUCCESS"
    SNAPSHOT_SUCCESS = "SNAPSHOT_SUCCESS"
    EMPTY_CONFIRMED = "EMPTY_CONFIRMED"
    UNAVAILABLE = "UNAVAILABLE"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
