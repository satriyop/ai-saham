"""SetupAction canonical display helpers (ADR-026)."""

from src.domain.value_objects.trade_setup import SetupAction


def test_is_actionable_is_enter_only():
    assert SetupAction.ENTER.is_actionable is True
    assert SetupAction.WATCH.is_actionable is False
    assert SetupAction.AVOID.is_actionable is False


def test_is_open_watchlist_is_enter_or_watch():
    assert SetupAction.ENTER.is_open_watchlist is True
    assert SetupAction.WATCH.is_open_watchlist is True
    assert SetupAction.AVOID.is_open_watchlist is False
    assert SetupAction.BLOCKED_EXECUTION.is_open_watchlist is False


def test_display_sort_rank_enter_first():
    ranks = [a.display_sort_rank for a in SetupAction]
    assert SetupAction.ENTER.display_sort_rank == min(ranks)
    assert SetupAction.ENTER.display_sort_rank < SetupAction.WATCH.display_sort_rank
    assert SetupAction.WATCH.display_sort_rank < SetupAction.AVOID.display_sort_rank


def test_from_value_parses_string_and_unknown():
    assert SetupAction.from_value("enter") is SetupAction.ENTER
    assert SetupAction.from_value(SetupAction.WATCH) is SetupAction.WATCH
    assert SetupAction.from_value("PRIME") is None
    assert SetupAction.from_value(None) is None
