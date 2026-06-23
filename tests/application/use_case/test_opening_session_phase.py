from datetime import datetime
from zoneinfo import ZoneInfo

from src.application.use_case.opening_snapshot_use_case import classify_opening_capture_phase

IDX_TZ = ZoneInfo("Asia/Jakarta")


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 6, 18, hour, minute, tzinfo=IDX_TZ)


def test_classifies_pre_ncp_window():
    assert classify_opening_capture_phase(_at(8, 45)) == "PRE_NCP"
    assert classify_opening_capture_phase(_at(8, 55)) == "PRE_NCP"


def test_classifies_ncp_locked_only_before_regular_open():
    assert classify_opening_capture_phase(_at(8, 56)) == "NCP_LOCKED"
    assert classify_opening_capture_phase(_at(8, 59)) == "NCP_LOCKED"


def test_classifies_post_open_as_not_ncp_locked():
    assert classify_opening_capture_phase(_at(9, 0)) == "OPEN"
    assert classify_opening_capture_phase(_at(12, 56)) == "POST_OPEN"
