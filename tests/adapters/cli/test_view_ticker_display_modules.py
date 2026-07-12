"""Smoke tests for ticker display module split.

Verifies that the public facade and each new display module import without error.
"""


def test_show_ticker_view_imports():
    from src.adapters.cli.view_ticker_display import DEFAULT_DB_PATH, show_ticker_view

    assert callable(show_ticker_view)
    assert DEFAULT_DB_PATH is not None


def test_formatters_module_imports():
    import src.adapters.cli.view_ticker_formatters  # noqa: F401


def test_identity_display_module_imports():
    import src.adapters.cli.view_ticker_identity_display  # noqa: F401


def test_valuation_display_module_imports():
    import src.adapters.cli.view_ticker_valuation_display  # noqa: F401


def test_flow_display_module_imports():
    import src.adapters.cli.view_ticker_flow_display  # noqa: F401


def test_events_display_module_imports():
    import src.adapters.cli.view_ticker_events_display  # noqa: F401


def test_market_activity_display_module_imports():
    import src.adapters.cli.view_ticker_market_activity_display  # noqa: F401
