from pathlib import Path

from src.application.services.swing_data_refresh import refresh_swing_data


def test_refresh_swing_data_delegates_to_fetch_functions():
    calls = []
    broker_provider = object()

    def fetch_candles(**kwargs):
        calls.append(("candles", kwargs))
        return "cached-current"

    def create_broker_provider(name):
        calls.append(("provider", name))
        return broker_provider, "idx"

    def fetch_broker(**kwargs):
        calls.append(("broker", kwargs))
        return "flow-current"

    actions = refresh_swing_data(
        ticker="BBCA",
        db_path=Path("data/db/data.db"),
        force_refresh=True,
        market_refresh_days=90,
        broker_refresh_days=30,
        fetch_candles=fetch_candles,
        create_broker_provider=create_broker_provider,
        fetch_broker=fetch_broker,
    )

    assert actions == ("candles=cached-current", "broker(idx)=flow-current")
    assert calls[0] == (
        "candles",
        {
            "ticker": "BBCA",
            "days": 90,
            "db_path": Path("data/db/data.db"),
            "provider_name": "yahoo",
            "refresh": True,
        },
    )
    assert calls[1] == ("provider", None)
    assert calls[2] == (
        "broker",
        {
            "ticker": "BBCA",
            "days": 30,
            "db_path": Path("data/db/data.db"),
            "broker_provider": broker_provider,
            "refresh": True,
        },
    )
